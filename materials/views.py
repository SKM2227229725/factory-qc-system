from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts import roles
from accounts.decorators import role_required

from . import services
from .forms import IntakeForm, RejectIntakeForm
from .models import RawMaterialIntake

INTAKE_ROLES = (roles.DOCK_CLERK, roles.QUALITY_ENGINEER, roles.QUALITY_MANAGER)
CLEARING_ROLES = (roles.QUALITY_ENGINEER, roles.QUALITY_MANAGER)


@login_required
def intake_list(request):
    intakes = RawMaterialIntake.objects.select_related("received_by")
    return render(request, "materials/intake_list.html", {"intakes": intakes})


@login_required
def intake_detail(request, pk):
    intake = get_object_or_404(RawMaterialIntake, pk=pk)
    return render(request, "materials/intake_detail.html", {"intake": intake})


@role_required(*INTAKE_ROLES)
def intake_create(request):
    form = IntakeForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        intake = services.register_intake(
            form.save(commit=False),
            request.user,
            form.cleaned_data["requires_lab_test"],
            request,
        )
        messages.success(request, f"Intake for heat {intake.heat_number} saved.")
        return redirect("materials:detail", pk=intake.pk)
    return render(request, "materials/intake_form.html", {"form": form})


@role_required(*CLEARING_ROLES)
@require_POST
def intake_clear(request, pk):
    intake = get_object_or_404(RawMaterialIntake, pk=pk)
    try:
        services.clear_intake(intake, request.user, request)
        messages.success(request, f"Heat {intake.heat_number} cleared for production.")
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    return redirect("materials:detail", pk=pk)


@role_required(*INTAKE_ROLES)
def intake_reject(request, pk):
    intake = get_object_or_404(RawMaterialIntake, pk=pk)
    form = RejectIntakeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            sncr = services.reject_intake(
                intake, request.user, form.cleaned_data["reason"], request
            )
            messages.warning(request, f"Intake rejected and quarantined. {sncr} raised.")
            return redirect("materials:detail", pk=pk)
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
    return render(request, "materials/intake_reject.html", {"form": form, "intake": intake})