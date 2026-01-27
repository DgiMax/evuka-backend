from books.models import Book
from courses.models import CourseBook

def get_or_create_course_book(course, book_id, user):
    book = Book.objects.get(id=book_id)
    course_book, created = CourseBook.objects.get_or_create(
        course=course,
        book=book,
        defaults={
            'integration_type': 'required_purchase',
            'added_by': user
        }
    )
    return course_book