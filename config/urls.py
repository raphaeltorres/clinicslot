"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from django.urls import include
from rest_framework.routers import DefaultRouter
from apps.booking.views import PatientViewSet, BookingSchedulesViewSet, PatientBookingViewSet, TentantViewSet, ConfirmRejectViewSet
from apps.booking.views import StaffViewSet, PublicPatientBookingStatusViewSet, PublicPatientBookingRequestViewSet
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

# Initialize the router
router = DefaultRouter()
router.register(r'tenants', TentantViewSet, basename='tenants')
router.register(r'patients', PatientViewSet, basename='tenant-patients')
router.register(r'staff', StaffViewSet, basename='tenant-staff')
router.register(r'booking-schedules', BookingSchedulesViewSet, basename='booking-schedules')
router.register(r'booking-confirm-reject', ConfirmRejectViewSet, basename='booking-confirm-reject')
router.register(r'patient-bookings', PatientBookingViewSet, basename='patient-booking')

public_booking = PublicPatientBookingStatusViewSet.as_view({
    'get': 'retrieve',
    'patch': 'partial_update',
})

booking_request = PublicPatientBookingRequestViewSet.as_view({
    'post': 'create'
})

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include(router.urls)),
    path("api/auth/", include("rest_framework.urls")),
    path('api/public/booking-status/', public_booking, name='public-booking'),
    path('api/public/booking-request/', booking_request, name='public-booking-request'),
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]
