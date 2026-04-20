from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from urllib.parse import urlencode

@shared_task
def send_status_email(email, tenant_email, status, reference_number, notes):
    subject = f"Booking {status}"
    message = f"Your booking ({reference_number}) has been {status}."
    message += f"\nNotes: {notes}"

    send_mail(
        subject,
        message,
        tenant_email,
        [email],
        fail_silently=True,
    )

@shared_task
def send_patient_link(email, tenant_email, status, reference_number, boooking_date, token, notes=None):
    subject = f"Booking Request {status}"
    message = f"Your booking ({reference_number}) has been {status}."
    message += f"\nBooking Date: {boooking_date}"
    if notes:
        message += f"\nNotes: {notes}"
    message += f"\nTo cancel or reschedule your booking, please use the following link:"
    message += f"\n{settings.SITE_DOMAIN}/api/public/booking-status/?{urlencode({'token': token})}"

    send_mail(
        subject,
        message,
        tenant_email,
        [email],
        fail_silently=True,
    )