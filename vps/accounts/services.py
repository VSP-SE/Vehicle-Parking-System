"""Account registration rules shared by forms and other callers."""

import re

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from vps.accounts.models import User
from vps.accounts.roles import Function, can
from vps.audit.models import AuditLog

DUPLICATE_EMAIL = "An account with this e-mail already exists"


def register_driver(*, full_name, email, mobile, password):
    full_name = full_name.strip()
    email = User.objects.normalize_email(email.strip())
    user = User(full_name=full_name, email=email, mobile=mobile, role=User.Role.DRIVER)
    errors = {}
    if not 2 <= len(full_name) <= 100:
        errors["full_name"] = ["Enter a full name of 2 to 100 characters."]
    if not re.fullmatch(r"[6-9][0-9]{9}", mobile):
        errors["mobile"] = ["Enter 10 digits, starting with 6, 7, 8 or 9."]
    try:
        user.full_clean(exclude=["password"], validate_unique=False, validate_constraints=False)
    except ValidationError as error:
        errors.update(error.message_dict)
    if User.objects.filter(email=email).exists():
        errors["email"] = [DUPLICATE_EMAIL]
    try:
        validate_password(password, user)
    except ValidationError as error:
        errors["password"] = error.messages
    if errors:
        raise ValidationError(errors)
    try:
        with transaction.atomic():
            return User.objects.create_user(
                email,
                password,
                full_name=full_name,
                mobile=mobile,
                role=User.Role.DRIVER,
            )
    except IntegrityError as error:
        if getattr(getattr(error.__cause__, "diag", None), "constraint_name", None) == (
            "accounts_user_email_key"
        ):
            raise ValidationError({"email": DUPLICATE_EMAIL}) from error
        raise

def create_staff(*, full_name, email, mobile, password, role):
    full_name = full_name.strip()
    email = User.objects.normalize_email(email.strip())

    if role not in (User.Role.ATTENDANT, User.Role.ADMIN):
        raise ValidationError({
            "role": "Only staff roles can be created here."
        })

    user = User(
        full_name=full_name,
        email=email,
        mobile=mobile,
        role=role,
    )

    errors = {}

    try:
        user.full_clean(
            exclude=["password"],
            validate_unique=False,
            validate_constraints=False,
        )
    except ValidationError as error:
        errors.update(error.message_dict)

    if User.objects.filter(email=email).exists():
        errors["email"] = [DUPLICATE_EMAIL]

    try:
        validate_password(password, user)
    except ValidationError as error:
        errors["password"] = error.messages

    if errors:
        raise ValidationError(errors)

    try:
        with transaction.atomic():
            return User.objects.create_user(
                email=email,
                password=password,
                full_name=full_name,
                mobile=mobile,
                role=role,
            )
    except IntegrityError as error:
        if getattr(
            getattr(error.__cause__, "diag", None),
            "constraint_name",
            None,
        ) == "accounts_user_email_key":
            raise ValidationError({"email": DUPLICATE_EMAIL}) from error
        raise


def set_accessible_permit(admin, driver, has_permit):
    """FR-AUTH-06: a Lot Administrator records a Driver's permit, audited when it changes."""
    if not can(admin, Function.MANAGE_STAFF):
        raise ValidationError({"__all__": "Only Lot Administrators may change permits."})
    if driver.role != User.Role.DRIVER:
        raise ValidationError({"__all__": "Only Drivers can hold an accessible-parking permit."})
    if driver.accessible_permit == has_permit:
        return driver
    with transaction.atomic():
        AuditLog.objects.create(
            actor=admin,
            action="driver.permit_changed",
            target=f"user:{driver.pk}",
            before={"accessible_permit": driver.accessible_permit},
            after={"accessible_permit": has_permit},
        )
        driver.accessible_permit = has_permit
        driver.save(update_fields=["accessible_permit"])
    return driver
