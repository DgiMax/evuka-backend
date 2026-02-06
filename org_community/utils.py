from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings


def send_community_email(subject, template_name, context, recipient_list):
    html_content = render_to_string(f'emails/{template_name}.html', context)
    text_content = strip_tags(html_content)

    email = EmailMultiAlternatives(
        subject,
        text_content,
        settings.DEFAULT_FROM_EMAIL,
        recipient_list
    )
    email.attach_alternative(html_content, "text/html")
    email.send()


def notify_tutor_of_invitation(invitation, tutor_username):
    context = {
        'org_name': invitation.organization.name,
        'invited_by': invitation.invited_by.username,
        'role': invitation.gov_role,
        'commission': invitation.tutor_commission if invitation.is_tutor_invite else None,
        'profile_url': f"https://tutors.e-vuka.com/tutor-profile/{tutor_username}"
    }
    send_community_email(
        f"Invitation to join {invitation.organization.name}",
        'tutor_invited',
        context,
        [invitation.email]
    )


def notify_admins_of_request(join_request):
    admins = join_request.organization.memberships.filter(
        role__in=['admin', 'owner'],
        is_active=True
    ).select_related('user')

    recipient_emails = [m.user.email for m in admins if m.user.email]
    if not recipient_emails:
        return

    context = {
        'applicant_name': join_request.user.username,
        'org_name': join_request.organization.name,
        'desired_role': join_request.desired_role,
        'message': join_request.message,
        'manage_url': f"https://tutors.e-vuka.com/{join_request.organization.slug}"
    }
    send_community_email(
        f"New Join Request: {join_request.user.username}",
        'admin_new_request',
        context,
        recipient_emails
    )


def notify_request_approved(join_request):
    context = {
        'org_name': join_request.organization.name,
        'org_url': f"https://tutors.e-vuka.com/{join_request.organization.slug}"
    }
    send_community_email(
        f"Request Approved: Welcome to {join_request.organization.name}",
        'request_approved',
        context,
        [join_request.user.email]
    )


def notify_counter_offer(invitation, actor_name):
    admins = invitation.organization.memberships.filter(role__in=['admin', 'owner'], is_active=True)
    recipient_emails = [m.user.email for m in admins if m.user.email]
    if not recipient_emails:
        return

    context = {
        'org_name': invitation.organization.name,
        'actor_name': actor_name,
        'new_commission': invitation.tutor_commission,
        'manage_url': f"https://tutors.e-vuka.com/{invitation.organization.slug}"
    }
    send_community_email(
        f"Counter Offer from {actor_name}",
        'invite_countered',
        context,
        recipient_emails
    )


def notify_rejection(instance, actor_name, is_invitation=True):
    if is_invitation:
        owner = instance.organization.memberships.filter(role='owner').first()
        recipients = [owner.user.email] if owner else []
        subject = f"Invitation Declined: {actor_name}"
        template = 'invite_rejected_by_tutor'
        link = f"https://tutors.e-vuka.com/{instance.organization.slug}"
    else:
        recipients = [instance.user.email]
        subject = f"Update regarding your request to {instance.organization.name}"
        template = 'request_rejected_by_org'
        link = f"https://tutors.e-vuka.com/discover"

    if recipients:
        context = {
            'org_name': instance.organization.name,
            'actor_name': actor_name,
            'action_url': link
        }
        send_community_email(subject, template, context, recipients)


def notify_invitation_accepted(invitation, tutor_username):
    owner = invitation.organization.memberships.filter(role='owner').first()
    recipients = [owner.user.email] if owner else []
    if not recipients:
        return

    context = {
        'tutor_username': tutor_username,
        'org_name': invitation.organization.name,
        'org_url': f"https://tutors.e-vuka.com/{invitation.organization.slug}"
    }
    send_community_email(
        f"{tutor_username} has joined {invitation.organization.name}",
        'invitation_accepted',
        context,
        recipients
    )