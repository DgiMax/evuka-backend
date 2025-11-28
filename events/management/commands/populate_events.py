import time

from django.core.management.base import BaseCommand
from django.utils import timezone
from courses.models import Course
from django.contrib.auth import get_user_model
from events.models import Event, EventLearningObjective, EventAgenda, EventRule
from django.utils.text import slugify
import datetime

User = get_user_model()


class Command(BaseCommand):
    help = "Populate 2 sample events with full details for testing"

    def handle(self, *args, **options):
        # --- Fetch a course to link events to ---
        course = Course.objects.first()
        if not course:
            self.stdout.write(self.style.ERROR("No course found! Please create a course first."))
            return

        # --- Fetch an organizer ---
        organizer = User.objects.filter(is_staff=True).first()
        if not organizer:
            self.stdout.write(self.style.ERROR("No staff user found! Please create a staff user first."))
            return

        now = timezone.now()

        # --- Utility function to generate unique slug ---
        def unique_slug(title):
            base_slug = slugify(title)
            timestamp = int(time.time())
            return f"{base_slug}-{timestamp}"

        # --- Event 1 ---
        event1_slug = unique_slug("Advanced Python Workshop")
        event1, created = Event.objects.get_or_create(
            slug=event1_slug,
            defaults={
                "course": course,
                "title": "Advanced Python Workshop",
                "overview": "Deep dive into advanced Python concepts.",
                "description": "<p>Learn advanced Python features including decorators, metaclasses, and async programming.</p>",
                "event_type": "online",
                "meeting_link": "https://zoom.us/j/1234567890",
                "start_time": now + datetime.timedelta(days=5),
                "end_time": now + datetime.timedelta(days=5, hours=3),
                "timezone": "Africa/Nairobi",
                "who_can_join": "Open to all Python enthusiasts",
                "is_paid": True,
                "price": 5000,
                "currency": "KES",
                "max_attendees": 50,
                "registration_open": True,
                "registration_deadline": now + datetime.timedelta(days=4),
                "organizer": organizer
            }
        )

        if created:
            # Learning objectives
            EventLearningObjective.objects.bulk_create([
                EventLearningObjective(event=event1, text="Understand decorators and context managers"),
                EventLearningObjective(event=event1, text="Master asynchronous programming"),
                EventLearningObjective(event=event1, text="Learn best practices for Python projects"),
            ])
            # Agenda
            EventAgenda.objects.bulk_create([
                EventAgenda(event=event1, order=1, time="10:00 AM", title="Introduction", description="Overview of workshop and setup."),
                EventAgenda(event=event1, order=2, time="10:30 AM", title="Decorators Deep Dive", description="Learn how to create and use decorators."),
                EventAgenda(event=event1, order=3, time="11:30 AM", title="Async Programming", description="Understanding async/await in Python."),
                EventAgenda(event=event1, order=4, time="12:30 PM", title="Q&A", description="Answering participant questions."),
            ])
            # Rules
            EventRule.objects.bulk_create([
                EventRule(event=event1, title="Respect Others", text="Be courteous and respectful during the workshop."),
                EventRule(event=event1, title="Attendance", text="Please attend on time and stay for the full session."),
                EventRule(event=event1, title="Recording", text="Do not record the session without permission."),
            ])
            self.stdout.write(self.style.SUCCESS(f"Created event: {event1.title}"))
        else:
            self.stdout.write(self.style.WARNING(f"Event already exists: {event1.title}"))

        # --- Event 2 ---
        event2_slug = unique_slug("Data Science Bootcamp")
        event2, created = Event.objects.get_or_create(
            slug=event2_slug,
            defaults={
                "course": course,
                "title": "Data Science Bootcamp",
                "overview": "Hands-on bootcamp on Data Science tools and techniques.",
                "description": "<p>Learn data preprocessing, visualization, machine learning, and deployment in a practical environment.</p>",
                "event_type": "physical",
                "location": "Tech Hub, Nairobi",
                "start_time": now + datetime.timedelta(days=10),
                "end_time": now + datetime.timedelta(days=10, hours=8),
                "timezone": "Africa/Nairobi",
                "who_can_join": "Beginners and intermediates in data science",
                "is_paid": False,
                "max_attendees": 30,
                "registration_open": True,
                "registration_deadline": now + datetime.timedelta(days=9),
                "organizer": organizer
            }
        )

        if created:
            # Learning objectives
            EventLearningObjective.objects.bulk_create([
                EventLearningObjective(event=event2, text="Understand data cleaning and preprocessing"),
                EventLearningObjective(event=event2, text="Perform data visualization with Python"),
                EventLearningObjective(event=event2, text="Build and evaluate machine learning models"),
            ])
            # Agenda
            EventAgenda.objects.bulk_create([
                EventAgenda(event=event2, order=1, time="09:00 AM", title="Introduction & Setup", description="Welcome and install required tools."),
                EventAgenda(event=event2, order=2, time="10:00 AM", title="Data Preprocessing", description="Cleaning and transforming data."),
                EventAgenda(event=event2, order=3, time="11:30 AM", title="Visualization", description="Creating plots with matplotlib and seaborn."),
                EventAgenda(event=event2, order=4, time="01:00 PM", title="Lunch Break", description=""),
                EventAgenda(event=event2, order=5, time="02:00 PM", title="Machine Learning Basics", description="Training models and evaluating performance."),
                EventAgenda(event=event2, order=6, time="04:30 PM", title="Wrap-Up & Q&A", description="Final questions and closing remarks."),
            ])
            # Rules
            EventRule.objects.bulk_create([
                EventRule(event=event2, title="Punctuality", text="Arrive on time to not miss sessions."),
                EventRule(event=event2, title="Laptop Requirement", text="Bring your laptop with Python installed."),
                EventRule(event=event2, title="Participation", text="Active participation is encouraged."),
            ])
            self.stdout.write(self.style.SUCCESS(f"Created event: {event2.title}"))
        else:
            self.stdout.write(self.style.WARNING(f"Event already exists: {event2.title}"))

        self.stdout.write(self.style.SUCCESS("Successfully populated 2 events with full details."))
