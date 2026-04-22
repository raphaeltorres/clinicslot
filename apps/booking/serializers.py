from rest_framework import serializers
from .models import Patient, TenantStaff, BookingSchedules, PatientBooking
from django.db.models import Count, Q
from django.contrib.auth.models import User, Group, Permission
from django.core import signing

ALLOWED_PERMISSIONS = [
    "blocks_read",
    "blocks_write",
    "requests_confirm",
    "requests_reject",
    "requests_cancel",
    "requests_reschedule",
    "patient_invite",
    "patient_view",
    "patient_edit",
]

PATIENT_ALLOWED_PERMISSIONS = [
    "blocks_write",
    "requests_cancel",
    "requests_reschedule"
]

def get_tenant(request):
    tenant = None
    groups = set(request.user.groups.values_list('name', flat=True))
    
    if "Staff" in groups:
        tenant_staff =  getattr(request.user, 'tenantstaff', None)
        tenant = tenant_staff.tenant
    elif "Tenant Admin" in groups:
        tenant = request.user
    return tenant

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'password', 'email', 'first_name', 'last_name', 'is_staff', 'is_active',]
        extra_kwargs = {
            'password': {'write_only': True, 'required': False},
            'username': {'required': False},
        }

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User.objects.create(**validated_data)
        user.set_password(password)
        user.save()
        user.groups.set(Group.objects.filter(name="Tenant Admin"))
        return user
    
    def to_representation(self, instance):
        group_name = ""
        for group in instance.groups.all():
            group_name = group.name
        
        return {
            'id': instance.id,
            'username': instance.username,
            'email': instance.email,
            'password': instance.password,
            'first_name': instance.first_name,
            'last_name': instance.last_name,
            'is_staff': instance.is_staff,
            'is_active': instance.is_active,
            'group': group_name
        }

class PermissionField(serializers.PrimaryKeyRelatedField):
    def display_value(self, instance):
        return f"{instance.codename}  - ({instance.name})"
    
class TenantUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'password',]
        extra_kwargs = {
            'password': {'write_only': True, 'required': False},
            'username': {'required': False},
        }

    def validate_user_permissions(self, perms):
        allowed = Permission.objects.filter(codename__in=ALLOWED_PERMISSIONS)

        for perm in perms:
            if perm not in allowed:
                raise serializers.ValidationError("Invalid permission")
        return perms

    def create(self, validated_data):
        user_permissions = validated_data.pop('user_permissions', [])

        password = validated_data.pop('password')
        user = User.objects.create(**validated_data)

        user.set_password(password)
        user.save()

        if user_permissions:
            user.user_permissions.set(user_permissions)

        return user
    
    def update(self, instance, validated_data):
        instance.email = validated_data.get('email', instance.email)
        instance.first_name = validated_data.get('first_name', instance.first_name)
        instance.last_name = validated_data.get('last_name', instance.last_name)

        if 'password' in validated_data:
            instance.set_password(validated_data['password'])

        if 'user_permissions' in validated_data:
            instance.user_permissions.set(validated_data['user_permissions'])

        instance.save()
        return instance
    
