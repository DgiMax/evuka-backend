from courses.models import Enrollment
from events.models import EventRegistration
from organizations.models import OrgMembership
# --- NEW IMPORTS ---
from books.models import BookAccess
from revenue.services import distribute_order_revenue
# -------------------
from .models import update_order_payment_status


def handle_successful_payment(payment):
    """
    Centralized logic to grant access (enrollments, events, memberships, books)
    after a payment is confirmed (whether Free or Paid).
    """
    # 1. Update the Order status to 'paid'
    update_order_payment_status(payment.order)

    order = payment.order
    # Safety check: Ensure metadata is a dict before accessing .get()
    metadata = payment.metadata or {}
    membership_id = metadata.get('membership_id')
    reference = payment.reference_code

    action_performed = []

    # 2. Iterate through items to grant access
    for item in order.items.all():

        # --- A. COURSE ENROLLMENT ---
        if item.course:
            Enrollment.objects.get_or_create(
                user=order.user,
                course=item.course,
                defaults={'status': 'active', 'role': 'student'}
            )
            action_performed.append(f"Course '{item.course.title}' enrollment")

        # --- B. EVENT REGISTRATION ---
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
            action_performed.append(f"Event '{item.event.title}' registration")

        # --- C. BOOK ACCESS (New) ---
        elif item.book:
            BookAccess.objects.get_or_create(
                user=order.user,
                book=item.book,
                defaults={'source': 'purchase'}
            )
            action_performed.append(f"Book '{item.book.title}' access")

        # --- D. ORGANIZATION MEMBERSHIP ---
        elif item.organization and membership_id:
            try:
                # We filter by ID and Org to ensure security
                membership = OrgMembership.objects.get(
                    id=membership_id,
                    organization=item.organization
                )
                membership.activate_membership()
                action_performed.append(f"Organization '{item.organization.name}' membership activation")

            except OrgMembership.DoesNotExist:
                action_performed.append(
                    f"Organization '{item.organization.name}' membership activation failed (record missing)"
                )

    # 3. TRIGGER REVENUE DISTRIBUTION (The Missing Link)
    # This calls the "Accountant" to split the money to wallets
    distribute_order_revenue(order)

    # 4. Construct the success message
    if action_performed:
        success_message = "Payment verified. " + ", ".join(action_performed) + "."
    else:
        success_message = "Payment verified, but no specific enrollment action was performed."

    return success_message