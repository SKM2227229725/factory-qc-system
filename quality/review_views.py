from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts import roles
from accounts.decorators import role_required

from . import review_services as review
from .forms import ConcessionForm, DispositionForm, RemarksForm
from .models import Inspection

REVIEW_ROLES = (roles.SHIFT_SUPERVISOR, roles.QUALITY_MANAGER)
MRB_ROLES = (roles.PLANT_MANAGER, roles.QUALITY_MANAGER, roles.SHIFT_SUPERVISOR)


def _detail(pk):
    return redirect("inspections:detail", pk=pk)


@role_required(*REVIEW_ROLES)
def review_queue(request):
    pending = (
        Inspection.objects.filter(status=Inspection.Status.PENDING_REVIEW)
        .select_related("work_order", "workstation", "inspector")
        .order_by("submitted_at")
    )
    return render(request, "inspections/review_queue.html", {"inspections": pending})


@role_required(*MRB_ROLES)
def mrb_queue(request):
    waiting = (
        Inspection.objects.filter(status=Inspection.Status.REJECTED, disposition__isnull=True)
        .select_related("work_order", "workstation", "review")
        .order_by("submitted_at")
    )
    return render(request, "inspections/mrb_queue.html", {"inspections": waiting})


@role_required(*REVIEW_ROLES)
@require_POST
def inspection_approve(request, pk):
    inspection = get_object_or_404(Inspection, pk=pk)
    try:
        review.approve_inspection(inspection, request.user, request)
        messages.success(request, "Inspection approved. The lot is cleared for the next step.")
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    return _detail(pk)


@role_required(*REVIEW_ROLES)
def inspection_concede(request, pk):
    inspection = get_object_or_404(Inspection, pk=pk)
    form = ConcessionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            review.issue_concession(
                inspection, request.user,
                form.cleaned_data["reason_code"], form.cleaned_data["justification"],
                request,
            )
            messages.warning(request, "Concession issued and permanently flagged in quality history.")
            return _detail(pk)
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
    return render(request, "inspections/concession_form.html", {
        "form": form, "inspection": inspection
    })


@role_required(*REVIEW_ROLES)
def inspection_reject(request, pk):
    inspection = get_object_or_404(Inspection, pk=pk)
    form = RemarksForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            review.reject_inspection(
                inspection, request.user, form.cleaned_data["remarks"], request
            )
            messages.error(request, "Lot rejected and moved to the Digital Rejection Holding Area.")
            return _detail(pk)
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
    return render(request, "inspections/reject_form.html", {
        "form": form, "inspection": inspection
    })


@role_required(*MRB_ROLES)
def disposition_create(request, pk):
    inspection = get_object_or_404(Inspection, pk=pk)
    form = DispositionForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            review.decide_disposition(
                inspection, request.user,
                form.cleaned_data["decision"], form.cleaned_data["notes"],
                form.cleaned_data["customer_approval"], request,
            )
            messages.success(request, "MRB disposition recorded.")
            return _detail(pk)
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
    return render(request, "inspections/disposition_form.html", {
        "form": form, "inspection": inspection
    })