from django.db import transaction
from django.db.models import Avg, Count
from django.utils import timezone
from .models import Enrollment, Lesson, CourseAssignment, Quiz, Certificate, LessonProgress


class CourseProgressService:
    def __init__(self, user, course):
        self.user = user
        self.course = course

    def calculate_progress(self):
        lessons_qs = Lesson.objects.filter(module__course=self.course)
        total_lessons = lessons_qs.count()
        completed_lessons = LessonProgress.objects.filter(
            user=self.user,
            lesson__in=lessons_qs,
            is_completed=True
        ).count()

        assignments_qs = CourseAssignment.objects.filter(module__course=self.course)
        total_assignments = assignments_qs.count()
        completed_assignments = self.user.assignment_submissions.filter(
            assignment__in=assignments_qs,
            submission_status='graded'
        ).count()

        quizzes_qs = Quiz.objects.filter(lesson__module__course=self.course)
        total_quizzes = quizzes_qs.count()
        completed_quizzes = Quiz.objects.filter(
            id__in=quizzes_qs,
            attempts__user=self.user,
            attempts__is_completed=True
        ).distinct().count()

        total_items = total_lessons + total_assignments + total_quizzes
        completed_items = completed_lessons + completed_assignments + completed_quizzes

        if total_items == 0:
            return {"percent": 0, "is_completed": False}

        percent = (completed_items / total_items) * 100
        is_completed = (completed_lessons == total_lessons and
                        completed_assignments == total_assignments and
                        completed_quizzes == total_quizzes)

        if is_completed:
            self._handle_completion()

        return {
            "percent": round(percent, 2),
            "is_completed": is_completed,
            "breakdown": {
                "lessons": {"total": total_lessons, "completed": completed_lessons},
                "assignments": {"total": total_assignments, "completed": completed_assignments},
                "quizzes": {"total": total_quizzes, "completed": completed_quizzes}
            }
        }

    def _handle_completion(self):
        with transaction.atomic():
            enrollment = Enrollment.objects.filter(
                user=self.user,
                course=self.course,
                status='active'
            ).first()

            if enrollment:
                enrollment.status = 'completed'
                enrollment.is_completed = True
                enrollment.save()

                self._issue_certificate()

    def _issue_certificate(self):
        Certificate.objects.get_or_create(
            user=self.user,
            course=self.course
        )