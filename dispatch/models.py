from django.conf import settings
from django.db import models

class Dispatch(models.Model):
    """Shipping manifest plus gate pass."""
    work_order = models.OneToOneField(
        "production.WorkOrder", on_delete=models.PROTECT, related_name="dispatch"
    )
    customer_po = models.CharField("Customer PO number", max_length=50)
    batch_size = models.PositiveIntegerField()
    vehicle_details = models.CharField(max_length=120)
    serial_numbers = models.TextField(help_text="One serial number per line.")
    gate_pass_number = models.CharField(max_length=40, unique=True)
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    issued_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-issued_at"]

    def __str__(self):
        return self.gate_pass_number

    @property
    def serial_list(self):
        return [line.strip() for line in self.serial_numbers.splitlines() if line.strip()]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise PermissionError("Dispatch records cannot be modified.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("Dispatch records cannot be deleted.")