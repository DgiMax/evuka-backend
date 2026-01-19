import pytz
from datetime import datetime, timedelta
from django.utils import timezone
from .models import LiveLesson


class LiveClassScheduler:
    def __init__(self, live_class):
        self.live_class = live_class
        self.tz = pytz.timezone(live_class.timezone)

    def schedule_lessons(self, months_ahead=3):
        if self.live_class.recurrence_type == "none":
            self._schedule_one_time()
        elif self.live_class.recurrence_type == "weekly":
            self._schedule_recurring(months_ahead)

    def update_schedule(self):
        now_utc = timezone.now()
        self.live_class.lessons.filter(
            start_datetime__gt=now_utc
        ).delete()
        self.schedule_lessons()

    def _schedule_one_time(self):
        if not self.live_class.single_session_start:
            return

        local_start = datetime.combine(
            self.live_class.start_date,
            self.live_class.single_session_start
        )
        local_dt_aware = self.tz.localize(local_start)

        utc_start = local_dt_aware.astimezone(pytz.UTC)
        utc_end = utc_start + timedelta(minutes=self.live_class.duration_minutes)

        LiveLesson.objects.get_or_create(
            live_class=self.live_class,
            start_datetime=utc_start,
            defaults={
                'title': self.live_class.title,
                'end_datetime': utc_end
            }
        )

    def _schedule_recurring(self, months_ahead=1):
        recurrence_map = self.live_class.recurrence_days
        if not recurrence_map:
            return

        start_date = self.live_class.start_date
        min_date = max(start_date, timezone.now().date())

        limit_date = min_date + timedelta(days=30 * months_ahead)
        if self.live_class.end_date:
            limit_date = min(limit_date, self.live_class.end_date)

        current_date = min_date

        while current_date <= limit_date:
            weekday_name = current_date.strftime("%A")

            if weekday_name in recurrence_map:
                time_str = recurrence_map[weekday_name]
                try:
                    lesson_time = datetime.strptime(time_str, "%H:%M").time()

                    local_dt = datetime.combine(current_date, lesson_time)
                    local_dt_aware = self.tz.localize(local_dt)

                    utc_start = local_dt_aware.astimezone(pytz.UTC)
                    utc_end = utc_start + timedelta(minutes=self.live_class.duration_minutes)

                    LiveLesson.objects.get_or_create(
                        live_class=self.live_class,
                        start_datetime=utc_start,
                        defaults={
                            'title': f"{self.live_class.title} - {weekday_name}",
                            'end_datetime': utc_end
                        }
                    )
                except ValueError:
                    pass

            current_date += timedelta(days=1)