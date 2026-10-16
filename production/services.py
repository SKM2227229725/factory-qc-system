"""Business rules for releasing and running work orders.

Order of operations is enforced here, not in the views. A stale form
cannot skip steps because every service re-reads the affected rows
before deciding (BRD §7.1, §8.2).
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from audit.services import record
from materials.models import RawMaterialIntake
from quality.models import PDITemplate

from .models import RoutingStep, WorkOrder, WorkOrderOperation

OrderStatus = WorkOrder.Status
OpStatus = WorkOrderOperation.Status


@transaction.atomic
def release_work_order(work_order, user, request=None):
    """Validate prerequisites, pin the template, and copy the routing."""
    intake = RawMaterialIntake.objects.get(pk=work_order.intake_id)
    if not intake.can_issue_to_production:
        raise ValidationError(
            f"Heat {intake.heat_number} is '{intake.get_status_display()}' "
            "and cannot be issued to production."
        )

    template = PDITemplate.objects.filter(
        part=work_order.part, status=PDITemplate.Status.APPROVED
    ).first()
    if template is None:
        raise ValidationError(
            f"Part {work_order.part} has no approved PDI template."
        )

    steps = list(
        RoutingStep.objects.filter(part=work_order.part).order_by("op_number")
    )
    if not steps:
        raise ValidationError(f"Part {work_order.part} has no routing steps defined.")

    work_order.pdi_template = template
    work_order.created_by = user
    work_order.status = OrderStatus.RELEASED
    work_order.save()

    WorkOrderOperation.objects.bulk_create(
        WorkOrderOperation(
            work_order=work_order,
            op_number=step.op_number,
            name=step.name,
            hold_minutes=step.hold_minutes,
        )
        for step in steps
    )

    record(
        "WORK_ORDER_RELEASED", work_order, user, request,
        new_value=f"heat {intake.heat_number}; PDI {template}; {len(steps)} operations",
    )
    return work_order


def _load_operation(op_id):
    return (
        WorkOrderOperation.objects.select_related("work_order")
        .get(pk=op_id)
    )


@transaction.atomic
def start_operation(operation, user, workstation_code, request=None):
    """Start one operation. Previous operations must be completed."""
    operation = _load_operation(operation.pk)
    order = operation.work_order

    if order.status not in (OrderStatus.RELEASED, OrderStatus.IN_PROGRESS):
        raise ValidationError(
            f"Work order {order.number} is '{order.get_status_display()}' "
            "and cannot be started."
        )

    if operation.status != OpStatus.PENDING:
        raise ValidationError(
            f"Op {operation.op_number} is already {operation.get_status_display()}."
        )

    # Sequence enforcement: previous op must be complete.
    previous = operation.previous_operation()
    if previous is not None and previous.status != OpStatus.COMPLETED:
        raise ValidationError(
            f"Op {previous.op_number} ({previous.name}) must be completed first."
        )

    # Hold timer on previous op.
    if previous is not None and previous.hold_until and previous.hold_until > timezone.now():
        remaining = previous.hold_until - timezone.now()
        mins = int(remaining.total_seconds() // 60)
        raise ValidationError(
            f"Mandatory hold after Op {previous.op_number} ({previous.name}) "
            f"is still active ({mins} min remaining)."
        )

    # Resolve workstation by code.
    from plant.models import Workstation
    station = Workstation.objects.filter(
        code__iexact=(workstation_code or "").strip()
    ).first()
    if station is None:
        raise ValidationError("Unknown station code. Use the code on the machine QR plate.")
    if station.is_pm_overdue:
        raise ValidationError(
            f"Machine {station.code} has an overdue PM check. "
            "Complete the daily check before running production."
        )

    operation.status = OpStatus.IN_PROGRESS
    operation.started_at = timezone.now()
    operation.operator = user
    operation.workstation = station

    if order.status == OrderStatus.RELEASED:
        order.status = OrderStatus.IN_PROGRESS
        order.save(update_fields=["status"])

    operation.save(update_fields=[
        "status", "started_at", "operator", "workstation",
    ])
    record(
        "OPERATION_STARTED", operation, user, request,
        new_value=f"Op {operation.op_number} at {station.code}",
    )
    return operation


@transaction.atomic
def complete_operation(operation, user, request=None):
    """Mark an operation complete and start any hold timer."""
    operation = _load_operation(operation.pk)

    if operation.status != OpStatus.IN_PROGRESS:
        raise ValidationError("Only an in-progress operation can be completed.")
    if operation.operator_id != user.pk:
        raise ValidationError("Only the operator who started it can complete it.")

    operation.status = OpStatus.COMPLETED
    operation.completed_at = timezone.now()
    if operation.hold_minutes:
        operation.hold_until = operation.completed_at + timezone.timedelta(
            minutes=operation.hold_minutes
        )
    operation.save(update_fields=["status", "completed_at", "hold_until"])

    order = operation.work_order
    if not order.operations.exclude(status=OpStatus.COMPLETED).exists():
        order.status = OrderStatus.COMPLETED
        order.save(update_fields=["status"])

    record(
        "OPERATION_COMPLETED", operation, user, request,
        new_value=f"Op {operation.op_number}; hold {operation.hold_minutes} min",
    )
    return operation