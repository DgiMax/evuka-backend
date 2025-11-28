# notifications/consumers.py

import json
from channels.generic.websocket import AsyncWebsocketConsumer

class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]

        if self.user.is_authenticated:
            self.user_group_name = f'user_{self.user.id}'

            # Add channel to the user's personal group
            await self.channel_layer.group_add(
                self.user_group_name,
                self.channel_name
            )
            await self.accept()
        else:
            await self.close()

    async def disconnect(self, close_code):
        if self.user.is_authenticated:
            await self.channel_layer.group_discard(
                self.user_group_name,
                self.channel_name
            )

    # Handler for messages pushed from Django views/tasks
    async def push_count_update(self, event):
        """Receives and sends the updated unread count."""
        await self.send(text_data=json.dumps({
            'type': event['type'],
            'unread_count': event['unread_count']
        }))