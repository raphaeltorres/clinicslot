from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import datetime, timedelta
from apps.booking.models import BookingSchedules
from django.contrib.auth.models import User


class Command(BaseCommand):
    help = "Generate booking schedules for today based on clinic hours"

    def add_arguments(self, parser):
        parser.add_argument('--tenant', type=str, help='Tenant username', required=True)
        parser.add_argument('--open', type=str, help='Opening time (HH:MM)', required=True)
        parser.add_argument('--close', type=str, help='Closing time (HH:MM)', required=True)

    def handle(self, *args, **options):
        open_time_str = options['open']
        close_time_str = options['close']
        tenant_username = options['tenant']

        # Convert to time objects
        open_time = datetime.strptime(open_time_str, "%H:%M").time()
        close_time = datetime.strptime(close_time_str, "%H:%M").time()

        today = timezone.localdate()  # current date

        # Combine date + time
        current_start = datetime.combine(today, open_time)
        closing_datetime = datetime.combine(today, close_time)

        # Make timezone aware
        current_start = timezone.make_aware(current_start)
        closing_datetime = timezone.make_aware(closing_datetime)

        created_count = 0

        tenant = User.objects.filter(username=tenant_username, groups__name__in=["Tenant Admin"]).get()
        while current_start < closing_datetime:
            current_end = current_start + timedelta(hours=1)

            # Avoid duplicates
            exists = BookingSchedules.objects.filter(
                booking_start=current_start,
                booking_end=current_end,
                tenant=tenant
            ).exists()

            if not exists:
                BookingSchedules.objects.create(
                    booking_start=current_start,
                    booking_end=current_end,
                    tenant=tenant,
                    status=True
                )
                created_count += 1
                self.stdout.write(
                    f"Created available blocks: {current_start.strftime('%Y-%m-%d %H:%M')} - {current_end.strftime('%Y-%m-%d %H:%M')}"
                )

            current_start = current_end

        self.stdout.write(self.style.SUCCESS(
            f"{created_count} booking slots created for {today}."
        ))