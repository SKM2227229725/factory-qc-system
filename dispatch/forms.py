from django import forms

class DispatchForm(forms.Form):
    customer_po = forms.CharField(max_length=50, label="Customer PO number")
    vehicle_details = forms.CharField(max_length=120, label="Transport vehicle details")
    serial_numbers = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 4}),
        label="Assigned serial numbers (one per line)",
    )