class PatientBookingSerializer(serializers.ModelSerializer):
    class Meta:
        model = PatientBooking
        fields = ['id', 'patient', 'description', 'notes', 'reason', 'booking_date']

    def validate(self, data):
        booking_date = data.get('booking_date')
        patient = data.get('patient')
        if booking_date and patient:
            existing_booking = PatientBooking.objects.filter(
                patient=patient,
                booking_date=booking_date,
                status__in=[
                    PatientBooking.StatusChoices.PENDING,
                    PatientBooking.StatusChoices.CONFIRMED,
                    PatientBooking.StatusChoices.RESCHEDULED,
                ]
            ).exists()
            if existing_booking:
                raise serializers.ValidationError("You already have a booking for this time slot.")
        if booking_date and not booking_date.status:
            raise serializers.ValidationError("This booking slot is no longer available.")
        return data

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        if not request:
            return fields
        tenant = get_tenant(request)
        if request and request.user.is_authenticated:
            fields["patient"].queryset = Patient.objects.for_user(request.user)
            fields["booking_date"].queryset = (
                    BookingSchedules.objects
                    .filter(
                        tenant=tenant,
                        status=True,
                        is_deleted=False,
                    )
                    .annotate(
                        booking_count=Count(
                            "patient_booking",
                            filter=~Q(
                                patient_booking__status__in=[
                                    PatientBooking.StatusChoices.CANCELLED,
                                    PatientBooking.StatusChoices.REJECTED,
                                ]
                            ),
                        )
                    )
                    .filter(booking_count=0)
                    .order_by("booking_start")
                )
        return fields
    
    def create(self, validated_data):
        signer = signing.TimestampSigner()
        booking = PatientBooking.objects.create(**validated_data)
        booking.token = signer.sign(booking.id)
        booking.save()
        return booking

    def update(self, instance, validated_data):
        instance.description = validated_data.get('description', instance.description)
        instance.notes = validated_data.get('notes', instance.notes)
        if instance.status != validated_data.get('status', instance.status):
            instance.status = validated_data.get('status', instance.status)
            if validated_data.get('status') == 'confirmed':
                instance.reason = ""
                instance.booking_date.status = False
                instance.booking_date.save()
            elif validated_data.get('status') == 'cancelled':
                instance.booking_date.status = True
                instance.booking_date.save()
        instance.booking_date = validated_data.get('booking_date', instance.booking_date)
        signer = signing.TimestampSigner()
        token = signer.sign(instance.id)
        instance.token = token
        instance.save()
        return instance

    def to_representation(self, instance):
        booking_date = f"{instance.booking_date.booking_start.strftime('%Y-%m-%d %H:%M')} - {instance.booking_date.booking_end.strftime('%H:%M%p')}"
        return {
            'booking_date_id': instance.booking_date.id,
            'patient': instance.patient.user.get_full_name(),
            'description': instance.description,
            'notes': instance.notes,
            'booking_date': booking_date,
            'date_created': instance.date_created,
            'status': instance.status,
            'id': instance.id,
            'token': instance.token
        }
    
class PatientSerializer(serializers.ModelSerializer):
    user = TenantUserSerializer(read_only=False)
    patient_bookings = PatientBookingSerializer(many=True, read_only=True)
    permissions = PermissionField(
        queryset=Permission.objects.filter(codename__in=PATIENT_ALLOWED_PERMISSIONS),
        many=True,
        required=False
    )
    
    class Meta:
        model = Patient
        fields = ['id', 'user', 'address', 'phone_number', 'patient_bookings', 'permissions']

    def create(self, validated_data):
        request = self.context.get('request')

        user_data = validated_data.pop('user')
        user_data['user_permissions'] = validated_data.pop('permissions', [])
        user = TenantUserSerializer().create(user_data)

        user.is_active = True
        user.is_staff = False
        user.save()

        user.groups.set(Group.objects.filter(name="Patient"))
        groups = set(request.user.groups.values_list('name', flat=True))

        if "Staff" in groups:
            tenant_staff = getattr(request.user, 'tenantstaff', None)
            validated_data['tenant'] = tenant_staff.tenant
        elif "Tenant Admin" in groups:
            validated_data['tenant'] = request.user

        patient = Patient.objects.create(user=user, **validated_data)
        patient.token = signing.TimestampSigner().sign(patient.id)
        patient.save()

        return patient
    
    def to_representation(self, instance):
        group_name = ""
        for group in instance.user.groups.all():
            group_name = group.name

        bookings = getattr(instance, 'patient_bookings', [])
        patient_bookings = PatientBookingSerializer(bookings, many=True).data
        
        return {
            'id': instance.id,
            'token': instance.token,
            'tenant': instance.tenant.username if instance.tenant else None,
            'first_name': instance.user.first_name,
            'last_name': instance.user.last_name,
            'email': instance.user.email,
            'address': instance.address,
            'phone_number': instance.phone_number,
            'groups': group_name,
            'date_created': instance.date_created,
            'patient_bookings': patient_bookings,
            'permissions': [perm.codename for perm in instance.user.user_permissions.all()]
        }


class PatientUpdateSerializer(serializers.ModelSerializer):
    permissions = PermissionField(
        queryset=Permission.objects.filter(codename__in=PATIENT_ALLOWED_PERMISSIONS),
        many=True,
        required=False
    )
    
    class Meta:
        model = Patient
        fields = ['address', 'phone_number', 'permissions']

    def update(self, instance, validated_data):
        instance.address = validated_data.get('address', instance.address)
        instance.phone_number = validated_data.get('phone_number', instance.phone_number)

        if 'permissions' in validated_data:
            instance.user.user_permissions.set(validated_data['permissions'])

        instance.save()
        return instance
    
    def to_representation(self, instance):
        group_name = ""
        for group in instance.user.groups.all():
            group_name = group.name
        
        return {
            'id': instance.id,
            'token': instance.token,
            'tenant': instance.tenant.username if instance.tenant else None,
            'first_name': instance.user.first_name,
            'last_name': instance.user.last_name,
            'email': instance.user.email,
            'address': instance.address,
            'phone_number': instance.phone_number,
            'groups': group_name,
            'date_created': instance.date_created,
            'permissions': [perm.codename for perm in instance.user.user_permissions.all()]
        }
        

