from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from .models import Order


@receiver(post_save, sender=Order)
def send_order_confirmation_email(sender, instance, created, **kwargs):
    if instance.status == "paid":
        subject = f"Payment Confirmed - Order #{instance.order_number}"

        context = {
            'user': instance.user,
            'order': instance,
            'dashboard_url': "https://e-vuka.com/dashboard",
            'items': instance.items.all()
        }

        html_message = render_to_string('emails/order_confirmed.html', context)
        plain_message = strip_tags(html_message)

        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[instance.user.email],
            html_message=html_message,
            fail_silently=False,
        )