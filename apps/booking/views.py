from urllib import request

from django.shortcuts import render
from rest_framework import mixins, viewsets, status
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from .serializers import PatientSerializer, StaffSerializer, UserSerializer, UserUpdateSerializer, PatientUpdateSerializer, PublicPatientBookingCreateSerializer
from .serializers import ConfirmRejectSerializer, BookingSchedulesSerializer, PatientBookingSerializer, PublicPatientBookingUpdateSerializer
from .models import Patient, TenantStaff, BookingSchedules, PatientBooking
from django.contrib.auth.models import User
from django.core.signing import TimestampSigner,BadSignature, SignatureExpired
from rest_framework.response import Response
from .custom_permission import ClinicPermission, SuperUserPerimission
from rest_framework.exceptions import ValidationError
from rest_framework.exceptions import NotFound
from drf_spectacular.utils import extend_schema
from django.db import transaction

@extend_schema(
    tags=["Tenant"],
    summary="List tenants",
    description="Retrieve all tenant admin users",
)
class TentantViewSet(
        mixins.ListModelMixin,
        mixins.CreateModelMixin, 
        mixins.UpdateModelMixin,
        mixins.RetrieveModelMixin, 
        viewsets.GenericViewSet
    ):
    """
    ViewSet for managing User instances.
    Supports listing, creating, updating, retrieving, and deleting users.
    """
    queryset = User.objects.filter(groups__name="Tenant Admin")
    serializer_class = UserSerializer
    permission_classes = [SuperUserPerimission]

    @extend_schema(summary="Retrieve tenant details")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(summary="Create tenant")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @extend_schema(summary="Update tenant")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)


@extend_schema(tags=["Staff"])
class StaffViewSet(
        mixins.ListModelMixin,
        mixins.CreateModelMixin, 
        mixins.UpdateModelMixin,
        mixins.RetrieveModelMixin, 
        viewsets.GenericViewSet
    ):
    """
    ViewSet for managing Staff instances.
    Supports listing, creating, updating, retrieving, and deleting staff members.
    """
    queryset = TenantStaff.objects.none()
    serializer_class = UserUpdateSerializer
    permission_classes = [IsAuthenticated, ClinicPermission]

    def get_serializer_class(self):
        if self.action == 'create':
            return StaffSerializer  
        elif self.action in ['update', 'partial_update']:
            return UserUpdateSerializer  
        return UserUpdateSerializer

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return TenantStaff.objects.all()
        elif user.groups.filter(name="Tenant Admin").exists():
            return TenantStaff.objects.filter(tenant=user)
        return TenantStaff.objects.none()
    
    @extend_schema(
        summary="List staff",
        responses=UserUpdateSerializer(many=True)
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        summary="Create staff",
        request=StaffSerializer,
        responses=StaffSerializer
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @extend_schema(
        summary="Update staff",
        request=UserUpdateSerializer,
        responses=UserUpdateSerializer
    )
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)


