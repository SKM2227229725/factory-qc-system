from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts import roles
from accounts.decorators import role_required
from accounts.roles import user_has_role

from . import inspection_services as services
from .forms import PhotoForm, ReadingForm, StartInspectionForm
# MRBDisposition import kiya gaya hai
from .models import Inspection, InspectionReading, TemplateField, MRBDisposition
# Review roles import kiye gaye hain
from .review_views import REVIEW_ROLES, MRB_ROLES

INSPECTOR_ROLES = (roles.QA_FLOOR_INSPECTOR,)


def _error_text(form):
    return " ".join(" ".join(errors) for errors in form.errors.values())


@login_required
def inspection_list(request):
    inspections = Inspection.objects.select_related(
        "work_order", "workstation", "inspector"
    )
    return render(request, "inspections/inspection_list.html", {
        "inspections": inspections,
        "can_start": user_has_role(request.user, *INSPECTOR_ROLES),
    })


@role_required(*INSPECTOR_ROLES)
def inspection_start(request):
    open_inspection = services.open_inspection_for(request.user)
    if open_inspection:
        messages.info(request, "You have an open inspection. Finish it first.")
        return redirect("inspections:detail", pk=open_inspection.pk)
    form = StartInspectionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            inspection = services.start_inspection(
                request.user, form.cleaned_data["station_code"],
                form.cleaned_data["job_code"], request,
            )
            return redirect("inspections:detail", pk=inspection.pk)
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
    return render(request, "inspections/start.html", {"form": form})


@login_required
def inspection_detail(request, pk):
    inspection = get_object_or_404(
        Inspection.objects.select_related(
            "work_order", "template__part", "workstation", "inspector"
        ),
        pk=pk,
    )
    is_open_owner = (
        inspection.inspector_id == request.user.pk
        and inspection.status == Inspection.Status.IN_PROGRESS
    )
    next_field = None
    if is_open_owner and not inspection.ctq_frozen:
        next_field = inspection.next_field()
    readings = inspection.readings.select_related(
        "template_field", "gauge"
    ).prefetch_related("photos")
    
    return render(request, "inspections/inspection_detail.html", {
        "inspection": inspection,
        "readings": readings,
        "is_open_owner": is_open_owner,
        "next_field": next_field,
        "form": ReadingForm(next_field) if next_field else None,
        "can_submit": is_open_owner and (inspection.ctq_frozen or next_field is None),
        "min_photos": services.MIN_DEFECT_PHOTOS,
        # --- NAYE CONTEXT VARIABLES SUPERVISOR/MRB KE LIYE ---
        "can_review": (
            inspection.status == Inspection.Status.PENDING_REVIEW
            and user_has_role(request.user, *REVIEW_ROLES)
            and inspection.inspector_id != request.user.pk
        ),
        "can_dispose": (
            inspection.status == Inspection.Status.REJECTED
            and user_has_role(request.user, *MRB_ROLES)
            and not MRBDisposition.objects.filter(inspection=inspection).exists()
        ),
        "has_failures": inspection.readings.filter(passed=False).exists(),
    })


@role_required(*INSPECTOR_ROLES)
@require_POST
def reading_add(request, pk, field_pk):
    inspection = get_object_or_404(Inspection, pk=pk, inspector=request.user)
    field = get_object_or_404(TemplateField, pk=field_pk, template=inspection.template)
    form = ReadingForm(field, request.POST)
    if not form.is_valid():
        messages.error(request, _error_text(form))
        return redirect("inspections:detail", pk=pk)

    data = form.cleaned_data
    try:
        reading = services.record_reading(
            inspection, request.user, field,
            value=data.get("value"),
            passed=(data["result"] == "PASS") if "result" in data else None,
            gauge_serial=data.get("gauge_serial", ""),
            request=request,
        )
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
        return redirect("inspections:detail", pk=pk)

    if reading.passed:
        messages.success(request, f"PASS: {field.name} is within limits.")
    else:
        text = (f"FAIL: {field.name} is OUT OF TOLERANCE. "
                f"Add at least {services.MIN_DEFECT_PHOTOS} defect photos.")
        if field.is_ctq:
            text += " CTQ failure: checklist frozen and Quality Head alerted."
        messages.error(request, text)
    return redirect("inspections:detail", pk=pk)


@role_required(*INSPECTOR_ROLES)
@require_POST
def photo_add(request, pk, reading_pk):
    inspection = get_object_or_404(Inspection, pk=pk, inspector=request.user)
    reading = get_object_or_404(InspectionReading, pk=reading_pk, inspection=inspection)
    form = PhotoForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, _error_text(form))
    else:
        try:
            services.add_defect_photo(reading, request.user, form.cleaned_data["image"], request)
            messages.success(request, "Defect photo saved.")
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
    return redirect("inspections:detail", pk=pk)


@role_required(*INSPECTOR_ROLES)
@require_POST
def inspection_submit(request, pk):
    inspection = get_object_or_404(Inspection, pk=pk, inspector=request.user)
    try:
        services.submit_inspection(inspection, request.user, request)
        messages.success(request, "Inspection submitted. Awaiting supervisor approval.")
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    return redirect("inspections:detail", pk=pk)