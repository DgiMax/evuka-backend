from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from courses.models import (
    Course,
    LessonProgress,
    QuizAttempt,
    AssignmentSubmission
)
from events.models import Event
from .models import LiveClass
from .services import CourseProgressService

@receiver(post_save, sender=LessonProgress)
@receiver(post_save, sender=QuizAttempt)
@receiver(post_save, sender=AssignmentSubmission)
def update_student_course_progress(sender, instance, **kwargs):
    if sender == LessonProgress:
        if not instance.is_completed:
            return
        user = instance.user
        course = instance.lesson.module.course

    elif sender == QuizAttempt:
        if not instance.is_completed:
            return
        user = instance.user
        course = instance.quiz.lesson.module.course

    elif sender == AssignmentSubmission:
        if instance.submission_status != 'graded':
            return
        user = instance.user
        course = instance.assignment.module.course

    progress_service = CourseProgressService(user, course)
    progress_service.calculate_progress()

@receiver(pre_save, sender=Course)
def track_course_status_change(sender, instance, **kwargs):
    if instance.pk:
        try:
            old_instance = Course.objects.get(pk=instance.pk)
            instance._old_status = old_instance.status
        except Course.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None

@receiver(post_save, sender=Course)
def handle_course_status_cascading(sender, instance, created, **kwargs):
    old_status = getattr(instance, '_old_status', None)
    new_status = instance.status

    if old_status == new_status:
        return

    if new_status in ['archived', 'draft']:
        live_classes = LiveClass.objects.filter(course=instance)
        live_classes.update(status=new_status)

        for live_class in live_classes:
            live_class.lessons.filter(
                start_datetime__gt=timezone.now(),
                is_cancelled=False
            ).update(is_cancelled=True)

        target_event_status = 'draft' if new_status == 'draft' else 'cancelled'

        Event.objects.filter(
            course=instance,
            start_time__gt=timezone.now(),
            event_status__in=['approved', 'scheduled', 'pending_approval']
        ).update(event_status=target_event_status)

    elif new_status == 'published' and old_status in ['archived', 'draft']:
        live_classes = LiveClass.objects.filter(
            course=instance,
            status__in=['archived', 'draft']
        )

        if live_classes.exists():
            live_classes.update(status='scheduled')

            from .services import LiveClassScheduler

            for live_class in live_classes:
                live_class.lessons.filter(
                    start_datetime__gt=timezone.now(),
                    is_cancelled=True
                ).update(is_cancelled=False)

                scheduler = LiveClassScheduler(live_class)
                scheduler.schedule_lessons(months_ahead=3)