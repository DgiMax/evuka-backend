from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.conf import settings
from django.utils import timezone

def send_unified_welcome_email(user, new_roles):
    """
    Sends a combined welcome email for all newly activated roles.
    """
    if not user.email or not new_roles:
        return False

    role_display = ", ".join([r.capitalize() for r in new_roles])
    subject = f"Evuka Access Granted: {role_display} Dashboard Ready"

    html_content = render_to_string('emails/unified_welcome.html', {
        'user': user,
        'new_roles': new_roles,
    })

    email = EmailMessage(
        subject=subject,
        body=html_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    email.content_subtype = "html"

    try:
        email.send(fail_silently=False)
        return True
    except Exception as e:
        return False

def send_ecosystem_overview_email(user):
    """
    Sends the general ecosystem onboarding email.
    """
    if not user.email:
        return False

    subject = f"Welcome to the Evuka Ecosystem, {user.username}"
    html_content = render_to_string('emails/evuka_overview.html', {
        'user': user,
        'current_year': timezone.now().year,
    })

    email = EmailMessage(
        subject=subject,
        body=html_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    email.content_subtype = "html"

    try:
        email.send(fail_silently=False)
        return True
    except Exception as e:
        return False