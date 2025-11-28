from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework import exceptions

class CookieJWTAuthentication(JWTAuthentication):
    """
    Custom JWT authentication that first tries to get the token from cookies,
    then falls back to the Authorization header if not found.
    """

    def authenticate(self, request):
        # 1️⃣ Try reading token from cookies
        access_token = request.COOKIES.get("access_token")

        if access_token:
            try:
                validated_token = self.get_validated_token(access_token)
                user = self.get_user(validated_token)
                return (user, validated_token)
            except exceptions.AuthenticationFailed:
                # Token in cookie is invalid or expired
                return None

        # 2️⃣ Fallback to default Authorization header (Bearer)
        return super().authenticate(request)