@extend_schema(tags=["Patient"])
class PatientViewSet(
        mixins.ListModelMixin,
        mixins.CreateModelMixin, 
        mixins.UpdateModelMixin,
        mixins.RetrieveModelMixin, 
        viewsets.GenericViewSet
    ):
    """
    ViewSet for managing Patient instances.
    Supports listing, creating, updating, retrieving, and deleting patients.
    """
    queryset = Patient.objects.none()
    serializer_class = PatientSerializer
    permission_classes = [IsAuthenticated, ClinicPermission]

    permission_map = {
        "list": "booking.patient_view",
        "retrieve": "booking.patient_view",
        "create": "booking.patient_invite",
        "update": "booking.patient_edit",
        "partial_update": "booking.patient_edit",
    }
    
    def get_queryset(self):
        return Patient.objects.for_user(self.request.user).with_bookings()
    
    def get_serializer_class(self):
        if self.action == 'create':
            return PatientSerializer  
        elif self.action in ['update', 'partial_update']:
            return PatientUpdateSerializer  
        return PatientSerializer
    
    @extend_schema(
        summary="List patients",
        description="Retrieve patients with booking info",
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @extend_schema(
        summary="Create patient",
        request=PatientSerializer,
        responses=PatientSerializer,
        description="Invite a patient by creating a patient record. An email with booking instructions will be sent to the patient."
    )
    def create(self, request):
        serializer = PatientSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        else:
            #return error if data didn't passed the serialization.
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @extend_schema(
        summary="Update patient",
        request=PatientUpdateSerializer,
        responses=PatientUpdateSerializer,
        description="Update a patient's information."
    )
    # def update(self, request, *args, **kwargs):
    #     instance = self.get_object()
    #     serializer = self.get_serializer(instance, data=request.data, context={'request': request})
    #     if serializer.is_valid():
    #         serializer.save()
    #         return Response(serializer.data)
    #     else:
    #         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def update(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        instance = queryset.get(pk=kwargs["pk"])
        serializer = PatientUpdateSerializer(instance, data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        return Response(serializer.data)


@extend_schema(tags=["Booking"])
class PatientBookingViewSet(
        mixins.ListModelMixin,
        mixins.CreateModelMixin, 
        mixins.UpdateModelMixin,
        mixins.RetrieveModelMixin, 
        viewsets.GenericViewSet
    ):
    """
    ViewSet for managing PatientBooking instances.
    Supports listing, creating, updating, retrieving, and deleting patient bookings.
    """
    queryset = PatientBooking.objects.none()
    serializer_class = PatientBookingSerializer
    permission_classes = [IsAuthenticated, ClinicPermission]

    permission_map = {
        "retrieve": "booking.blocks_read",
        "list": "booking.blocks_read",
        "create": "booking.blocks_write",
        "update": [
            "booking.requests_confirm",
            "booking.requests_reject",
        ],
        "partial_update": [
            "booking.requests_confirm",
            "booking.requests_reject",
        ],
    }

    def get_queryset(self):
        return PatientBooking.objects.for_user(self.request.user).with_related()
    
    @extend_schema(summary="List bookings",responses=PatientBookingSerializer(many=True))
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @extend_schema(
        summary="Create booking",
        request=PatientBookingSerializer,
        responses=PatientBookingSerializer,
        description="Create a booking for a patient. The booking will be in pending status until confirmed or rejected by staff."
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)
    
    @extend_schema(
        summary="Update booking (confirm/reject)",
        request=PatientBookingSerializer,
        responses=PatientBookingSerializer,
        description="Update a booking's status to confirm or reject."
    )
    @transaction.atomic
    def update(self, request, *args, **kwargs):
        queryset = self.get_queryset().select_for_update()
        instance = queryset.get(pk=kwargs["pk"])
        schedule = BookingSchedules.objects.select_for_update().get(pk=instance.booking_date_id)
        if instance.status in ["confirmed", "rejected"]:
            raise ValidationError("Booking already processed.")
        new_status = request.data.get("status", "").lower()
        if new_status == "rejected":
            schedule.status = True  # Mark schedule as available
            schedule.save()

        if new_status == "confirmed":
            schedule.status = False  # Mark schedule as unavailable
            schedule.save()
        
        serializer = self.get_serializer(instance, data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        return Response(serializer.data)
    
    @transaction.atomic
    def partial_update(self, request, *args, **kwargs):
        queryset = self.get_queryset().select_for_update()
        instance = queryset.get(pk=kwargs["pk"])
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        return Response(serializer.data)

@extend_schema(tags=["Booking"])    
class ConfirmRejectViewSet(
        mixins.UpdateModelMixin,
        mixins.RetrieveModelMixin,
        viewsets.GenericViewSet
    ):
    """
    ViewSet for confirming or rejecting patient bookings.
    Supports retrieving pending bookings and updating their status to confirm or reject.
    """
    queryset = PatientBooking.objects.none()
    serializer_class = ConfirmRejectSerializer
    permission_classes = [IsAuthenticated, ClinicPermission]

    permission_map = {
        "retrieve": "booking.blocks_read",
        "update": [
            "booking.requests_confirm",
            "booking.requests_reject",
        ],
        "partial_update": [
            "booking.requests_confirm",
            "booking.requests_reject",
        ],
    }

    def get_queryset(self):
        return PatientBooking.objects.for_user(self.request.user).with_related().pending()
    
    @extend_schema(
        summary="Retrieve pending booking",
        responses=ConfirmRejectSerializer
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)
    
    @extend_schema(
        summary="Confirm or reject booking",
        request=ConfirmRejectSerializer,
        responses=ConfirmRejectSerializer,
    )
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)


@extend_schema(tags=["Schedules"]) 
class BookingSchedulesViewSet(
        mixins.ListModelMixin,
        mixins.CreateModelMixin, 
        mixins.UpdateModelMixin,
        mixins.RetrieveModelMixin, 
        viewsets.GenericViewSet
    ):
    """
    ViewSet for managing BookingSchedules instances.
    Supports listing, creating, updating, retrieving, and deleting booking schedules.
    """
    queryset = BookingSchedules.objects.none()
    serializer_class = BookingSchedulesSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]

    permission_map = {
        "list": "booking.blocks_read",
        "retrieve": "booking.blocks_read",
        "create": "booking.blocks_write",
        "update": "booking.blocks_write",
        "partial_update": "booking.blocks_write",
    }

    def get_queryset(self):
        return BookingSchedules.objects.for_user(self.request.user)
    
    @extend_schema(summary="List booking schedules",responses=BookingSchedulesSerializer(many=True))
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @extend_schema(
        summary="Create booking schedule",
        request=BookingSchedulesSerializer,
        responses=BookingSchedulesSerializer,
    )   
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)
    