class StaffSerializer(serializers.ModelSerializer):
    user = TenantUserSerializer(read_only=False)
    permissions = PermissionField(
        queryset=Permission.objects.filter(codename__in=ALLOWED_PERMISSIONS),
        many=True,
        required=False
    )    
    class Meta:
        model = TenantStaff
        fields = ['id', 'user', 'address', 'phone_number', 'permissions']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')

        if request and request.user.is_superuser:
            self.fields['tenant'] = serializers.PrimaryKeyRelatedField(
                queryset=User.objects.filter(groups__name="Tenant Admin"),
                required=True
            )

    def create(self, validated_data):
        request = self.context.get('request')
        user_data = validated_data.pop('user')
        user_data['user_permissions'] = validated_data.pop('permissions', [])
        user = TenantUserSerializer().create(user_data)

        user.is_active = True
        user.is_staff = True
        user.save()

        user.groups.set(Group.objects.filter(name="Staff"))
        tenant = request.user
        if request.user.is_superuser:
            tenant = validated_data.get("tenant")

        validated_data['tenant'] = tenant
        staff = TenantStaff.objects.create(user=user, **validated_data)
        return staff
    
    def to_representation(self, instance):
        group_name = ""
        for group in instance.user.groups.all():
            group_name = group.name
        
        return {
            'id': instance.id,
            'username': instance.user.username,
            'company': instance.tenant.get_full_name() if instance.tenant else None,
            'first_name': instance.user.first_name,
            'last_name': instance.user.last_name,
            'email': instance.user.email,
            'address': instance.address,
            'phone_number': instance.phone_number,
            'groups': group_name,
            'date_created': instance.date_created,
            'permissions': [perm.codename for perm in instance.user.user_permissions.all()]
        }

class UserUpdateSerializer(serializers.ModelSerializer):
    permissions = PermissionField(
        queryset=Permission.objects.filter(codename__in=ALLOWED_PERMISSIONS),
        many=True,
        required=False
    )    
    class Meta:
        model = TenantStaff
        fields = ['address', 'phone_number', 'permissions']

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        groups = set(request.user.groups.values_list('name', flat=True))
        if "Staff" not in groups:
            fields["permissions"].queryset = Permission.objects.filter(codename__in=PATIENT_ALLOWED_PERMISSIONS)
        return fields

    def update(self, instance, validated_data):
        instance.address = validated_data.get('address', instance.address)
        instance.phone_number = validated_data.get('phone_number', instance.phone_number)

        if 'permissions' in validated_data:
            instance.user.user_permissions.set(validated_data['permissions'])

        instance.save()
        return instance
    
    def to_representation(self, instance):
        group_name = ""
        for group in instance.user.groups.all():
            group_name = group.name
        
        return {
            'id': instance.id,
            'username': instance.user.username,
            'company': instance.tenant.get_full_name() if instance.tenant else None,
            'first_name': instance.user.first_name,
            'last_name': instance.user.last_name,
            'email': instance.user.email,
            'address': instance.address,
            'phone_number': instance.phone_number,
            'groups': group_name,
            'date_created': instance.date_created,
            'permissions': [perm.codename for perm in instance.user.user_permissions.all()]
        }

class BookingSchedulesSerializer(serializers.ModelSerializer):
    class Meta:
        model = BookingSchedules
        fields = ['id', 'booking_start', 'booking_end', 'status', 'is_deleted']
        
    def create(self, validated_data):
        request = self.context.get('request')
        groups = set(request.user.groups.values_list('name', flat=True))

        if "Staff" in groups:
            tenant_staff = getattr(request.user, 'tenantstaff', None)
            validated_data['tenant'] = tenant_staff.tenant
        elif "Tenant Admin" in groups:
            validated_data['tenant'] = request.user
        return BookingSchedules.objects.create(**validated_data)
    
    def update(self, instance, validated_data):
        instance.booking_start = validated_data.get('booking_start', instance.booking_start)
        instance.booking_end = validated_data.get('booking_end', instance.booking_end)
        instance.status = validated_data.get('status', instance.status)
        instance.is_deleted = validated_data.get('is_deleted', instance.is_deleted)
        instance.save()
        return instance
    
    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['booked'] = PatientBooking.objects.filter(
            booking_date=instance,
            status__in=['pending', 'confirmed']
        ).exists()

        return data


