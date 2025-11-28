# notifications/utils.py

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .models import Notification


def get_unread_count(user):
    """Returns the total number of unread generic notifications for a user."""
    return Notification.objects.filter(recipient=user, is_read=False).count()


def push_unread_count_update(user):
    """Pushes the new unread count to the user's WebSocket channel."""
    if not user.is_authenticated:
        return

    channel_layer = get_channel_layer()
    new_count = get_unread_count(user)
    user_group_name = f'user_{user.id}'

    # Send the message to the user's group
    async_to_sync(channel_layer.group_send)(
        user_group_name,
        {
            'type': 'push.count.update',  # Name of the handler method in the Consumer
            'unread_count': new_count
        }
    )