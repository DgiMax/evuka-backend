from django.core.management.base import BaseCommand
from django.utils import timezone
from live.models import LiveClass


class Command(BaseCommand):
    help = 'Generates upcoming lessons for ongoing live classes (maintains a 30-day buffer)'

    def handle(self, *args, **kwargs):
        today = timezone.now().date()

        active_classes = LiveClass.objects.filter(
            status__in=['scheduled', 'ongoing'],
            recurrence_type='weekly'
        )

        self.stdout.write(f"Checking {active_classes.count()} active classes for lesson generation...")

        count = 0
        for live_class in active_classes:
            if live_class.end_date and live_class.end_date < today:
                live_class.status = 'completed'
                live_class.save()
                continue

            live_class.generate_lessons_batch(start_from=today, days_ahead=30)
            count += 1

        self.stdout.write(self.style.SUCCESS(f"Successfully processed {count} classes."))