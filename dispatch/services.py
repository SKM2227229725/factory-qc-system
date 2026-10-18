from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from audit.services import record
from production.models import WorkOrder, WorkOrderOperation
from quality.models import Inspection

from .models import Dispatch

OrderStatus = WorkOrder.Status
DISPATCHABLE_ORDER_STATUSES = (OrderStatus.RELEASED, OrderStatus.IN_PROGRESS, OrderStatus.COMPLETED)
APPROVED_INSPECTION_STATUSES = (Inspection.Status.APPROVED, Inspection.Status.CONCEDED)

def check_dispatch_clearance(work_order, now=None):
    now = now or timezone.now()
    order = WorkOrder.objects.get(pk=work_order.pk)
    if order.status == OrderStatus.DISPATCHED:
        return ["This work order has already been dispatched."]

    reasons = []
    operations = list(order.operations.all())

    if not operations:
        reasons.append("(a) The work order has no operations.")
    for op in operations:
        if op.status != WorkOrderOperation.Status.COMPLETED:
            reasons.append(f"(a) Op {op.op_number} ({op.name}) is not signed off.")

    if order.status not in DISPATCHABLE_ORDER_STATUSES:
        reasons.append(f"(b) Work order status is '{order.get_status_display()}'. The outstanding quality hold must be resolved first.")
    
    for op in operations:
        if op.hold_until and op.hold_until > now:
            reasons.append(f"(b) Mandatory hold after Op {op.op_number} is still active.")

    latest = order.inspections.order_by("-pk").first()
    if latest is None:
        reasons.append("(c) No final PDI inspection has been performed.")
    elif latest.status not in APPROVED_INSPECTION_STATUSES:
        reasons.append(f"(c) The latest PDI inspection (#{latest.pk}) is '{latest.get_status_display()}'. It must be Approved by Quality.")
    return reasons

@transaction.atomic
def issue_gate_pass(work_order, user, customer_po, vehicle_details, serial_numbers, request=None):
    customer_po = (customer_po or "").strip()
    vehicle_details = (vehicle_details or "").strip()
    serial_numbers = (serial_numbers or "").strip()
    if not (customer_po and vehicle_details and serial_numbers):
        raise ValidationError("Customer PO, vehicle details and serial numbers are all required.")

    reasons = check_dispatch_clearance(work_order)
    if reasons:
        raise ValidationError(reasons)

    order = WorkOrder.objects.get(pk=work_order.pk)
    dispatch = Dispatch.objects.create(
        work_order=order, customer_po=customer_po, batch_size=order.quantity,
        vehicle_details=vehicle_details, serial_numbers=serial_numbers,
        gate_pass_number=f"GP-{order.number}", issued_by=user,
    )
    old_status = order.status
    order.status = OrderStatus.DISPATCHED
    order.save(update_fields=["status"])
    record("GATE_PASS_ISSUED", dispatch, user, request, new_value=f"{dispatch.gate_pass_number}; PO {customer_po}")
    record("WORK_ORDER_STATUS_CHANGED", order, user, request, old_status, order.status)
    return dispatch