from django.core.management.base import BaseCommand
from live.tasks import trigger_daily_schedule_updates


class Command(BaseCommand):
    help = 'Manually triggers the Celery task to regenerate future lessons.'

    def handle(self, *args, **options):
        self.stdout.write("Triggering daily schedule update task...")

        # We call the logic directly or trigger the async task
        # Triggering async is safer to prevent memory leaks in the CLI process
        task = trigger_daily_schedule_updates.delay()

        self.stdout.write(self.style.SUCCESS(f"Task dispatched. ID: {task.id}"))