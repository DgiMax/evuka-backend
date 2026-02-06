from celery import shared_task
from django.contrib.auth import get_user_model
from users.utils.welcomer import send_ecosystem_overview_email, send_unified_welcome_email

User = get_user_model()


@shared_task(bind=True, max_retries=3)
def send_ecosystem_overview_task(self, user_id):
    """
    Background task to send the ecosystem overview.
    Retries up to 3 times on failure.
    """
    try:
        user = User.objects.get(pk=user_id)
        if not send_ecosystem_overview_email(user):
            raise Exception("Email delivery failed")
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            User.objects.filter(pk=user_id).update(ecosystem_email_sent=False)
        raise self.retry(exc=exc, countdown=60)


@shared_task(bind=True, max_retries=3)
def send_unified_welcome_task(self, user_id, roles):
    """
    Background task to send role-specific welcomes.
    """
    try:
        user = User.objects.get(pk=user_id)
        if not send_unified_welcome_email(user, roles):
            raise Exception("Email delivery failed")

        updated_roles_dict = {**user.roles_welcome_sent}
        for role in roles:
            updated_roles_dict[role] = True
        User.objects.filter(pk=user_id).update(roles_welcome_sent=updated_roles_dict)

    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)