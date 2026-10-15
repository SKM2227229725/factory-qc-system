from django import forms

from .models import RawMaterialIntake


class IntakeForm(forms.ModelForm):
    requires_lab_test = forms.BooleanField(
        required=False,
        label="Material grade requires lab (spectro) testing",
    )

    class Meta:
        model = RawMaterialIntake
        fields = [
            "supplier", "po_number", "material_grade", "heat_number",
            "quantity", "mtc_file", "mtc_verified",
        ]
        widgets = {
            "supplier": forms.TextInput(attrs={"placeholder": "e.g. Acme Steel"}),
            "po_number": forms.TextInput(attrs={"placeholder": "e.g. PO-2026-001"}),
            "material_grade": forms.TextInput(attrs={"placeholder": "e.g. EN8"}),
            "heat_number": forms.TextInput(attrs={"placeholder": "e.g. H-8042"}),
            "quantity": forms.NumberInput(attrs={"step": "0.01"}),
        }


class RejectIntakeForm(forms.Form):
    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Why is this lot being rejected?"}),
        label="Reason for rejection",
    )