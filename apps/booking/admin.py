from django.contrib import admin
from django.contrib.auth.models import Permission
from .models import Patient, PatientBooking, TenantStaff, BookingSchedules

@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ['name', 'codename', 'content_type']
    search_fields = ['name', 'codename']
    list_filter = ['content_type']

@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ['user', 'tenant']
    search_fields = ['user__username', 'user__first_name', 'user__last_name', 'tenant__username']
    list_filter = ['tenant']

@admin.register(PatientBooking)
class PatientBookingAdmin(admin.ModelAdmin):
    list_display = ['patient', 'booking_date', 'status', 'date_created']
    search_fields = ['patient__user__username', 'patient__user__first_name', 'patient__user__last_name']
    list_filter = ['status', 'patient__tenant__username']

@admin.register(TenantStaff)
class TenantStaffAdmin(admin.ModelAdmin):
    list_display = ['user', 'tenant']
    search_fields = ['user__username', 'user__first_name', 'user__last_name', 'tenant__username']
    list_filter = ['tenant']

@admin.register(BookingSchedules)
class BookingSchedulesAdmin(admin.ModelAdmin):
    list_display = ['id', 'tenant__username', 'booking_start', 'booking_end', 'status', 'date_created', 'is_deleted']
    search_fields = ['status']
    list_filter = ['status', 'booking_start', 'is_deleted']