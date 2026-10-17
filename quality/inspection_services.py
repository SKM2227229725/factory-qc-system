"""Business rules for inspection entry (Phase 3C).

Enforces:
- Station code + job number must match real records (no browse-all)
- Fields must be measured in order (server-side, not UI)
- Gauge must exist and not be expired
- Defect photos (2 minimum) required for any failed reading
- CTQ failure freezes the checklist and alerts Quality Head
"""

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from audit.services import record
from plant.models import Gauge, Workstation
from production.models import WorkOrder

from .models import (
    DefectPhoto, Inspection, InspectionReading, TemplateField
)

MIN_DEFECT_PHOTOS = 2
INSPECTABLE_STATUSES = (WorkOrder.Status.RELEASED, WorkOrder.Status.IN_PROGRESS)
Status = Inspection.Status


def open_inspection_for(user):
    return Inspection.objects.filter(inspector=user, status=Status.IN_PROGRESS).first()


@transaction.atomic
def start_inspection(user, station_code, job_number, request=None):
    station = Workstation.objects.filter(code__iexact=(station_code or "").strip()).first()
    if station is None:
        raise ValidationError("Unknown station code. Use the code on the machine's QR plate.")
    order = WorkOrder.objects.filter(number__iexact=(job_number or "").strip()).first()
    if order is None:
        raise ValidationError("Unknown job traveler code.")
    if order.status not in INSPECTABLE_STATUSES:
        raise ValidationError(
            f"Work order {order.number} is '{order.get_status_display()}' "
            "and cannot be inspected."
        )
    existing = open_inspection_for(user)
    if existing:
        raise ValidationError(
            f"Finish your open inspection for {existing.work_order} before starting another."
        )
    inspection = Inspection.objects.create(
        work_order=order, template=order.pdi_template,
        workstation=station, inspector=user,
    )
    record("INSPECTION_STARTED", inspection, user, request,
           new_value=f"{order.number} at {station.code}")
    return inspection


def _require_open_owner(inspection, user):
    if inspection.inspector_id != user.pk:
        raise PermissionDenied
    if inspection.status != Status.IN_PROGRESS:
        raise ValidationError("This inspection is closed and cannot be changed.")


def _failed_readings_missing_photos(inspection):
    return list(
        inspection.readings.filter(passed=False)
        .annotate(photo_count=Count("photos"))
        .filter(photo_count__lt=MIN_DEFECT_PHOTOS)
    )


def _usable_gauge(serial):
    serial = (serial or "").strip()
    gauge = Gauge.objects.filter(serial__iexact=serial).first() if serial else None
    if gauge is None:
        raise ValidationError(
            "Gauge not found in the calibration register. Enter its serial number."
        )
    if not gauge.is_calibration_valid:
        raise ValidationError(
            f"Expired Tool Calibration: {gauge.serial} expired on "
            f"{gauge.calibration_expiry:%d %b %Y}. Get a calibrated tool from the tool crib."
        )
    return gauge


def _alert_quality_head(inspection, field, value):
    send_mail(
        subject=f"[CTQ FAILURE] {inspection.work_order} - {field.name}",
        message=(
            f"Critical-to-Quality dimension '{field.name}' is out of specification.\n"
            f"Work order: {inspection.work_order}\nStation: {inspection.workstation}\n"
            f"Measured: {value}\nSpecification: {field.spec_display}\n"
            f"Inspector: {inspection.inspector}"
        ),
        from_email=None,
        recipient_list=settings.QUALITY_ALERT_EMAILS,
    )


@transaction.atomic
def record_reading(inspection, user, field, *, value=None, passed=None,
                   gauge_serial="", request=None):
    inspection.refresh_from_db()
    _require_open_owner(inspection, user)
    if inspection.ctq_frozen:
        raise ValidationError(
            "Checklist frozen after a CTQ failure. Add defect photos and submit for review."
        )
    missing = _failed_readings_missing_photos(inspection)
    if missing:
        raise ValidationError(
            f"Add at least {MIN_DEFECT_PHOTOS} defect photos for "
            f"'{missing[0].template_field.name}' before continuing."
        )
    expected = inspection.next_field()
    if expected is None:
        raise ValidationError("Every field is already measured. Submit the inspection.")
    if expected.pk != field.pk:
        raise ValidationError(f"Measure in order. The next field is '{expected.name}'.")

    gauge = None
    if field.field_type == TemplateField.FieldType.PASS_FAIL:
        if passed is None:
            raise ValidationError("Select Pass or Fail.")
    else:
        if value is None:
            raise ValidationError("Enter the measured value.")
        if value.as_tuple().exponent < -4:
            raise ValidationError("Use at most 4 decimal places.")
        gauge = _usable_gauge(gauge_serial)
        passed = field.evaluate(value)

    reading = InspectionReading.objects.create(
        inspection=inspection, template_field=field,
        measured_value=value, passed=passed, gauge=gauge,
    )
    outcome = "PASS" if passed else "FAIL"
    record("READING_RECORDED", reading, user, request,
           new_value=f"{field.name}: {value if value is not None else '-'} -> {outcome}; "
                     f"gauge {gauge.serial if gauge else '-'}")

    if not passed and field.is_ctq:
        inspection.ctq_frozen = True
        inspection.save(update_fields=["ctq_frozen"])
        record("CTQ_FAILURE_FROZEN", inspection, user, request, new_value=field.name)
        _alert_quality_head(inspection, field, value)
    return reading


@transaction.atomic
def add_defect_photo(reading, user, image, request=None):
    inspection = reading.inspection
    _require_open_owner(inspection, user)
    if reading.passed:
        raise ValidationError("Photos can only be added to out-of-tolerance readings.")
    photo = DefectPhoto.objects.create(reading=reading, image=image)
    record("DEFECT_PHOTO_ADDED", photo, user, request,
           new_value=reading.template_field.name)
    return photo


@transaction.atomic
def submit_inspection(inspection, user, request=None):
    inspection.refresh_from_db()
    _require_open_owner(inspection, user)
    if not inspection.ctq_frozen:
        remaining = inspection.next_field()
        if remaining is not None:
            raise ValidationError(
                f"Measure every field before submitting. Next: '{remaining.name}'."
            )
    missing = _failed_readings_missing_photos(inspection)
    if missing:
        names = ", ".join(r.template_field.name for r in missing)
        raise ValidationError(
            f"At least {MIN_DEFECT_PHOTOS} defect photos are required for: {names}."
        )
    inspection.status = Status.PENDING_REVIEW
    inspection.submitted_at = timezone.now()
    inspection.save(update_fields=["status", "submitted_at"])
    record("INSPECTION_SUBMITTED", inspection, user, request,
           Status.IN_PROGRESS, Status.PENDING_REVIEW)
    return inspection