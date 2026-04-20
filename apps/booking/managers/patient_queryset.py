from django.db import models
from django.db.models import Prefetch
from django.apps import apps

class PatientQuerySet(models.QuerySet):

    def with_bookings(self):
        PatientBooking = apps.get_model('booking', 'PatientBooking')
        return self.prefetch_related(
            Prefetch(
                'bookings',
                queryset=PatientBooking.objects.only(
                    'id', 'description', 'notes', 'booking_date', 'date_created', 'status'
                ),
                to_attr="patient_bookings"
            )
        )

    def for_user(self, user):
        if user.is_superuser:
            return self

        groups = set(user.groups.values_list('name', flat=True))

        if "Staff" in groups:
            tenant_staff = getattr(user, 'tenantstaff', None)
            if not tenant_staff:
                return self.none()
            return self.filter(tenant=tenant_staff.tenant)

        if "Tenant Admin" in groups:
            return self.filter(tenant=user)

        return self.none()