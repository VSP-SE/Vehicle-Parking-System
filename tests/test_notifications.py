"""FR-RES-07 / TC-10: booking e-mails are queued with the change and sent by the scheduler."""

from datetime import time, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core import mail
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.utils import timezone

from vps.accounts.models import User
from vps.lots.models import Lot, Slot
from vps.notifications.models import ReservationNotification
from vps.notifications.services import (
    MAX_ATTEMPTS,
    process_pending_notifications,
    queue_reservation_notification,
)
from vps.reservations import services as reservations
from vps.reservations.models import Reservation
from vps.vehicles.models import Vehicle

pytestmark = pytest.mark.django_db
START = timezone.localtime().replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=1)


@pytest.fixture
def driver():
    return User.objects.create_user(email="asha@example.com", full_name="Asha Rao")


@pytest.fixture
def lot():
    lot = Lot.objects.create(
        name="Lot A", address="Ring Road", opens_at=time(6), closes_at=time(23)
    )
    Slot.objects.create(lot=lot, code="S1", distance_rank=1)
    return lot


@pytest.fixture
def notification_reservation(driver, lot):
    return Reservation.objects.create(
        booking_ref="VPS-261030-0001",
        driver=driver,
        vehicle_reg_no="KA01AB1234",
        slot=lot.slots.get(),
        period=DateTimeTZRange(START, START + timedelta(hours=2)),
    )


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


def test_reserve_queues_a_created_email(driver, lot):
    car = Vehicle.objects.create(owner=driver, registration_no="KA01AB1234", vehicle_type="Car")
    booking = reservations.reserve(driver, car, lot, START, START + timedelta(hours=1))

    notification = ReservationNotification.objects.get()
    assert (notification.reservation, notification.event) == (booking, "created")
    assert notification.recipient_email == "asha@example.com"
    assert booking.booking_ref in notification.subject


def test_cancel_queues_a_cancelled_email(driver, notification_reservation):
    reservations.cancel_reservation(
        driver=driver, reservation_id=notification_reservation.pk, now=START - timedelta(hours=3)
    )
    assert ReservationNotification.objects.get().event == "cancelled"


def test_tc10_expiry_queues_an_expired_email(notification_reservation):
    """Still Reserved at 10:14 with no e-mail; Expired at 10:16 with the e-mail queued."""
    reservations.expire_no_shows(now=START + timedelta(minutes=14))
    assert not ReservationNotification.objects.exists()

    reservations.expire_no_shows(now=START + timedelta(minutes=16))

    notification_reservation.refresh_from_db()
    assert notification_reservation.status == Reservation.Status.EXPIRED
    assert notification_reservation.charges.get().amount_inr == Decimal("50.00")
    notification = ReservationNotification.objects.get()
    assert notification.event == "expired"
    assert "expired" in notification.message


def test_failed_booking_queues_nothing(driver, lot):
    car = Vehicle.objects.create(
        owner=driver, registration_no="KA01AB1234", vehicle_type="TwoWheeler"
    )
    with pytest.raises(Exception):
        reservations.reserve(driver, car, lot, START, START + timedelta(hours=1))
    assert not ReservationNotification.objects.exists()


def test_scheduler_command_sends_queued_mail(notification_reservation, settings, capsys):
    from django.core.management import call_command

    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    queue_reservation_notification(notification_reservation, ReservationNotification.Event.CREATED)

    call_command("send_reservation_notifications")

    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["asha@example.com"]
    assert "Hello Asha Rao" in mail.outbox[0].body
    assert "Sent 1 notification(s); failed 0 attempt(s)." in capsys.readouterr().out
