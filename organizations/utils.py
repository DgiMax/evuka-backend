from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.conf import settings


def send_membership_welcome_email(membership):
    user = membership.user
    org = membership.organization

    subject = f"Welcome to {org.name} on Evuka"

    context = {
        'user': user,
        'organization': org,
        'role_display': membership.get_role_display(),
        'expires_at': membership.expires_at,
    }

    html_content = render_to_string('emails/org_welcome.html', context)

    email = EmailMessage(
        subject=subject,
        body=html_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    email.content_subtype = "html"
    email.send(fail_silently=True)