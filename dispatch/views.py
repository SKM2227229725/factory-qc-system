from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from accounts import roles
from accounts.decorators import role_required
from production.models import WorkOrder

from . import services
from .forms import DispatchForm
from .models import Dispatch

DISPATCH_ROLES = (roles.WAREHOUSE_CLERK, roles.SHIFT_SUPERVISOR, roles.PLANT_MANAGER)
CLOSED_STATUSES = (WorkOrder.Status.DISPATCHED, WorkOrder.Status.SCRAPPED, WorkOrder.Status.RTV)

def _lockout(request, order, reasons):
    return render(request, "dispatch/lockout.html", {"order": order, "reasons": reasons}, status=403)

@role_required(*DISPATCH_ROLES)
def dispatch_board(request):
    now = timezone.now()
    orders = WorkOrder.objects.exclude(status__in=CLOSED_STATUSES).select_related("part")
    rows = [(order, services.check_dispatch_clearance(order, now)) for order in orders]
    dispatches = Dispatch.objects.select_related("work_order", "issued_by")
    return render(request, "dispatch/dispatch_board.html", {"rows": rows, "dispatches": dispatches})

@role_required(*DISPATCH_ROLES)
def dispatch_create(request, pk):
    order = get_object_or_404(WorkOrder, pk=pk)
    if Dispatch.objects.filter(work_order=order).exists():
        return redirect("dispatch:gate_pass", pk=pk)
    reasons = services.check_dispatch_clearance(order)
    if reasons:
        return _lockout(request, order, reasons)

    form = DispatchForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            services.issue_gate_pass(order, request.user, request=request, **form.cleaned_data)
            messages.success(request, "Dispatch cleared. Gate pass issued.")
            return redirect("dispatch:gate_pass", pk=pk)
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
    return render(request, "dispatch/dispatch_form.html", {
        "title": f"Dispatch manifest: {order.number}",
        "form": form, "order": order
    })

def _document(request, pk, template_name):
    order = get_object_or_404(WorkOrder.objects.select_related("part", "intake"), pk=pk)
    dispatch = Dispatch.objects.filter(work_order=order).select_related("issued_by").first()
    if dispatch is None:
        reasons = services.check_dispatch_clearance(order)
        if not reasons:
            return redirect("dispatch:create", pk=pk)
        return _lockout(request, order, reasons)
    return render(request, template_name, {
        "order": order, "dispatch": dispatch,
        "inspection": order.inspections.order_by("-pk").first(),
    })

@role_required(*DISPATCH_ROLES)
def gate_pass(request, pk):
    return _document(request, pk, "dispatch/gate_pass.html")

@role_required(*DISPATCH_ROLES)
def packing_slip(request, pk):
    return _document(request, pk, "dispatch/packing_slip.html")