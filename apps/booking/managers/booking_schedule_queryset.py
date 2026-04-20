from django.db import models

class BookingScheduleQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_deleted=False)

    def available(self):
        return self.active().filter(status=True)

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