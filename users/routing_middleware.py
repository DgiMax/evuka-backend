from channels.db import database_sync_to_async
from django.conf import settings


@database_sync_to_async
def get_user_from_jwt_cookie(scope):
    from django.db import close_old_connections
    from django.contrib.auth.models import AnonymousUser
    from rest_framework_simplejwt.authentication import JWTAuthentication
    from rest_framework_simplejwt.tokens import AccessToken

    close_old_connections()

    query_string = scope.get('query_string', b'').decode()
    query_params = dict(x.split('=', 1) for x in query_string.split('&') if '=' in x)

    access_token_value = query_params.get('token')

    if access_token_value:
        try:
            validated_token = AccessToken(access_token_value)
            jwt_auth = JWTAuthentication()
            user = jwt_auth.get_user(validated_token)

            return user
        except Exception:
            return AnonymousUser()

    return AnonymousUser()


class JWTAuthMiddleware:
    """
    Middleware that populates scope["user"] using a JWT token found in the query string.
    """

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'websocket':
            scope['user'] = await get_user_from_jwt_cookie(scope)

        return await self.inner(scope, receive, send)


def JWTAuthMiddlewareStack(inner):
    """
    The final middleware stack for ASGI.
    """
    return JWTAuthMiddleware(inner)