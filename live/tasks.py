import logging
from celery import shared_task
from django.utils import timezone
from .models import LiveClass
from .services import LiveClassScheduler

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3)
def update_single_class_schedule(self, live_class_id):
    """
    Worker Task: Updates the schedule for a specific class.
    Retries automatically on database locks or transient errors.
    """
    try:
        live_class = LiveClass.objects.get(id=live_class_id)
        scheduler = LiveClassScheduler(live_class)
        # Ensure the next 30 days are populated
        scheduler.schedule_lessons(months_ahead=1)
        return f"Updated schedule for {live_class.title}"
    except LiveClass.DoesNotExist:
        logger.error(f"LiveClass {live_class_id} not found.")
    except Exception as exc:
        logger.error(f"Error updating class {live_class_id}: {exc}")
        raise self.retry(exc=exc, countdown=60)

@shared_task
def trigger_daily_schedule_updates():
    """
    Master Task: Finds all active recurring classes and dispatches
    individual update tasks for them.
    """
    active_classes = LiveClass.objects.filter(
        status='scheduled',
        recurrence_type='weekly'
    ).values_list('id', flat=True)

    count = 0
    for class_id in active_classes:
        update_single_class_schedule.delay(class_id)
        count += 1

    return f"Dispatched update tasks for {count} classes."