"""Template workflow: create, add fields, submit, approve, reject."""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from audit.services import record

from .models import PDITemplate

Status = PDITemplate.Status


@transaction.atomic
def create_template(template, user, request=None):
    template.created_by = user
    template.save()
    record("TEMPLATE_CREATED", template, user, request, new_value=str(template))
    return template


@transaction.atomic
def add_field(template, field, user, request=None):
    last = template.fields.aggregate(last=Max("sequence"))["last"] or 0
    field.template = template
    field.sequence = last + 1
    field.save()
    record("TEMPLATE_FIELD_ADDED", template, user, request, new_value=field.name)
    return field


@transaction.atomic
def remove_field(field, user, request=None):
    template, name = field.template, field.name
    field.delete()
    record("TEMPLATE_FIELD_REMOVED", template, user, request, old_value=name)


@transaction.atomic
def submit_for_approval(template, user, request=None):
    if template.status != Status.DRAFT:
        raise ValidationError("Only a Draft template can be submitted for approval.")
    if not template.fields.exists():
        raise ValidationError("Add at least one inspection field before submitting.")
    template.status = Status.PENDING
    template.save(update_fields=["status"])
    record("TEMPLATE_SUBMITTED", template, user, request, Status.DRAFT, Status.PENDING)


@transaction.atomic
def approve_template(template, user, request=None):
    if template.status != Status.PENDING:
        raise ValidationError("Only a template pending approval can be approved.")

    # Supersede any older approved revision for the same part first.
    older = PDITemplate.objects.filter(
        part=template.part, status=Status.APPROVED
    ).exclude(pk=template.pk)
    for old in older:
        old.status = Status.SUPERSEDED
        old.save(update_fields=["status"])
        record("TEMPLATE_SUPERSEDED", old, user, request, Status.APPROVED, Status.SUPERSEDED)

    template.status = Status.APPROVED
    template.approved_by = user
    template.approved_at = timezone.now()
    template.review_remarks = ""
    template.save(update_fields=["status", "approved_by", "approved_at", "review_remarks"])
    record("TEMPLATE_APPROVED", template, user, request, Status.PENDING, Status.APPROVED)


@transaction.atomic
def reject_template(template, user, remarks, request=None):
    remarks = (remarks or "").strip()
    if template.status != Status.PENDING:
        raise ValidationError("Only a template pending approval can be rejected.")
    if not remarks:
        raise ValidationError("Remarks are required when rejecting a template.")
    template.status = Status.DRAFT
    template.review_remarks = remarks
    template.save(update_fields=["status", "review_remarks"])
    record("TEMPLATE_REJECTED", template, user, request, Status.PENDING, remarks)