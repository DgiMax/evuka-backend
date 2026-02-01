from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from .models import Enrollment, Lesson, CourseAssignment, Quiz, Certificate, LessonProgress
from live.models import LiveLesson


class CourseProgressService:
    """
    Calculates weighted course progress and enforces certification requirements.

    The service applies weights to different content categories:
    - Lessons: 30%
    - Assignments: 30%
    - Quizzes: 20%
    - Live Sessions: 20%

    Certification is strictly gated. A student is only marked as completed if:
    1. All core content (Lessons, Quizzes, Assignments) is 100% finished.
    2. All scheduled live classes for the course have chronologically ended.
    3. The student has attended at least 80% of the total live sessions.
    """

    def __init__(self, user, course):
        self.user = user
        self.course = course
        self.weights = {
            "lessons": 0.30,
            "quizzes": 0.20,
            "assignments": 0.30,
            "live": 0.20
        }
        self.attendance_threshold = 0.80

    def calculate_progress(self):
        now = timezone.now()

        lessons_qs = Lesson.objects.filter(module__course=self.course)
        total_lessons = lessons_qs.count()
        completed_lessons = LessonProgress.objects.filter(
            user=self.user, lesson__in=lessons_qs, is_completed=True
        ).count()
        lesson_score = (completed_lessons / total_lessons) if total_lessons > 0 else 1.0

        assignments_qs = CourseAssignment.objects.filter(module__course=self.course)
        total_assignments = assignments_qs.count()
        completed_assignments = self.user.assignment_submissions.filter(
            assignment__in=assignments_qs, submission_status='graded'
        ).count()
        assignment_score = (completed_assignments / total_assignments) if total_assignments > 0 else 1.0

        quizzes_qs = Quiz.objects.filter(lesson__module__course=self.course)
        total_quizzes = quizzes_qs.count()
        completed_quizzes = Quiz.objects.filter(
            id__in=quizzes_qs, attempts__user=self.user, attempts__is_completed=True
        ).distinct().count()
        quiz_score = (completed_quizzes / total_quizzes) if total_quizzes > 0 else 1.0

        live_lessons_qs = LiveLesson.objects.filter(live_class__course=self.course)
        total_live = live_lessons_qs.count()
        past_live_qs = live_lessons_qs.filter(end_datetime__lte=now)
        finished_live_count = past_live_qs.count()
        attended_live_count = past_live_qs.filter(attendees=self.user).count()

        attendance_rate = (attended_live_count / total_live) if total_live > 0 else 1.0
        live_score = attendance_rate

        weighted_percent = (
                                   (lesson_score * self.weights['lessons']) +
                                   (quiz_score * self.weights['quizzes']) +
                                   (assignment_score * self.weights['assignments']) +
                                   (live_score * self.weights['live'])
                           ) * 100

        all_live_finished = (finished_live_count == total_live)
        meets_attendance_threshold = (attendance_rate >= self.attendance_threshold)
        base_content_finished = (
                completed_lessons == total_lessons and
                completed_assignments == total_assignments and
                completed_quizzes == total_quizzes
        )

        is_completed = all_live_finished and meets_attendance_threshold and base_content_finished

        if is_completed:
            self._handle_completion()

        return {
            "percent": round(weighted_percent, 2),
            "is_completed": is_completed,
            "requirements": {
                "attendance_rate": round(attendance_rate * 100, 2),
                "required_attendance": self.attendance_threshold * 100,
                "all_live_sessions_finished": all_live_finished,
                "meets_attendance_threshold": meets_attendance_threshold
            },
            "breakdown": {
                "lessons": {"total": total_lessons, "completed": completed_lessons},
                "assignments": {"total": total_assignments, "completed": completed_assignments},
                "quizzes": {"total": total_quizzes, "completed": completed_quizzes},
                "live_sessions": {"total": total_live, "attended": attended_live_count}
            }
        }

    def _handle_completion(self):
        with transaction.atomic():
            enrollment = Enrollment.objects.filter(
                user=self.user, course=self.course, status='active'
            ).first()
            if enrollment:
                enrollment.status = 'completed'
                enrollment.is_completed = True
                enrollment.save()
                self._issue_certificate()

    def _issue_certificate(self):
        Certificate.objects.get_or_create(user=self.user, course=self.course)