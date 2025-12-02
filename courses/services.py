from django.db.models import Count, Q
from django.utils import timezone
from .models import Enrollment, Lesson, CourseAssignment, Quiz, Certificate
from live.models import LiveLesson, LiveClass


class CourseProgressService:
    def __init__(self, user, course):
        self.user = user
        self.course = course

    def calculate_progress(self):
        """
        Aggregates all course content and calculates a percentage.
        Returns: { 'percent': float, 'detail': dict, 'is_completed': bool }
        """

        # --- 1. GET TOTALS (The Denominator) ---

        # Standard Lessons
        total_lessons = Lesson.objects.filter(module__course=self.course).count()

        # Assignments
        total_assignments = CourseAssignment.objects.filter(module__course=self.course).count()

        # Quizzes (attached to lessons in this course)
        total_quizzes = Quiz.objects.filter(lesson__module__course=self.course).count()

        # Live Lessons (Only count ones that have actually happened or are active)
        # We don't want to penalize students for future lessons that haven't happened yet.
        total_live_lessons = LiveLesson.objects.filter(
            live_class__course=self.course,
            date__lte=timezone.now().date()
        ).count()

        total_items = total_lessons + total_assignments + total_quizzes + total_live_lessons

        if total_items == 0:
            return {"percent": 0, "is_completed": False}

        # --- 2. GET COMPLETED (The Numerator) ---

        # Completed Lessons (from LessonProgress)
        completed_lessons = self.user.lesson_progress.filter(
            lesson__module__course=self.course,
            is_completed=True
        ).count()

        # Completed Assignments (Submitted)
        # Optional: Add filter(submission_status='graded') if you want strict grading
        completed_assignments = self.user.assignment_submissions.filter(
            assignment__module__course=self.course
        ).count()

        # Completed Quizzes (Passed or Attempted)
        # Here we assume 'is_completed' means they finished the attempt.
        # You could add score checks here (e.g., attempt__score__gte=50)
        completed_quizzes = Quiz.objects.filter(
            lesson__module__course=self.course,
            attempts__user=self.user,
            attempts__is_completed=True
        ).distinct().count()

        # Live Lessons "Attended"
        # Since we don't have strict attendance logs yet, we can use a heuristic:
        # If the student clicked "Join" (we can track this) or we just assume
        # simple progress for now. Ideally, you add an 'Attendance' model.
        # For this version, let's assume if it's in the past, they get credit
        # (Participation grade) OR we just track 0 for now until you add attendance.
        # Let's count Jitsi tokens generated as 'attendance' if you log them,
        # otherwise we might exclude Live Classes from the *Certificate* calculation
        # to be fair, or auto-complete them.

        # STRATEGY: Exclude Live Lessons from "Hard" Progress for now to avoid blocking certificates
        # unless you manually mark attendance.
        # We will modify the denominator to exclude live lessons for the certificate math.

        weighted_total = total_lessons + total_assignments + total_quizzes
        weighted_completed = completed_lessons + completed_assignments + completed_quizzes

        if weighted_total == 0:
            percent = 0
        else:
            percent = (weighted_completed / weighted_total) * 100

        # --- 3. CHECK CERTIFICATE ---
        is_completed = percent >= 100

        # Auto-Generate Certificate if 100%
        if is_completed:
            self._issue_certificate()

        return {
            "percent": round(percent, 2),
            "breakdown": {
                "lessons": f"{completed_lessons}/{total_lessons}",
                "assignments": f"{completed_assignments}/{total_assignments}",
                "quizzes": f"{completed_quizzes}/{total_quizzes}",
            },
            "is_completed": is_completed
        }

    def _issue_certificate(self):
        """Idempotent certificate generation"""
        Certificate.objects.get_or_create(
            user=self.user,
            course=self.course
        )