from django.db import models
from django.conf import settings

class ChatHistory(models.Model):
    """Stores the conversation history for a specific course and user."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ai_chats"
    )
    course = models.ForeignKey(
        'courses.Course',
        on_delete=models.CASCADE,
        related_name="ai_chats"
    )
    history_json = models.JSONField(default=list)
    last_updated = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'course')
        verbose_name_plural = "Chat Histories"

    def __str__(self):
        return f"Chat History for {self.user.username} in {self.course.title}"