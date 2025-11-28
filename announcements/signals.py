# announcements/signals.py (CORRECTED FINAL LOGIC)

from django.db.models.signals import post_save, pre_save # 🚨 Added pre_save
from django.dispatch import receiver
from .models import Announcement
from .views import _create_notifications_for_announcement

# Dictionary to hold old status values before they are saved
# Key: Announcement ID, Value: Old Status (e.g., 'draft')
_announcement_status_cache = {}


@receiver(pre_save, sender=Announcement)
def cache_old_status(sender, instance, **kwargs):
    """Caches the current status before the model is saved to the database."""
    if instance.pk:
        try:
            # We must use .only() to minimize the DB hit
            old_status = Announcement.objects.only('status').get(pk=instance.pk).status
            _announcement_status_cache[instance.pk] = old_status
        except Announcement.DoesNotExist:
            # New object, no need to cache
            pass

@receiver(post_save, sender=Announcement)
def handle_announcement_publication(sender, instance, created, **kwargs):
    """
    Triggers notification creation ONLY if the status transitions to 'published'.
    """
    # 1. Condition: It must be published now.
    if instance.status != 'published':
        # Clear the cache entry if it exists, as the status is not the target state.
        _announcement_status_cache.pop(instance.pk, None)
        return

    # 2. Check 1: If newly created, run helper.
    if created:
        _create_notifications_for_announcement(instance)
        return

    # 3. Check 2: Check for status transition.
    old_status = _announcement_status_cache.pop(instance.pk, None)

    if old_status and old_status != 'published':
        # Success! Status transitioned from Draft, Pending, or Scheduled TO Published.
        _create_notifications_for_announcement(instance)
        return

    # If old_status was 'published', we do nothing (prevent re-publishing).