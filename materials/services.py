"""Business rules for raw material intake and supplier non-conformance.

All state changes here are wrapped in a transaction so the intake row and
its audit entry stay consistent (BRD §3.3).
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction

from audit.services import record

from .models import RawMaterialIntake, SupplierNonConformance

Status = RawMaterialIntake.Status


@transaction.atomic
def register_intake(intake, user, requires_lab_test, request=None):
    intake.received_by = user
    intake.status = Status.IN_LAB_TESTING if requires_lab_test else Status.RECEIVED
    intake.save()
    record("INTAKE_CREATED", intake, user, request, new_value=intake.status)
    return intake


@transaction.atomic
def clear_intake(intake, user, request=None):
    if intake.status not in (Status.RECEIVED, Status.IN_LAB_TESTING):
        raise ValidationError(
            f"An intake in status '{intake.get_status_display()}' cannot be cleared."
        )
    old_status = intake.status
    intake.status = Status.CLEARED
    intake.save(update_fields=["status"])
    record("INTAKE_CLEARED", intake, user, request, old_status, intake.status)
    return intake


@transaction.atomic
def reject_intake(intake, user, reason, request=None):
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("A rejection reason is required.")
    if intake.status == Status.QUARANTINED:
        raise ValidationError("This intake is already in Supplier Quarantine.")
    if intake.status == Status.CLEARED:
        raise ValidationError("A cleared intake cannot be rejected at the dock.")

    old_status = intake.status
    intake.status = Status.QUARANTINED
    intake.save(update_fields=["status"])

    sncr = SupplierNonConformance.objects.create(
        intake=intake, reason=reason, raised_by=user
    )
    record("INTAKE_REJECTED", intake, user, request, old_status,
           f"{intake.status}; {sncr}")

    send_mail(
        subject=f"[SNCR] Heat {intake.heat_number} rejected - {sncr}",
        message=(
            f"Supplier: {intake.supplier}\n"
            f"PO: {intake.po_number}\n"
            f"Heat number: {intake.heat_number}\n"
            f"Reason: {reason}"
        ),
        from_email=None,
        recipient_list=settings.QUALITY_ALERT_EMAILS,
    )
    return sncr