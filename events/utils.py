import base64
from django.template.loader import render_to_string
from weasyprint import HTML
from django.core.mail import EmailMessage
from django.conf import settings
import requests


def generate_event_ticket_pdf(registration):
    event = registration.event
    user = registration.user
    qr_base64 = ""

    if registration.ticket_qr_code:
        try:
            try:
                img_data = registration.ticket_qr_code.read()
            except Exception:
                url = registration.ticket_qr_code.url
                if not url.startswith('http'):
                    url = f"{settings.BUNNY_PULL_ZONE_URL}/{url.lstrip('/')}"

                response = requests.get(url)
                if response.status_code == 200:
                    img_data = response.content
                else:
                    img_data = None

            if img_data:
                encoded_string = base64.b64encode(img_data).decode('utf-8')
                qr_base64 = f"data:image/png;base64,{encoded_string}"
        except Exception as e:
            print(f"CRITICAL ERROR: Failed to process QR code from storage: {e}")

    context = {
        'event': event,
        'user': user,
        'registration': registration,
        'ticket_id': str(registration.ticket_id),
        'qr_code_base64': qr_base64,
    }

    html_content = render_to_string('events/ticket_template.html', context)

    html = HTML(string=html_content, base_url=settings.BASE_DIR)
    return html.write_pdf()


def send_event_confirmation_email(registration):
    event = registration.event
    user = registration.user

    subject = f"Confirmed: {event.title} Registration"
    html_content = render_to_string('emails/event_confirmation.html', {
        'user': user,
        'event': event,
        'registration': registration,
    })

    email = EmailMessage(
        subject=subject,
        body=html_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    email.content_subtype = "html"

    if event.event_type in ['physical', 'hybrid']:
        pdf_content = generate_event_ticket_pdf(registration)
        filename = f"Ticket_{event.slug}.pdf"
        email.attach(filename, pdf_content, 'application/pdf')

    email.send(fail_silently=False)