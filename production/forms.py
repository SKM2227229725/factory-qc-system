from django import forms

from materials.models import RawMaterialIntake

from .models import WorkOrder


class WorkOrderForm(forms.ModelForm):
    class Meta:
        model = WorkOrder
        fields = ["number", "part", "intake", "quantity"]
        widgets = {
            "number": forms.TextInput(attrs={"placeholder": "e.g. WO-1001"}),
            "quantity": forms.NumberInput(attrs={"min": 1}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only Cleared lots can be selected. The service re-checks anyway.
        self.fields["intake"].queryset = RawMaterialIntake.objects.filter(
            status=RawMaterialIntake.Status.CLEARED
        )
        self.fields["intake"].label = "Raw material heat lot (Cleared only)"


class StartOperationForm(forms.Form):
    workstation_code = forms.CharField(
        max_length=30,
        label="Station code (machine QR plate)",
        widget=forms.TextInput(attrs={"placeholder": "e.g. WS-04"}),
    )