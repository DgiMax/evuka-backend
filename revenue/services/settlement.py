from decimal import Decimal
from django.db import transaction
from revenue.models import Wallet, Transaction
from organizations.models import Organization

PLATFORM_FEE_PERCENT = Decimal("0.10")


def distribute_order_revenue(order):
    """
    Splits money between Sellers (Tutors/Orgs) and the Platform.
    Idempotent: Checks if transactions already exist for this order to prevent double-payment.
    """
    # 1. Idempotency Check: Have we already paid out for this order?
    if getattr(order, 'is_distributed', False):
        return

    # Secondary check on transaction history
    if Transaction.objects.filter(description__contains=f"Order #{order.order_number}").exists():
        return

    # Get System Wallet (Safely create if missing to prevent crashes)
    try:
        platform_wallet = Wallet.get_system_wallet()
    except Wallet.DoesNotExist:
        # Create system org and wallet if this is the first ever transaction
        sys_org, _ = Organization.objects.get_or_create(
            name="Evuka Platform",
            slug="evuka-platform",
            defaults={'status': 'approved'}
        )
        platform_wallet, _ = Wallet.objects.get_or_create(owner_org=sys_org)

    with transaction.atomic():
        for item in order.items.all():
            seller_wallet = None
            product_desc = ""

            # 2. Identify Seller Wallet (Strict Ownership Rules)

            # --- A. COURSE LOGIC ---
            if item.course:
                if item.course.organization:
                    # RULE: Org Course -> Money goes to Organization
                    seller_wallet, _ = Wallet.objects.get_or_create(owner_org=item.course.organization)
                    product_desc = f"Course: {item.course.title} (Org Sale)"
                else:
                    # RULE: Independent Course -> Money goes to Creator
                    seller_wallet, _ = Wallet.objects.get_or_create(owner_user=item.course.creator)
                    product_desc = f"Course: {item.course.title}"

            # --- B. EVENT LOGIC ---
            elif item.event:
                # Events are children of Courses. We must check the Parent Course.
                # Use getattr to prevent crashes if event is somehow orphaned
                parent_course = getattr(item.event, 'course', None)
                course_org = parent_course.organization if parent_course else None

                if course_org:
                    # RULE: Org Event -> Money goes to Organization
                    seller_wallet, _ = Wallet.objects.get_or_create(owner_org=course_org)
                    product_desc = f"Event: {item.event.title} (Org Event)"
                else:
                    # RULE: Independent Event -> Money goes to Organizer
                    organizer = item.event.organizer
                    if not organizer and parent_course:
                        organizer = parent_course.creator  # Fallback to course creator

                    if organizer:
                        seller_wallet, _ = Wallet.objects.get_or_create(owner_user=organizer)
                        product_desc = f"Event: {item.event.title}"

            # --- C. MEMBERSHIP LOGIC ---
            elif item.organization:
                seller_wallet, _ = Wallet.objects.get_or_create(owner_org=item.organization)
                product_desc = f"Payment to: {item.organization.name}"

            # --- D. BOOK LOGIC (Added) ---
            elif item.book:
                # Books pay the creator directly
                seller_wallet, _ = Wallet.objects.get_or_create(owner_user=item.book.created_by)
                product_desc = f"Book: {item.book.title}"

            # If no wallet found (e.g. data error), skip item
            if not seller_wallet:
                continue

            # 3. Calculate Splits
            gross_amount = Decimal(str(item.price))
            commission = gross_amount * PLATFORM_FEE_PERCENT
            net_earnings = gross_amount - commission

            # 4. Execute Transfers
            # We add source_item=item to link the transaction to the specific product
            seller_wallet.deposit(
                amount=net_earnings,
                description=f"Earnings from {product_desc} (Order #{order.order_number})",
                tx_type="credit",
                source_item=item
            )

            platform_wallet.deposit(
                amount=commission,
                description=f"Commission from {product_desc} (Order #{order.order_number})",
                tx_type="fee",
                source_item=item
            )

        # 5. Mark Order as Distributed
        # This flag is critical to prevent re-running this function on the same order
        order.is_distributed = True
        order.save()