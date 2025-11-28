# courses/signals.py (NEW FILE)

from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Course, Enrollment



@receiver(post_save, sender=Course)
def auto_enroll_org_members(sender, instance, created, **kwargs):
    """
    Auto-enrolls active student members of the related organization
    when a new course is created or published.
    """
    from organizations.models import OrgMembership

    # 1. Only proceed if the course belongs to an organization and is published/created
    if not instance.organization:
        return

    # Check for relevant status changes (e.g., draft -> published)
    is_published = instance.status == 'published'
    is_level_required = bool(instance.org_level)

    if not is_published:
        return

    # 2. Find all active student members of this organization
    members_qs = OrgMembership.objects.filter(
        organization=instance.organization,
        is_active=True,
        role='student'
    )

    # 3. Apply level filtering before iterating
    if is_level_required:
        members_qs = members_qs.filter(level=instance.org_level)

    # Iterate and enroll
    for membership in members_qs:
        # Create enrollment for the member
        Enrollment.objects.get_or_create(
            user=membership.user,
            course=instance,
            defaults={
                'role': 'student',
                'status': 'active'
            }
        )