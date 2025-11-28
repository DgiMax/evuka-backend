import jwt
import time
from django.conf import settings

def generate_jitsi_token(user, room_name, is_moderator=False):
    JITSI_APP_ID = getattr(settings, "JITSI_APP_ID", "my_app_id")
    JITSI_APP_SECRET = getattr(settings, "JITSI_APP_SECRET", "my_secret_key")
    JITSI_DOMAIN = getattr(settings, "JITSI_DOMAIN", "http://localhost:8981")

    now = int(time.time())

    user_context = {
        "name": user.get_full_name() or user.username,
        "email": user.email,
        "id": str(user.id),
    }

    if is_moderator:
        user_context["moderator"] = "true"

    payload = {
        "aud": JITSI_APP_ID,
        "iss": JITSI_APP_ID,
        "sub": JITSI_DOMAIN,
        "room": room_name,
        "exp": now + 3600,
        "iat": now,
        "nbf": now,
        "context": {"user": user_context},
    }

    token = jwt.encode(payload, JITSI_APP_SECRET, algorithm="HS256")

    # PyJWT>=2 returns a str, older versions return bytes
    if isinstance(token, bytes):
        token = token.decode("utf-8")

    return token
