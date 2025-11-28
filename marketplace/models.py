from django.db import models
from django.db.models import Q, CheckConstraint
from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage

from courses.models import Course
from events.models import Event

User = get_user_model()


class Wishlist(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="wishlist")
    course = models.ForeignKey(
        Course, null=True, blank=True, on_delete=models.CASCADE
    )
    event = models.ForeignKey(Event, null=True, blank=True, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            CheckConstraint(
                check=(
                    Q(course__isnull=False, event__isnull=True)
                    | Q(course__isnull=True, event__isnull=False)
                ),
                name="wishlist_only_one_item_type",
            )
        ]
        unique_together = (("user", "course"), ("user", "event"))

    def __str__(self):
        if self.course:
            return f"{self.user.username} - Course: {self.course.title}"
        if self.event:
            return f"{self.user.username} - Event: {self.event.title}"
        return f"{self.user.username} - Empty Wishlist Item"

    @property
    def item_title(self):
        return self.course.title if self.course else self.event.title

    @property
    def item_slug(self):
        return self.course.slug if self.course else self.event.slug

    @property
    def item_type(self):
        return "course" if self.course else "event"

    @property
    def item_image(self):
        """Return a safe image/thumbnail URL for the wishlist item, checking existence."""
        if self.course and self.course.thumbnail:
            thumb = self.course.thumbnail
            if thumb and getattr(thumb, "name", None) and default_storage.exists(thumb.name):
                return thumb.url
            return None

        if self.event:
            img = self.event.banner_image
            if img and getattr(img, "name", None) and default_storage.exists(img.name):
                return img.url
            return None

        return None