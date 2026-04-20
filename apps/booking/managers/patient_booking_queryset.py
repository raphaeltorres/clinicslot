from django.db import models
from django.db.models import Q

class PatientBookingQuerySet(models.QuerySet):

    def with_related(self):
        return self.select_related('patient', 'patient__user', 'booking_date')
    
    def completed(self):
        return self.filter(status__in=["completed", "cancelled"])
    
    def pending(self):
        return self.filter(status__in=["pending", "rescheduled"])
  
    def for_user(self, user):
        if user.is_superuser:
            return self

        groups = set(user.groups.values_list('name', flat=True))

        if "Staff" in groups:
            tenant_staff = getattr(user, 'tenantstaff', None)
            if not tenant_staff:
                return self.none()
            return self.filter(patient__tenant=tenant_staff.tenant)

        if "Tenant Admin" in groups:
            return self.filter(patient__tenant=user)

        return self.none()