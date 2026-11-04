from rest_framework.permissions import BasePermission

from .models import UserProfile


class IsAdminRole(BasePermission):
    """Allow only active Django staff/superusers or ADMIN profiles."""

    message = "Administrator access is required."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated or not user.is_active:
            return False
        if user.is_staff or user.is_superuser:
            return True
        try:
            return user.profile.role == UserProfile.Role.ADMIN
        except UserProfile.DoesNotExist:
            return False


class IsAgentOrAdmin(BasePermission):
    """Allow support agents and administrators."""

    message = "Support agent or administrator access is required."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated or not user.is_active:
            return False
        if user.is_staff or user.is_superuser:
            return True
        try:
            return user.profile.role in (
                UserProfile.Role.AGENT,
                UserProfile.Role.ADMIN,
            )
        except UserProfile.DoesNotExist:
            return False


class IsCustomer(BasePermission):
    """Allow authenticated customer accounts only."""

    message = "Customer access is required."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated or not user.is_active:
            return False
        try:
            return user.profile.role == UserProfile.Role.CUSTOMER
        except UserProfile.DoesNotExist:
            return False
