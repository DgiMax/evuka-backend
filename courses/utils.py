from books.models import Book
from courses.models import CourseBook
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.conf import settings
from weasyprint import HTML
from django.utils import timezone

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


def generate_and_send_certificate(certificate):
    user = certificate.user
    course = certificate.course

    context = {
        'user': user,
        'course': course,
        'issue_date': certificate.issue_date,
        'certificate_uid': str(certificate.certificate_uid),
    }

    html_string = render_to_string('certificates/certificate.html', context)
    pdf_file = HTML(string=html_string).write_pdf()

    subject = f"Congratulations! Your certificate for {course.title} is ready"
    email_body = render_to_string('emails/course_completed.html', context)

    email = EmailMessage(
        subject=subject,
        body=email_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    email.content_subtype = "html"

    filename = f"Certificate_{course.slug}_{user.username}.pdf"
    email.attach(filename, pdf_file, 'application/pdf')

    try:
        email.send(fail_silently=False)
        return True
    except Exception as e:
        print(f"Error sending certificate: {e}")
        return False