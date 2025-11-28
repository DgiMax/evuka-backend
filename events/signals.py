from django.db.models.signals import post_save
from django.dispatch import receiver
from courses.models import Course
from .models import Event, EventRegistration


@receiver(post_save, sender=Course)
def auto_assign_organizer(sender, instance, created, **kwargs):
    """
    Ensure organizer defaults to course.creator when events are created.
    """
    if created:
        # nothing to auto-create here yet, but this ensures
        # events linked to this course will inherit course.creator
        pass


@receiver(post_save, sender=Event)
def auto_register_org_members(sender, instance, created, **kwargs):
    """
    Automatically registers active student members of the related organization
    when a new event is created or its status changes to approved/scheduled.
    """
    from organizations.models import OrgMembership

    # 1. Only proceed if the event is tied to an organization course
    if not instance.course or not instance.course.organization:
        return

    # 2. Check if the event is ready for public access (approved/scheduled) and is upcoming
    is_ready_for_registration = instance.event_status in ['approved', 'scheduled']
    if not is_ready_for_registration:
        return

    organization = instance.course.organization

    # 3. Find all active student members of this organization
    members_qs = OrgMembership.objects.filter(
        organization=organization,
        is_active=True,
        role='student'
    )

    # 4. Filter members based on Event's 'who_can_join' setting (if needed)
    # The simplest logic is to check if the user is an active org member (already done).
    # If you need more granular checks (e.g., only Course Students), you'd add filters here.

    # Check if the course linked to the event has a level, and filter members by that level
    course_level = instance.course.org_level
    if course_level:
        members_qs = members_qs.filter(level=course_level)

    # 5. Iterate and register
    for membership in members_qs:
        # Create registration for the member (get_or_create prevents duplicates)
        EventRegistration.objects.get_or_create(
            user=membership.user,
            event=instance,
            defaults={
                'status': 'registered',
                'payment_status': 'free'
            }
        )
