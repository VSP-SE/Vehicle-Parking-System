from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from vps.notifications.models import ReservationNotification


MAX_ATTEMPTS = 5


def queue_reservation_notification(reservation, event):
    """Queue an email for a reservation event."""

    if not reservation.driver or not reservation.driver.email:
        return None

    event_labels = {
        ReservationNotification.Event.CREATED: "created",
        ReservationNotification.Event.CANCELLED: "cancelled",
        ReservationNotification.Event.MOVED: "rescheduled",
        ReservationNotification.Event.EXPIRED: "expired",
    }

    label = event_labels[event]

    subject = f"Parking booking {label}: {reservation.booking_ref}"

    message = (
        f"Hello {reservation.driver.full_name},\n\n"
        f"Your parking booking has been {label}.\n\n"
        f"Booking reference: {reservation.booking_ref}\n"
        f"Vehicle: {reservation.vehicle_reg_no}\n"
        f"Parking slot: {reservation.slot}\n"
        f"Status: {reservation.status}\n\n"
        "Vehicle Parking System"
    )

    period = reservation.period
    event_key = (
        f"{reservation.pk}:{event}:"
        f"{period.lower.isoformat()}:{period.upper.isoformat()}"
    )

    notification, _ = ReservationNotification.objects.get_or_create(
        event_key=event_key,
        defaults={
            "reservation": reservation,
            "event": event,
            "recipient_email": reservation.driver.email,
            "subject": subject,
            "message": message,
        },
    )

    return notification


def process_pending_notifications(batch_size=50):
    """Send pending notification emails."""

    sent = 0
    failed = 0

    for _ in range(batch_size):
        with transaction.atomic():
            notification = (
                ReservationNotification.objects
                .select_for_update(skip_locked=True)
                .filter(
                    status=ReservationNotification.Status.PENDING,
                    attempts__lt=MAX_ATTEMPTS,
                )
                .order_by("created_at")
                .first()
            )

            if notification is None:
                break

            notification.attempts += 1

            try:
                result = send_mail(
                    subject=notification.subject,
                    message=notification.message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[notification.recipient_email],
                    fail_silently=False,
                )

                if result != 1:
                    raise RuntimeError("Email backend did not confirm delivery.")

                notification.status = ReservationNotification.Status.SENT
                notification.sent_at = timezone.now()
                notification.last_error = ""
                sent += 1

            except Exception as error:
                notification.last_error = str(error)

                if notification.attempts >= MAX_ATTEMPTS:
                    notification.status = ReservationNotification.Status.FAILED

                failed += 1

            notification.save(
                update_fields=[
                    "attempts",
                    "status",
                    "sent_at",
                    "last_error",
                ]
            )

    return {"sent": sent, "failed": failed}