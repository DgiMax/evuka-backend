# users/permissions.py
from rest_framework import permissions
from rest_framework.permissions import BasePermission


class IsVerified(BasePermission):
    """
    Allow access only to verified users.
    """

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_verified


class IsTutor(permissions.BasePermission):
    """
    Custom permission to only allow users with the 'is_tutor' flag.
    """
    def has_permission(self, request, view):
        # Check that the user is authenticated and has the 'is_tutor' flag
        return request.user and request.user.is_authenticated and request.user.is_tutor
