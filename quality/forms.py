from django import forms

from .models import PDITemplate, TemplateField


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