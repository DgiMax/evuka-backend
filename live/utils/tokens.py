import jwt
import datetime
from django.conf import settings


def generate_live_service_token(user, room_id, role):
    """
    Generates a JWT specifically for the separate FastAPI WebSocket service.
    """
    # Use a specific secret for the live service, or fall back to the main one
    secret = getattr(settings, "LIVE_SERVICE_SECRET", settings.SECRET_KEY)

    expiration = datetime.datetime.utcnow() + datetime.timedelta(hours=6)

    payload = {
        "user_id": user.id,
        "username": user.get_full_name() or user.username,
        "role": role,  # 'host' or 'viewer'
        "room_id": room_id,  # e.g., the lesson slug or ID
        "exp": expiration,
        "iss": "django-backend"
    }

    return jwt.encode(payload, secret, algorithm="HS256")