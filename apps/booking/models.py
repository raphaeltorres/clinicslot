import uuid
from django.db import models
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from .tasks import send_status_email, send_patient_link
from apps.booking.managers.patient_queryset import PatientQuerySet
from apps.booking.managers.patient_booking_queryset import PatientBookingQuerySet
from apps.booking.managers.booking_schedule_queryset import BookingScheduleQuerySet
from django.core.signing import TimestampSigner
from django.db.models import Q, UniqueConstraint

# Create your models here.
class Patient(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    tenant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='tenant_patients', help_text="Tenant associated with the patient")
    address = models.CharField(max_length=255, blank=True, null=True, help_text="Optional address for the patient")
    phone_number = models.CharField(max_length=20, blank=True, null=True, help_text="Optional phone number")
    date_created = models.DateTimeField(auto_now=False, auto_now_add=True, help_text="Date the record was created")
    token = models.CharField(max_length=255, blank=True, null=True, help_text="Token for secure access to request bookings")
    objects = PatientQuerySet.as_manager()

    def __str__(self):
        return f"{self.user.first_name} {self.user.last_name}"

    class Meta:
        db_table = "tenant_patient"
        get_latest_by = 'date_created'
        ordering = ['date_created']
        permissions = [
            ("patient_invite", "Can invite patients for bookings"),
            ("patient_view", "Can view patient details"),
            ("patient_edit", "Can edit patient details"),
        ]

class TenantStaff(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    tenant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='tenant_staffs', help_text="Tenant associated with the staff member")
    address = models.CharField(max_length=255, blank=True, null=True, help_text="Optional address for the staff member")
    phone_number = models.CharField(max_length=20, blank=True, null=True, help_text="Optional phone number")
    date_created = models.DateTimeField(auto_now=False, auto_now_add=True, help_text="Date the record was created")

    def __str__(self):
        return f"{self.user.first_name} {self.user.last_name}"

    class Meta:
        db_table = "tenant_staff"
        get_latest_by = 'date_created'
        ordering = ['date_created']

class BookingSchedules(models.Model):
    id = models.AutoField(primary_key=True)
    tenant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,related_name="booking_schedules")
    booking_start = models.DateTimeField(auto_now=False, auto_now_add=False, null=True, blank=True, help_text="Time the booking starts")
    booking_end = models.DateTimeField(auto_now=False, auto_now_add=False, null=True, blank=True, help_text="Time the booking ends")
    status = models.BooleanField(default=True, help_text="Indicates if the booking slot is available or not")
    is_deleted = models.BooleanField(default=False, help_text="Indicates if the booking slot is deleted")
    date_created = models.DateTimeField(auto_now=False, auto_now_add=True, help_text="Date the record was created")
    objects = BookingScheduleQuerySet.as_manager()
    
    def __str__(self):
        booking_date = f"{self.booking_start.strftime('%Y-%m-%d %H:%M')} - {self.booking_end.strftime('%H:%M')}"
        return booking_date
    
    class Meta:
        db_table = "patient_schedules"
        get_latest_by = 'date_created'
        ordering = ['date_created']
        constraints = [
            UniqueConstraint(
                fields=['booking_start', 'booking_end', 'tenant'],
                condition=Q(is_deleted=False),
                name='unique_active_booking_schedule'
            )
        ]
        indexes = [
            models.Index(fields=["status", "booking_start"]),
        ]
        permissions = [
            ("schedule_read", "Can read or view booking schedules"),
            ("schedule_write", "Can create/update booking schedules"),
            ("schedule_update", "Can confirm booking requests"),
            ("schedule_delete", "Can reject booking requests"),
        ]

class PatientBooking(models.Model):
    class StatusChoices(models.TextChoices):
        PENDING = 'pending', 'Pending'
        CANCELLED = 'cancelled', 'Cancelled'
        CONFIRMED = 'confirmed', 'Confirmed'
        RESCHEDULED = 'rescheduled', 'Rescheduled'
        DELETED = 'deleted', 'Deleted'
        REJECTED = 'rejected', 'Rejected'
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.ForeignKey(Patient, related_name='bookings', on_delete=models.CASCADE, help_text="The patient associated with this booking")
    description = models.CharField(max_length=255, blank=True, null=True, help_text="Optional description for the patient booking")
    notes = models.TextField(blank=True, null=True, help_text="Staff notes for the patient booking: confirmed, rejected, rescheduled, etc.")
    reason = models.CharField(max_length=255, blank=True, null=True, help_text="Reason for cancellation or rescheduling")
    booking_date = models.ForeignKey(BookingSchedules, related_name='patient_booking', on_delete=models.CASCADE, help_text="The booking schedule associated with this patient booking")
    token = models.CharField(max_length=255, blank=True, null=True, help_text="Token for secure access to booking details")
    date_created = models.DateTimeField(auto_now=False, auto_now_add=True, help_text="Date the record was created")
    status = models.CharField(
        max_length=20,
        db_index=True,
        choices=StatusChoices.choices,
        default=StatusChoices.PENDING
    )
    objects = PatientBookingQuerySet.as_manager()

    class Meta:
        db_table = "patient_bookings"
        get_latest_by = 'date_created'
        ordering = ['date_created']
        permissions = [
            ("blocks_read", "Can read or view booking blocks"),
            ("blocks_write", "Can create/update booking blocks"),
            ("requests_confirm", "Can confirm booking requests"),
            ("requests_reject", "Can reject booking requests"),
            ("requests_cancel", "Can cancel booking requests"),
            ("requests_reschedule", "Can reschedule booking requests"),
        ]

@receiver(models.signals.post_save, sender=PatientBooking)
def send_booking_status_email(sender, instance, created, *args, **kwargs):
    if created:
        email = instance.patient.user.email
        tenant_email = instance.patient.tenant.email
        signer = TimestampSigner()

        send_patient_link.delay(
            email=email,
            tenant_email=tenant_email,
            notes=instance.notes,
            status=instance.status,
            reference_number=str(instance.id),
            boooking_date=instance.booking_date.booking_start.strftime('%Y-%m-%d %H:%M') + " - " + instance.booking_date.booking_end.strftime('%H:%M%p'),
            token=signer.sign(str(instance.id))
        )

    if instance.status.lower() == 'confirmed':
        email = instance.patient.user.email
        tenant_email = instance.patient.tenant.email
        
        send_patient_link.delay(
            email=email,
            tenant_email=tenant_email,
            notes=instance.notes,
            status=instance.status,
            reference_number=str(instance.id),
            boooking_date=instance.booking_date.booking_start.strftime('%Y-%m-%d %H:%M') + " - " + instance.booking_date.booking_end.strftime('%H:%M%p'),
            token=instance.token
        )
    elif instance.status.lower() in ['cancelled', 'rejected']:
        send_status_email.delay(
            email=instance.patient.user.email,
            tenant_email=instance.patient.tenant.email,
            status=instance.status,
            reference_number=str(instance.id), 
            notes=instance.notes
        )