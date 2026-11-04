from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from .models import UserProfile

User = get_user_model()


class AuthenticationAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.register_url = "/api/auth/register/"
        self.login_url = "/api/auth/login/"
        self.me_url = "/api/auth/me/"
        self.refresh_url = "/api/auth/token/refresh/"
        self.logout_url = "/api/auth/logout/"
        self.password = "Strong-Test-Password-928!"

    def create_customer(self, email="customer@example.com"):
        user = User.objects.create_user(
            username=email,
            email=email,
            password=self.password,
        )
        UserProfile.objects.create(user=user, role=UserProfile.Role.CUSTOMER)
        return user

    def test_registration_creates_customer_profile_and_tokens(self):
        response = self.client.post(
            self.register_url,
            {
                "first_name": "Test",
                "last_name": "Customer",
                "email": "new-customer@example.com",
                "password": self.password,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        user = User.objects.get(email="new-customer@example.com")
        self.assertEqual(user.profile.role, UserProfile.Role.CUSTOMER)
        self.assertTrue(user.check_password(self.password))

    def test_duplicate_email_is_rejected(self):
        self.create_customer()
        response = self.client.post(
            self.register_url,
            {
                "email": "CUSTOMER@example.com",
                "password": self.password,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_login_returns_tokens(self):
        self.create_customer()
        response = self.client.post(
            self.login_url,
            {"email": "customer@example.com", "password": self.password},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_me_requires_access_token(self):
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, 401)

    def test_me_returns_authenticated_user(self):
        user = self.create_customer()
        self.client.force_authenticate(user=user)
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["user"]["email"], user.email)

    def test_refresh_returns_new_access_token(self):
        user = self.create_customer()
        refresh = RefreshToken.for_user(user)
        response = self.client.post(
            self.refresh_url,
            {"refresh": str(refresh)},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)

    def test_logout_blacklists_refresh_token(self):
        user = self.create_customer()
        refresh = RefreshToken.for_user(user)
        self.client.force_authenticate(user=user)
        response = self.client.post(
            self.logout_url,
            {"refresh": str(refresh)},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(RefreshToken(str(refresh)).check_blacklist())

    def test_only_admin_can_change_user_role(self):
        customer = self.create_customer()
        agent = self.create_customer("agent@example.com")
        agent.profile.role = UserProfile.Role.AGENT
        agent.profile.save(update_fields=["role"])

        self.client.force_authenticate(user=customer)
        denied = self.client.patch(
            f"/api/auth/users/{agent.pk}/role/",
            {"role": "CUSTOMER"},
            format="json",
        )
        self.assertEqual(denied.status_code, 403)

        admin = User.objects.create_superuser(
            username="admin@example.com",
            email="admin@example.com",
            password=self.password,
        )
        self.client.force_authenticate(user=admin)
        allowed = self.client.patch(
            f"/api/auth/users/{agent.pk}/role/",
            {"role": "AGENT"},
            format="json",
        )
        self.assertEqual(allowed.status_code, 200)
        agent.profile.refresh_from_db()
        self.assertEqual(agent.profile.role, UserProfile.Role.AGENT)
