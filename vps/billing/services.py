"""Payment recording (FR-GATE-05) and unpaid-charge lookup."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q, Sum

from vps.accounts.roles import Function, can
from vps.audit.models import AuditLog
from vps.billing.models import Charge, Payment
from vps.vehicles.services import normalise_registration

ALREADY_PAID = "This charge has already been paid."


def record_payment(attendant, charge, method):
    """FR-GATE-05: record one payment and its audit entry atomically."""
    if not can(attendant, Function.GATE_OPERATIONS):
        raise ValidationError({"__all__": "Only Gate Attendants may record payments."})
    if method not in Payment.Method.values:
        raise ValidationError({"method": "Choose Cash, UPI or Card."})
    try:
        with transaction.atomic():
            charge = Charge.objects.select_for_update().get(pk=charge.pk)
            if Payment.objects.filter(charge=charge).exists():
                raise ValidationError({"__all__": ALREADY_PAID})
            payment = Payment.objects.create(charge=charge, method=method, recorded_by=attendant)
            AuditLog.objects.create(
                actor=attendant,
                action="payment.recorded",
                target=f"charge:{charge.pk}",
                after={
                    "reservation": charge.reservation.booking_ref,
                    "kind": charge.kind,
                    "amount_inr": str(charge.amount_inr),
                    "method": method,
                },
            )
    except IntegrityError as error:
        if getattr(getattr(error.__cause__, "diag", None), "constraint_name", None) == (
            "billing_payment_charge_id_key"
        ):
            raise ValidationError({"__all__": ALREADY_PAID}) from error
        raise
    return payment


def unpaid_charges(query):
    """FR-GATE-05: find unpaid charges by booking reference or normalised registration."""
    query = query.strip()
    if not query:
        return []
    return (
        Charge.objects.filter(
            Q(reservation__booking_ref__iexact=query)
            | Q(reservation__vehicle_reg_no=normalise_registration(query)),
            payment__isnull=True,
        )
        .select_related("reservation")
        .order_by("id")
    )


def unpaid_total(driver):
    """FR-BILL-05: the sum of a Driver's charges that have no payment yet."""
    total = Charge.objects.filter(reservation__driver=driver, payment__isnull=True).aggregate(
        total=Sum("amount_inr")
    )["total"]
    return total or Decimal("0.00")