class PublicPatientBookingRequestViewSet(mixins.CreateModelMixin,viewsets.GenericViewSet):
    authentication_classes = []
    permission_classes = []
    serializer_class = PublicPatientBookingCreateSerializer
    queryset = Patient.objects.none()

    def get_patient_from_token(self):
        token = self.request.query_params.get('token')

        if not token:
            raise ValidationError({"token": "Token required"})
        signer = TimestampSigner()

        try:
            patient_id = signer.unsign(token, max_age=3600)
        except SignatureExpired:
            raise ValidationError({"token": "Token expired"})
        except BadSignature:
            raise ValidationError({"token": "Invalid token"})

        try:
            return Patient.objects.select_related('user').get(pk=patient_id)
        except Patient.DoesNotExist:
            raise NotFound("Patient not found")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['patient'] = self.get_patient_from_token()
        return context


class PublicPatientBookingStatusViewSet(mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """
    Public API for cancelling or rescheduling a booking using a token.
    """
    serializer_class = PublicPatientBookingUpdateSerializer
    authentication_classes = []
    permission_classes = []

    def get_booking_from_token(self):
        token = self.request.query_params.get('token')
        if not token:
            raise ValidationError({"token": "Token required"})

        signer = TimestampSigner()
        try:
            booking_id = signer.unsign(token, max_age=3600)
        except SignatureExpired:
            raise ValidationError({"token": "Token expired"})
        except BadSignature:
            raise ValidationError({"token": "Invalid token"})

        try:
            booking = PatientBooking.objects.select_related('booking_date', 'patient').get(pk=booking_id)
        except PatientBooking.DoesNotExist:
            raise NotFound("Booking not found")

        # Token is invalid if booking was already cancelled/rescheduled
        if booking.status in ['cancelled', 'rescheduled']:
            raise ValidationError({"token": "Token already used; booking cannot be updated"})

        return booking

    def get_object(self):
        return self.get_booking_from_token()

    # Optional GET endpoint to fetch booking info
    def retrieve(self, request, *args, **kwargs):
        booking = self.get_booking_from_token()
        booking_date = f"{booking.booking_date.booking_start.strftime('%Y-%m-%d %H:%M')}-{booking.booking_date.booking_end.strftime('%H:%M%p')}"
        return Response({
            "patient": booking.patient.user.get_full_name(),
            "id": booking.id,
            "description": booking.description,
            "notes": booking.notes,
            "status": booking.status,
            "booking_date": booking_date,
        })
    
    def update(self, request, *args, **kwargs):
        serializer = PublicPatientBookingUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        booking = self.perform_update(serializer)
        booking_date = f"{booking.booking_date.booking_start.strftime('%Y-%m-%d %H:%M')}-{booking.booking_date.booking_end.strftime('%H:%M%p')}"
        return Response({
            "patient": booking.patient.user.get_full_name(),
            "id": booking.id,
            "description": booking.description,
            "notes": booking.notes,
            "status": booking.status,
            "booking_date": booking_date,
        }, status=status.HTTP_200_OK)

    def make_booking_available(self, booking):
        booking.booking_date.status = True  # Mark old schedule as available
        booking.booking_date.save()

    def perform_update(self, serializer):
        booking = self.get_object()
        action = serializer.validated_data.get('action')
        reason = serializer.validated_data.get('reason', '')

        if action == 'cancel':
            booking.status = 'cancelled'
            booking.reason = reason
            self.make_booking_available(booking)
            booking.save()
        elif action == 'reschedule':
            rescheduled_date = serializer.validated_data.get('booking_date')
            self.make_booking_available(booking)
            booking.booking_date = rescheduled_date
            booking.reason = reason
            booking.status = 'rescheduled'
            booking.save()

        return booking