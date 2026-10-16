from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts import roles
from accounts.decorators import role_required
from accounts.roles import user_has_role

from . import services
from .forms import StartOperationForm, WorkOrderForm
from .models import WorkOrder, WorkOrderOperation

RELEASE_ROLES = (roles.SHIFT_SUPERVISOR, roles.PLANT_MANAGER)
OPERATOR_ROLES = (roles.MACHINE_OPERATOR, roles.SHIFT_SUPERVISOR)


@login_required
def work_order_list(request):
    orders = WorkOrder.objects.select_related("part", "intake")
    return render(request, "production/work_order_list.html", {
        "orders": orders,
        "can_release": user_has_role(request.user, *RELEASE_ROLES),
    })


@login_required
def work_order_detail(request, pk):
    order = get_object_or_404(
        WorkOrder.objects.select_related("part", "intake", "pdi_template"), pk=pk
    )
    operations = order.operations.select_related("operator", "workstation")
    return render(request, "production/work_order_detail.html", {
        "order": order,
        "operations": operations,
        "can_operate": user_has_role(request.user, *OPERATOR_ROLES),
        "form": StartOperationForm(),
    })


@role_required(*RELEASE_ROLES)
def work_order_create(request):
    form = WorkOrderForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            order = services.release_work_order(
                form.save(commit=False), request.user, request
            )
            messages.success(request, f"Work order {order.number} released.")
            return redirect("production:detail", pk=order.pk)
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
    return render(request, "production/work_order_form.html", {"form": form})


@role_required(*OPERATOR_ROLES)
def operation_start(request, pk, op_pk):
    operation = get_object_or_404(WorkOrderOperation, pk=op_pk, work_order_id=pk)
    form = StartOperationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            services.start_operation(
                operation, request.user,
                form.cleaned_data["workstation_code"], request,
            )
            messages.success(
                request, f"Op {operation.op_number} started at "
                f"{form.cleaned_data['workstation_code']}."
            )
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
    return redirect("production:detail", pk=pk)


@role_required(*OPERATOR_ROLES)
@require_POST
def operation_complete(request, pk, op_pk):
    operation = get_object_or_404(WorkOrderOperation, pk=op_pk, work_order_id=pk)
    try:
        services.complete_operation(operation, request.user, request)
        messages.success(
            request, f"Op {operation.op_number} completed."
        )
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    return redirect("production:detail", pk=pk)