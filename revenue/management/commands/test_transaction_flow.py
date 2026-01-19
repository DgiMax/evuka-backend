import uuid
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from unittest.mock import patch

from courses.models import Course
from payments.models import Payment
from orders.models import Order, OrderItem
from revenue.models import Wallet, Payout
from revenue.services.settlement import distribute_order_revenue
from revenue.tasks import process_single_payout
from users.models import BankingDetails

User = get_user_model()


class Command(BaseCommand):
    help = 'Simulates a full transaction cycle.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING("--- STARTING EVUKA TRANSACTION TEST ---"))

        # ------------------------------------------------------------------
        # 1. SETUP
        # ------------------------------------------------------------------
        self.stdout.write("1. Setting up users...")
        student, _ = User.objects.get_or_create(email="student@test.com", defaults={"username": "student"})

        # Get or Create Course
        course = Course.objects.first()
        if not course:
            creator, _ = User.objects.get_or_create(email="tutor@test.com", defaults={"username": "tutor"})
            course = Course.objects.create(title="Test Course", creator=creator, price=1000)

        creator = course.creator
        # Handle case where price is None
        price = course.price if course.price is not None else Decimal("1000.00")

        # Ensure Creator Wallet
        wallet, _ = Wallet.objects.get_or_create(owner_user=creator)
        initial_balance = wallet.balance

        self.stdout.write(f"   Creator: {creator.username}")
        self.stdout.write(f"   Initial Balance: {initial_balance}")

        # ------------------------------------------------------------------
        # 2. ORDER
        # ------------------------------------------------------------------
        self.stdout.write(f"\n2. Creating Order for KES {price}...")
        order = Order.objects.create(
            user=student,
            total_amount=price,
            status='pending'
        )
        # Note: OrderItem requires exactly ONE of course/event/org
        OrderItem.objects.create(order=order, course=course, price=price)
        self.stdout.write(self.style.SUCCESS(f"✓ Order #{order.order_number} Created"))

        # ------------------------------------------------------------------
        # 3. PAYMENT
        # ------------------------------------------------------------------
        self.stdout.write("\n3. Simulating Payment...")
        payment = Payment.objects.create(
            order=order,
            user=student,
            amount=price,
            provider='paystack',
            reference_code=f"TEST-{uuid.uuid4()}",
            status='successful',  # Force success
            transaction_id=f"PAY-{uuid.uuid4().hex[:8]}"
        )

        # Use your Order model's method to update status
        order.update_payment_status()
        self.stdout.write(self.style.SUCCESS("✓ Payment Confirmed"))

        # ------------------------------------------------------------------
        # 4. SETTLEMENT
        # ------------------------------------------------------------------
        self.stdout.write("\n4. Running Settlement...")
        distribute_order_revenue(order)

        wallet.refresh_from_db()

        # Calculate expected earnings (Price - 10%)
        earnings = price * Decimal("0.90")
        actual_gain = wallet.balance - initial_balance

        self.stdout.write(f"   Gain: {actual_gain} (Expected: {earnings})")

        if actual_gain == earnings:
            self.stdout.write(self.style.SUCCESS("✓ Settlement Math Correct"))
        else:
            self.stdout.write(self.style.ERROR("X Settlement Math Failed"))

        # ------------------------------------------------------------------
        # 5. PAYOUT
        # ------------------------------------------------------------------
        self.stdout.write("\n5. Testing Payout...")

        # Add bank details
        BankingDetails.objects.update_or_create(
            user=creator,
            defaults={
                "paystack_recipient_code": "RCP_TEST_MOCK",
                "bank_name": "MPESA",
                "display_number": "0700****00"
            }
        )

        if wallet.balance >= 100:
            payout = Payout.objects.create(
                wallet=wallet,
                amount=100,
                status='pending'
            )

            # Lock funds
            wallet.withdraw(100, "Test Payout")

            # Process via Mocked Celery (so we don't actually hit Paystack API)
            with patch('revenue.tasks.initiate_transfer') as mock_transfer:
                mock_transfer.return_value = {"status": True, "data": {"transfer_code": "TRF_MOCK"}}
                process_single_payout(payout.id)

            payout.refresh_from_db()

            if payout.status == 'processing':
                self.stdout.write(self.style.SUCCESS("✓ Payout Processing"))
            else:
                self.stdout.write(self.style.ERROR(f"X Payout Failed: {payout.failure_reason}"))
        else:
            self.stdout.write(self.style.WARNING("   Skipping payout (Low balance)"))

        self.stdout.write(self.style.WARNING("\n--- TEST COMPLETE ---"))