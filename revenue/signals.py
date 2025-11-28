from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from .models import Wallet


User = settings.AUTH_USER_MODEL


@receiver(post_save, sender=User)
def create_user_wallet(sender, instance, created, **kwargs):
    if created and not hasattr(instance, "wallet"):
        Wallet.objects.create(owner_user=instance)


@receiver(post_save, sender="organizations.Organization")
def create_org_wallet(sender, instance, created, **kwargs):
    if created and not hasattr(instance, "wallet"):
        Wallet.objects.create(owner_org=instance)
