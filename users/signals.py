from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import StudentProfile

User = get_user_model()


@receiver(post_save, sender=User)
def create_student_profile(sender, instance, created, **kwargs):
    """
    When a new User is created, automatically create a
    StudentProfile for them.
    """
    if created:
        StudentProfile.objects.get_or_create(user=instance)


@receiver(post_delete, sender=User)
def delete_student_profile(sender, instance, **kwargs):
    """
    When a User is deleted, also delete their StudentProfile.
    """
    try:
        instance.marketplace_learner.delete()
    except StudentProfile.DoesNotExist:
        pass