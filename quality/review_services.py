from django.core.exceptions import ValidationError
from django.db import transaction

from audit.services import record
from production.models import WorkOrder

from .models import Concession, Inspection, MRBDisposition, SupervisorReview

Status = Inspection.Status
Decision = SupervisorReview.Decision
OrderStatus = WorkOrder.Status
OPEN_ORDER_STATUSES = (OrderStatus.RELEASED, OrderStatus.IN_PROGRESS)


def _load_pending(inspection, user, allowed_order_statuses):
    inspection.refresh_from_db()
    if inspection.status != Status.PENDING_REVIEW:
        raise ValidationError("Only an inspection awaiting approval can be reviewed.")
    if inspection.inspector_id == user.pk:
        raise ValidationError("You cannot review your own inspection.")
    order = WorkOrder.objects.get(pk=inspection.work_order_id)
    if order.status not in allowed_order_statuses:
        raise ValidationError(
            f"Work order {order.number} is '{order.get_status_display()}'. "
            "Resolve it through the Material Review Board first."
        )
    return order


def _close(inspection, user, decision, new_status, remarks, request):
    SupervisorReview.objects.create(
        inspection=inspection, reviewer=user, decision=decision, remarks=remarks
    )
    inspection.status = new_status
    inspection.save(update_fields=["status"])
    record(f"INSPECTION_{decision}", inspection, user, request,
           Status.PENDING_REVIEW, f"{new_status}; {remarks}")


def _has_failures(inspection):
    return inspection.readings.filter(passed=False).exists()


@transaction.atomic
def approve_inspection(inspection, user, request=None):
    _load_pending(inspection, user, OPEN_ORDER_STATUSES)
    if inspection.ctq_frozen or _has_failures(inspection):
        raise ValidationError(
            "Cannot approve: there are out-of-tolerance readings. "
            "Issue a concession (non-CTQ only) or reject the lot."
        )
    _close(inspection, user, Decision.APPROVED, Status.APPROVED, "", request)


@transaction.atomic
def issue_concession(inspection, user, reason_code, justification, request=None):
    justification = (justification or "").strip()
    if reason_code not in Concession.ReasonCode.values:
        raise ValidationError("Select a concession reason code.")
    if not justification:
        raise ValidationError("An engineering justification is required.")
    
    _load_pending(inspection, user, OPEN_ORDER_STATUSES)
    
    if inspection.ctq_frozen or inspection.readings.filter(
        passed=False, template_field__is_ctq=True
    ).exists():
        raise ValidationError(
            "A concession is not allowed when a CTQ dimension is out of specification."
        )
    if not _has_failures(inspection):
        raise ValidationError("Nothing to concede: all readings passed. Approve instead.")
    
    Concession.objects.create(
        inspection=inspection, reason_code=reason_code,
        justification=justification, issued_by=user,
    )
    _close(inspection, user, Decision.CONCEDED, Status.CONCEDED, justification, request)
    record("CONCESSION_ISSUED", inspection, user, request, new_value=reason_code)


@transaction.atomic
def reject_inspection(inspection, user, remarks, request=None):
    remarks = (remarks or "").strip()
    if not remarks:
        raise ValidationError("Remarks are required when rejecting a lot.")
        
    order = _load_pending(
        inspection, user, OPEN_ORDER_STATUSES + (OrderStatus.QUARANTINED,)
    )
    
    _close(inspection, user, Decision.REJECTED, Status.REJECTED, remarks, request)
    
    if order.status != OrderStatus.QUARANTINED:
        old = order.status
        order.status = OrderStatus.QUARANTINED
        order.save(update_fields=["status"])
        record("WORK_ORDER_QUARANTINED", order, user, request, old, order.status)


def _status_after_release(order):
    started = order.operations.exclude(status="PENDING").exists()
    return OrderStatus.IN_PROGRESS if started else OrderStatus.RELEASED


@transaction.atomic
def decide_disposition(inspection, user, decision, notes,
                       customer_approval=None, request=None):
    Decision_ = MRBDisposition.Decision
    notes = (notes or "").strip()
    if decision not in Decision_.values:
        raise ValidationError("Select an MRB disposition.")
    if not notes:
        raise ValidationError("Disposition notes are required.")
    if decision == Decision_.CUSTOMER_CONCESSION and not customer_approval:
        raise ValidationError("Upload the written customer approval for a Customer Special Concession.")

    inspection.refresh_from_db()
    if inspection.status != Status.REJECTED:
        raise ValidationError("Only a rejected inspection needs an MRB disposition.")
    if MRBDisposition.objects.filter(inspection=inspection).exists():
        raise ValidationError("This lot already has an MRB disposition.")
        
    order = WorkOrder.objects.get(pk=inspection.work_order_id)
    if order.status != OrderStatus.QUARANTINED:
        raise ValidationError(f"Work order {order.number} is not in quarantine.")

    MRBDisposition.objects.create(
        inspection=inspection, decision=decision, notes=notes,
        customer_approval=customer_approval or "", decided_by=user,
    )
    new_status = {
        Decision_.REWORK: _status_after_release(order),
        Decision_.CUSTOMER_CONCESSION: _status_after_release(order),
        Decision_.SCRAP: OrderStatus.SCRAPPED,
        Decision_.RTV: OrderStatus.RTV,
    }[decision]
    
    old = order.status
    order.status = new_status
    order.save(update_fields=["status"])
    record("MRB_DISPOSITION", inspection, user, request, old, f"{decision}; {notes}")
    record("WORK_ORDER_STATUS_CHANGED", order, user, request, old, new_status)