class ConfirmRejectSerializer(serializers.ModelSerializer):
    status = serializers.ChoiceField(choices=[('confirmed', 'Confirmed'), ('rejected', 'Rejected')])
    class Meta:
        model = PatientBooking
        fields = ['id', 'notes', 'status']

    def update(self, instance, validated_data):
        instance.status = validated_data.get('status', instance.status)
        instance.notes = validated_data.get('notes', instance.notes)
        if validated_data.get('status') == 'confirmed':
            instance.booking_date.status = False
        elif validated_data.get('status') == 'rejected':
            instance.booking_date.status = True
        instance.save(update_fields=['status', 'notes'])
        return instance
    
    def to_representation(self, instance):
        booking_date = f"{instance.booking_date.booking_start.strftime('%Y-%m-%d %H:%M')} - {instance.booking_date.booking_end.strftime('%H:%M%p')}"
        return {
            'reference_number': instance.id,
            'patient': instance.patient.user.get_full_name(),
            'tentant': instance.patient.tenant.get_full_name(),
            'notes': instance.notes,
            'description': instance.description,
            'booking_date': booking_date,
            'date_created': instance.date_created,
            'status': instance.status,
            'token': instance.token
        }
    
class PublicPatientBookingUpdateSerializer(serializers.ModelSerializer):
    action = serializers.CharField(write_only=True)
    booking_date = serializers.PrimaryKeyRelatedField(
        queryset = (
            BookingSchedules.objects
            .annotate(
                booking_count=Count(
                    "patient_booking",
                    filter=~Q(
                        patient_booking__status__in=[
                            PatientBooking.StatusChoices.CANCELLED,
                            PatientBooking.StatusChoices.REJECTED,
                        ]
                    ),
                )
            )
            .filter(
                booking_count=0,
                status=True,
            )
            .order_by("booking_start")
        ), 
        write_only=True,
        required=False
    )
    reason = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = PatientBooking
        fields = ['action', 'booking_date', 'reason']

    def validate_action(self, value):
        if value not in ['cancel', 'reschedule']:
            raise serializers.ValidationError("Action must be 'cancel' or 'reschedule'.")
        return value
    
    def validate(self, data):
        action = data.get('action')
        booking_date = data.get('booking_date')

        if action == 'reschedule' and not booking_date:
            raise serializers.ValidationError({
                'booking_date': 'This field is required when action is reschedule.'
            })
        return data
    

class PublicPatientBookingCreateSerializer(serializers.ModelSerializer):
    booking_date = serializers.PrimaryKeyRelatedField(
        queryset = (
            BookingSchedules.objects
            .annotate(
                booking_count=Count(
                    "patient_booking",
                    filter=~Q(
                        patient_booking__status__in=[
                            PatientBooking.StatusChoices.CANCELLED,
                            PatientBooking.StatusChoices.REJECTED,
                        ]
                    ),
                )
            )
            .filter(
                booking_count=0,
                status=True,
            )
            .order_by("booking_start")
        )
    )

    class Meta:
        model = PatientBooking
        fields = ['booking_date', 'description']

    def validate(self, attrs):
        patient = self.context.get('patient')
        booking_date = attrs.get('booking_date')

        if not patient:
            raise serializers.ValidationError("Invalid patient.")

        # Prevent duplicate active booking
        exists = PatientBooking.objects.filter(
            patient=patient,
            booking_date=booking_date,
            status__in=['pending', 'confirmed']
        ).exists()

        if exists:
            raise serializers.ValidationError(
                "You already have an active booking for this schedule."
            )

        return attrs

    def create(self, validated_data):
        patient = self.context['patient']
        booking = PatientBooking.objects.create(
            patient=patient,
            status='pending',
            **validated_data
        )
        booking.token = signing.TimestampSigner().sign(str(booking.id))
        booking.save()
        
        return booking

    def to_representation(self, instance):
        booking_date = f"{instance.booking_date.booking_start.strftime('%Y-%m-%d %H:%M')} - {instance.booking_date.booking_end.strftime('%H:%M%p')}"
        return {
            'tentant': instance.patient.tenant.get_full_name(),
            'patient': instance.patient.user.get_full_name(),
            'description': instance.description,
            'notes': instance.notes,
            'booking_date': booking_date,
            'date_created': instance.date_created,
            'status': instance.status,
            'reference_number': instance.id,
            'token': instance.token
        }