import logging

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.db import IntegrityError, transaction

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .models import UserProfile
from .permissions import IsAdminRole
from .serializers import (
    GoogleLoginSerializer,
    LoginSerializer,
    RegisterSerializer,
    RoleUpdateSerializer,
    UserSerializer,
)

logger = logging.getLogger(__name__)
User = get_user_model()


def issue_tokens(user):
    """Create a refresh token and its corresponding access token."""
    refresh = RefreshToken.for_user(user)
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    }


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            with transaction.atomic():
                user = serializer.save()
                tokens = issue_tokens(user)
        except IntegrityError:
            return Response(
                {"email": ["An account with this email already exists."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "message": "Registration successful",
                "user": UserSerializer(user).data,
                **tokens,
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"].strip().lower()
        password = serializer.validated_data["password"]
        user_record = User.objects.filter(email__iexact=email).first()

        if user_record is None:
            return Response(
                {"detail": "Invalid email or password."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        user = authenticate(
            request,
            username=user_record.username,
            password=password,
        )
        if user is None:
            return Response(
                {"detail": "Invalid email or password."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if not user.is_active:
            return Response(
                {"detail": "This account is inactive."},
                status=status.HTTP_403_FORBIDDEN,
            )

        UserProfile.objects.get_or_create(user=user)
        return Response(
            {
                "message": "Login successful",
                "user": UserSerializer(user).data,
                **issue_tokens(user),
            },
            status=status.HTTP_200_OK,
        )


class GoogleLoginView(APIView):
    """Verify a Google ID token on the server before issuing local JWTs."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = GoogleLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if not settings.GOOGLE_CLIENT_ID:
            return Response(
                {"detail": "Google Sign-In is not configured on this server."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        try:
            from google.auth.transport import requests as google_requests
            from google.oauth2 import id_token

            claims = id_token.verify_oauth2_token(
                serializer.validated_data["id_token"],
                google_requests.Request(),
                settings.GOOGLE_CLIENT_ID,
            )
        except (ValueError, ImportError):
            return Response(
                {"detail": "Invalid Google ID token."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except Exception:
            logger.exception("Google token verification failed")
            return Response(
                {"detail": "Google Sign-In could not be verified."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        google_sub = claims.get("sub")
        email = (claims.get("email") or "").strip().lower()
        if not google_sub or not email or claims.get("email_verified") is not True:
            return Response(
                {"detail": "Google must provide a verified email address."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            with transaction.atomic():
                profile = UserProfile.objects.select_related("user").filter(
                    google_sub=google_sub
                ).first()

                if profile:
                    user = profile.user
                    if user.email.lower() != email:
                        return Response(
                            {"detail": "Google account email does not match the linked account."},
                            status=status.HTTP_403_FORBIDDEN,
                        )
                else:
                    user = User.objects.filter(email__iexact=email).first()
                    if user is None:
                        user = User.objects.create_user(
                            username=email,
                            email=email,
                            first_name=claims.get("given_name", ""),
                            last_name=claims.get("family_name", ""),
                        )
                    if not user.is_active:
                        return Response(
                            {"detail": "This account is inactive."},
                            status=status.HTTP_403_FORBIDDEN,
                        )
                    profile, _ = UserProfile.objects.get_or_create(user=user)
                    if profile.google_sub and profile.google_sub != google_sub:
                        return Response(
                            {"detail": "This account is linked to a different Google identity."},
                            status=status.HTTP_409_CONFLICT,
                        )
                    profile.google_sub = google_sub
                    profile.save(update_fields=["google_sub", "updated_at"])
        except IntegrityError:
            return Response(
                {"detail": "This Google account is already linked to another user."},
                status=status.HTTP_409_CONFLICT,
            )

        if not user.is_active:
            return Response(
                {"detail": "This account is inactive."},
                status=status.HTTP_403_FORBIDDEN,
            )

        return Response(
            {
                "message": "Google login successful",
                "user": UserSerializer(user).data,
                **issue_tokens(user),
            },
            status=status.HTTP_200_OK,
        )


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        UserProfile.objects.get_or_create(user=request.user)
        return Response(
            {"user": UserSerializer(request.user).data},
            status=status.HTTP_200_OK,
        )


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response(
                {"refresh": ["This field is required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            token = RefreshToken(refresh_token)
            if str(token["user_id"]) != str(request.user.pk):
                return Response(
                    {"detail": "This refresh token does not belong to the logged-in user."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            token.blacklist()
        except TokenError:
            return Response(
                {"detail": "Invalid or expired refresh token."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {"message": "Logout successful. Refresh token has been revoked."},
            status=status.HTTP_200_OK,
        )


class UserRoleUpdateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def patch(self, request, user_id):
        target_user = User.objects.filter(pk=user_id).first()
        if target_user is None:
            return Response(
                {"detail": "User not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = RoleUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile, _ = UserProfile.objects.get_or_create(user=target_user)
        profile.role = serializer.validated_data["role"]
        profile.save(update_fields=["role", "updated_at"])

        return Response(
            {
                "message": "User role updated successfully.",
                "user": UserSerializer(target_user).data,
            },
            status=status.HTTP_200_OK,
        )


@api_view(["GET"])
@permission_classes([AllowAny])
def home(request):
    return Response(
        {
            "message": "Welcome to AI-Powered Ticket Management System",
            "status": "Server is running successfully",
            "authentication": {
                "register": "/api/auth/register/",
                "login": "/api/auth/login/",
                "google_login": "/api/auth/google/",
                "profile": "/api/auth/me/",
                "refresh": "/api/auth/token/refresh/",
                "logout": "/api/auth/logout/",
            },
        }
    )
