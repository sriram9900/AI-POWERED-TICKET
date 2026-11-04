
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import RegisterView, LoginView, MeView


urlpatterns = [

    # User Registration
    path("register/", RegisterView.as_view(), name="register"),

    # User Login
    path("login/", LoginView.as_view(), name="login"),

    # Get Logged-in User Profile
    path("me/", MeView.as_view(), name="me"),

    # Refresh JWT Access Token
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),

]
