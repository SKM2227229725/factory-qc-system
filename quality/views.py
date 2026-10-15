from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts import roles
from accounts.decorators import role_required
from accounts.roles import user_has_role

from . import services
from .forms import PDITemplateForm, RemarksForm, TemplateFieldForm
from .models import PDITemplate, TemplateField

EDIT_ROLES = (roles.QUALITY_ENGINEER,)
REVIEW_ROLES = (roles.QUALITY_MANAGER,)


@login_required
def template_list(request):
    templates = PDITemplate.objects.select_related("part", "created_by").annotate(
        field_count=Count("fields")
    )
    return render(request, "quality/template_list.html", {
        "templates": templates,
        "can_create": user_has_role(request.user, *EDIT_ROLES),
    })


@login_required
def template_detail(request, pk):
    pdi = get_object_or_404(PDITemplate.objects.select_related("part"), pk=pk)
    return render(request, "quality/template_detail.html", {
        "pdi": pdi,
        "fields": pdi.fields.all(),
        "can_edit": pdi.is_editable and user_has_role(request.user, *EDIT_ROLES),
        "can_review": pdi.status == PDITemplate.Status.PENDING
            and user_has_role(request.user, *REVIEW_ROLES),
    })


@role_required(*EDIT_ROLES)
def template_create(request):
    form = PDITemplateForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        pdi = services.create_template(form.save(commit=False), request.user, request)
        messages.success(request, f"{pdi} created as Draft. Add inspection fields next.")
        return redirect("quality:template_detail", pk=pdi.pk)
    return render(request, "quality/template_form.html", {"form": form})


@role_required(*EDIT_ROLES)
def field_add(request, pk):
    pdi = get_object_or_404(PDITemplate, pk=pk)
    if not pdi.is_editable:
        messages.error(request, "Only Draft templates can be edited. Create a new revision.")
        return redirect("quality:template_detail", pk=pk)
    form = TemplateFieldForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            services.add_field(pdi, form.save(commit=False), request.user, request)
            messages.success(request, "Inspection field added.")
            return redirect("quality:template_detail", pk=pk)
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
    return render(request, "quality/field_form.html", {"form": form, "pdi": pdi})


@role_required(*EDIT_ROLES)
@require_POST
def field_remove(request, pk, field_pk):
    field = get_object_or_404(TemplateField, pk=field_pk, template_id=pk)
    try:
        services.remove_field(field, request.user, request)
        messages.success(request, "Field removed.")
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    return redirect("quality:template_detail", pk=pk)


def _run_transition(request, pk, action, success_message):
    pdi = get_object_or_404(PDITemplate, pk=pk)
    try:
        action(pdi, request.user, request=request)
        messages.success(request, success_message)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    return redirect("quality:template_detail", pk=pk)


@role_required(*EDIT_ROLES)
@require_POST
def template_submit(request, pk):
    return _run_transition(request, pk, services.submit_for_approval,
                           "Submitted for Quality Manager approval.")


@role_required(*REVIEW_ROLES)
@require_POST
def template_approve(request, pk):
    return _run_transition(request, pk, services.approve_template,
                           "Template approved and released.")


@role_required(*REVIEW_ROLES)
def template_reject(request, pk):
    pdi = get_object_or_404(PDITemplate, pk=pk)
    form = RemarksForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            services.reject_template(
                pdi, request.user, form.cleaned_data["remarks"], request
            )
            messages.warning(request, "Template returned to Draft with your remarks.")
            return redirect("quality:template_detail", pk=pk)
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
    return render(request, "quality/template_reject.html", {"form": form, "pdi": pdi})