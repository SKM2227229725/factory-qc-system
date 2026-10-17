from django import forms
from django.core.validators import FileExtensionValidator

from materials.models import validate_file_size
from .models import PDITemplate, TemplateField, Concession, MRBDisposition
class PDITemplateForm(forms.ModelForm):
    class Meta:
        model = PDITemplate
        fields = ["part", "revision", "blueprint"]
        widgets = {
            "revision": forms.TextInput(attrs={"placeholder": "e.g. A"}),
        }


class TemplateFieldForm(forms.ModelForm):
    class Meta:
        model = TemplateField
        fields = [
            "name", "field_type", "nominal", "upper_tol",
            "lower_tol", "limit_value", "unit", "is_ctq",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "e.g. Shaft diameter"}),
            "unit": forms.TextInput(attrs={"placeholder": "e.g. mm"}),
        }
        help_texts = {
            "upper_tol": "Offset from nominal, e.g. 0.05",
            "lower_tol": "Offset from nominal, e.g. -0.02",
            "limit_value": "Only for Maximum / Minimum fields.",
        }


class RemarksForm(forms.Form):
    remarks = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Explain what needs to change"}),
        label="Remarks",
    )
    
    

# ---------------------------------------------------------------------------
# Inspection forms (Phase 3C)
# ---------------------------------------------------------------------------

from materials.models import validate_file_size  # noqa: E402
from .models import InspectionReading, TemplateField  # noqa: E402


class StartInspectionForm(forms.Form):
    station_code = forms.CharField(
        max_length=30, label="Station code (machine QR plate)"
    )
    job_code = forms.CharField(max_length=30, label="Job traveler code")


class ReadingForm(forms.Form):
    def __init__(self, template_field, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if template_field.field_type == TemplateField.FieldType.PASS_FAIL:
            self.fields["result"] = forms.ChoiceField(
                choices=[("PASS", "Pass"), ("FAIL", "Fail")],
                widget=forms.RadioSelect,
            )
        else:
            self.fields["value"] = forms.DecimalField(
                max_digits=10, decimal_places=4, label="Measured value",
                widget=forms.NumberInput(attrs={"step": "any", "inputmode": "decimal"}),
            )
            self.fields["gauge_serial"] = forms.CharField(
                max_length=30, label="Gauge serial (e.g. VC-104)"
            )


class PhotoForm(forms.Form):
    image = forms.ImageField(validators=[validate_file_size])
    


# ---------------------------------------------------------------------------
# Review and MRB forms (Phase 4A)
# ---------------------------------------------------------------------------

class ConcessionForm(forms.Form):
    reason_code = forms.ChoiceField(choices=Concession.ReasonCode.choices)
    justification = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Explain why this out-of-tolerance dimension is acceptable."}),
        label="Engineering justification",
    )


class DispositionForm(forms.Form):
    decision = forms.ChoiceField(choices=MRBDisposition.Decision.choices)
    notes = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Disposition notes"}),
        label="Notes"
    )
    customer_approval = forms.FileField(
        required=False,
        label="Customer written approval (only for Customer Special Concession)",
        validators=[FileExtensionValidator(["pdf", "jpg", "jpeg", "png"]), validate_file_size],
    )