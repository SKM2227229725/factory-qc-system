"""Raw material intake and supplier non-conformance."""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models

MAX_MTC_SIZE_MB = 5


def validate_file_size(file):
    if file.size > MAX_MTC_SIZE_MB * 1024 * 1024:
        raise ValidationError(f"File must be smaller than {MAX_MTC_SIZE_MB} MB.")


class RawMaterialIntake(models.Model):
    class Status(models.TextChoices):
        RECEIVED = "RECEIVED", "Received"
        IN_LAB_TESTING = "IN_LAB", "In Lab Testing"
        CLEARED = "CLEARED", "Cleared"
        QUARANTINED = "QUARANTINED", "Supplier Quarantine"

    supplier = models.CharField(max_length=120)
    po_number = models.CharField("PO number", max_length=50)
    material_grade = models.CharField(max_length=60)
    heat_number = models.CharField(max_length=50, unique=True)
    quantity = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    mtc_file = models.FileField(
        "Mill Test Certificate",
        upload_to="mtc/%Y/%m/",
        validators=[
            FileExtensionValidator(["pdf", "jpg", "jpeg", "png"]),
            validate_file_size,
        ],
    )
    mtc_verified = models.BooleanField(
        "Heat number verified against MTC", default=False
    )
    status = models.CharField(
        max_length=15, choices=Status.choices, default=Status.RECEIVED
    )
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-received_at"]

    def __str__(self):
        return f"{self.heat_number} ({self.material_grade})"

    def clean(self):
        if not self.mtc_verified:
            raise ValidationError(
                {"mtc_verified": "The heat number must be verified against the MTC."}
            )

    @property
    def can_issue_to_production(self):
        return self.status == self.Status.CLEARED


class SupplierNonConformance(models.Model):
    intake = models.OneToOneField(
        RawMaterialIntake, on_delete=models.PROTECT, related_name="sncr"
    )
    reason = models.TextField()
    raised_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"SNCR-{self.pk:05d}"