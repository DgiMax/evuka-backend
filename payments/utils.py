from courses.models import Enrollment
from events.models import EventRegistration
from books.models import BookAccess
from organizations.models import OrgMembership
from revenue.services.settlement import distribute_order_revenue
from .models import update_order_payment_status

def handle_successful_payment(payment):
    update_order_payment_status(payment.order)
    order = payment.order
    metadata = payment.metadata or {}
    membership_id = metadata.get('membership_id')
    reference = payment.reference_code

    actions = []

    for item in order.items.all():
        if item.course:
            Enrollment.objects.get_or_create(
                user=order.user,
                course=item.course,
                defaults={'status': 'active', 'role': 'student'}
            )
            actions.append(f"Course '{item.course.title}'")

        elif item.event:
            EventRegistration.objects.get_or_create(
                user=order.user,
                event=item.event,
                defaults={
                    'status': 'registered',
                    'payment_status': 'paid',
                    'payment_reference': reference
                }
            )
            actions.append(f"Event '{item.event.title}'")

        elif item.book:
            BookAccess.objects.get_or_create(
                user=order.user,
                book=item.book,
                defaults={'source': 'purchase'}
            )
            actions.append(f"Book '{item.book.title}'")

        elif item.organization and membership_id:
            try:
                membership = OrgMembership.objects.get(id=membership_id, organization=item.organization)
                membership.activate_membership()
                actions.append(f"Membership '{item.organization.name}'")
            except OrgMembership.DoesNotExist:
                pass

    distribute_order_revenue(order)
    return f"Access granted: {', '.join(actions)}" if actions else "Payment verified."

def get_redirect_context(order):
    first_item = order.items.first()
    if first_item and first_item.organization:
        return {"type": "organization", "org_slug": first_item.organization.slug}
    return {"type": "global"}