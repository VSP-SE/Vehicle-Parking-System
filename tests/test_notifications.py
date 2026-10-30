import pytest
from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.utils import timezone

from vps.notifications.models import ReservationNotification
from vps.notifications.services import (
    MAX_ATTEMPTS,
    process_pending_notifications,
    queue_reservation_notification,
)
from vps.reservations.models import Reservation


pytestmark = pytest.mark.django_db


@pytest.fixture
def notification_reservation(booking):
    """
    Reuse the existing booking fixture from the reservation/expiry tests.
    The booking fixture must provide a reservation with a driver and slot.
    """
    return booking


def test_queue_created_notification(notification_reservation):
    notification = queue_reservation_notification(
        notification_reservation,
        ReservationNotification.Event.CREATED,
    )

    assert notification is not None
    assert notification.event == ReservationNotification.Event.CREATED
    assert notification.status == ReservationNotification.Status.PENDING
    assert notification.recipient_email == notification_reservation.driver.email
    assert notification.reservation == notification_reservation


def test_duplicate_notification_is_not_created(notification_reservation):
    first = queue_reservation_notification(
        notification_reservation,
        ReservationNotification.Event.CREATED,
    )
    second = queue_reservation_notification(
        notification_reservation,
        ReservationNotification.Event.CREATED,
    )

    assert first.pk == second.pk
    assert ReservationNotification.objects.count() == 1


def test_process_pending_notification_sends_email(
    notification_reservation,
    settings,
):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

    notification = queue_reservation_notification(
        notification_reservation,
        ReservationNotification.Event.CREATED,
    )

    result = process_pending_notifications()

    notification.refresh_from_db()

    assert result == {"sent": 1, "failed": 0}
    assert notification.status == ReservationNotification.Status.SENT
    assert notification.sent_at is not None
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [notification_reservation.driver.email]


def test_failed_email_remains_pending_for_retry(
    notification_reservation,
    settings,
):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

    queue_reservation_notification(
        notification_reservation,
        ReservationNotification.Event.CREATED,
    )

    with patch(
        "vps.notifications.services.send_mail",
        side_effect=RuntimeError("SMTP server unavailable"),
    ):
        result = process_pending_notifications()

    notification = ReservationNotification.objects.get()

    assert result == {"sent": 0, "failed": 1}
    assert notification.status == ReservationNotification.Status.PENDING
    assert notification.attempts == 1
    assert "SMTP server unavailable" in notification.last_error


def test_notification_marked_failed_after_max_attempts(
    notification_reservation,
):
    notification = queue_reservation_notification(
        notification_reservation,
        ReservationNotification.Event.CREATED,
    )

    notification.attempts = MAX_ATTEMPTS - 1
    notification.save(update_fields=["attempts"])

    with patch(
        "vps.notifications.services.send_mail",
        side_effect=RuntimeError("SMTP server unavailable"),
    ):
        result = process_pending_notifications()

    notification.refresh_from_db()

    assert result == {"sent": 0, "failed": 1}
    assert notification.status == ReservationNotification.Status.FAILED
    assert notification.attempts == MAX_ATTEMPTS


def test_missing_driver_does_not_create_notification(notification_reservation):
    notification_reservation.driver = None

    result = queue_reservation_notification(
        notification_reservation,
        ReservationNotification.Event.CREATED,
    )

    assert result is None
    assert ReservationNotification.objects.count() == 0
