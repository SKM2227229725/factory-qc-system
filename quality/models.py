"""PDI checklist templates and their inspection fields.

A template belongs to one part and carries a revision (A, B, C...).
Only an approved revision can be used on the shopfloor; approving a new
revision automatically supersedes the previous one (BRD §4.1).
"""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models
from django.db.models import Q

from materials.models import validate_file_size


class PDITemplate(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PENDING = "PENDING", "Pending approval"
        APPROVED = "APPROVED", "Approved"
        SUPERSEDED = "SUPERSEDED", "Superseded"

    part = models.ForeignKey(
        "plant.Part", on_delete=models.PROTECT, related_name="pdi_templates"
    )
    revision = models.CharField(max_length=10, help_text="e.g. A, B, C")
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.DRAFT
    )
    blueprint = models.FileField(
        upload_to="blueprints/%Y/%m/",
        blank=True,
        validators=[FileExtensionValidator(["pdf"]), validate_file_size],
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.PROTECT, related_name="+",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    review_remarks = models.TextField(blank=True)

    class Meta:
        ordering = ["part__part_number", "-revision"]
        constraints = [
            models.UniqueConstraint(
                fields=["part", "revision"], name="unique_template_revision"
            ),
            # At most one live revision per part.
            models.UniqueConstraint(
                fields=["part"],
                condition=Q(status="APPROVED"),
                name="one_approved_template_per_part",
            ),
        ]

    def __str__(self):
        return f"{self.part} Rev {self.revision}"

    @property
    def is_editable(self):
        return self.status == self.Status.DRAFT


class TemplateField(models.Model):
    class FieldType(models.TextChoices):
        TOLERANCE = "TOLERANCE", "Dimension with +/- tolerance"
        MAX = "MAX", "Maximum limit"
        MIN = "MIN", "Minimum limit"
        PASS_FAIL = "PASS_FAIL", "Visual Pass / Fail"

    template = models.ForeignKey(
        PDITemplate, on_delete=models.PROTECT, related_name="fields"
    )
    sequence = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=100)
    field_type = models.CharField(max_length=10, choices=FieldType.choices)
    nominal = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    upper_tol = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    lower_tol = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    limit_value = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    unit = models.CharField(max_length=15, blank=True)
    is_ctq = models.BooleanField("Critical-to-Quality (CTQ)", default=False)

    class Meta:
        ordering = ["sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["template", "sequence"], name="unique_field_sequence"
            )
        ]

    def __str__(self):
        return f"{self.sequence}. {self.name}"

    def clean(self):
        errors = {}
        if self.field_type == self.FieldType.TOLERANCE:
            for name in ("nominal", "upper_tol", "lower_tol"):
                if getattr(self, name) is None:
                    errors[name] = "Required for a tolerance dimension."
            if not errors and self.upper_tol <= self.lower_tol:
                errors["upper_tol"] = "Upper tolerance must be greater than lower tolerance."
        elif self.field_type in (self.FieldType.MAX, self.FieldType.MIN):
            if self.limit_value is None:
                errors["limit_value"] = "A limit value is required."
        if errors:
            raise ValidationError(errors)

    def evaluate(self, value):
        """Return True if a numeric reading is within limits (inclusive)."""
        value = Decimal(str(value))
        if self.field_type == self.FieldType.TOLERANCE:
            low = self.nominal + self.lower_tol
            high = self.nominal + self.upper_tol
            return low <= value <= high
        if self.field_type == self.FieldType.MAX:
            return value <= self.limit_value
        if self.field_type == self.FieldType.MIN:
            return value >= self.limit_value
        raise ValueError("Pass/Fail fields have no numeric limits.")

    @property
    def spec_display(self):
        if self.field_type == self.FieldType.TOLERANCE:
            return f"{self.nominal:g} ({self.upper_tol:+g} / {self.lower_tol:+g}) {self.unit}"
        if self.field_type == self.FieldType.MAX:
            return f"{self.limit_value:g} MAX {self.unit}"
        if self.field_type == self.FieldType.MIN:
            return f"{self.limit_value:g} MIN {self.unit}"
        return "Pass / Fail"

    def _template_is_draft(self):
        return PDITemplate.objects.filter(
            pk=self.template_id, status=PDITemplate.Status.DRAFT
        ).exists()

    def save(self, *args, **kwargs):
        # Released templates are frozen; create a new revision instead.
        if self.pk is None and not PDITemplate.objects.filter(
            pk=self.template_id, status=PDITemplate.Status.DRAFT
        ).exists():
            raise ValidationError(
                "Fields can only be added to a Draft template."
            )
        if self.pk is not None and not self._template_is_draft():
            raise ValidationError(
                "Fields can only be changed on a Draft template."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if not self._template_is_draft():
            raise ValidationError("Fields cannot be removed from a released template.")
        super().delete(*args, **kwargs)
        
        

# ---------------------------------------------------------------------------
# Inspection models (Phase 3C)
# ---------------------------------------------------------------------------

class Inspection(models.Model):
    class Status(models.TextChoices):
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        PENDING_REVIEW = "PENDING_REVIEW", "Awaiting Approval"
        APPROVED = "APPROVED", "Approved"
        CONCEDED = "CONCEDED", "Approved with Concession"
        REJECTED = "REJECTED", "Rejected / Quarantined"

    work_order = models.ForeignKey(
        "production.WorkOrder", on_delete=models.PROTECT, related_name="inspections"
    )
    template = models.ForeignKey(
        PDITemplate, on_delete=models.PROTECT, related_name="inspections"
    )
    workstation = models.ForeignKey(
        "plant.Workstation", on_delete=models.PROTECT, related_name="inspections"
    )
    inspector = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="inspections"
    )
    status = models.CharField(
        max_length=15, choices=Status.choices, default=Status.IN_PROGRESS
    )
    ctq_frozen = models.BooleanField(default=False)
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["inspector"],
                condition=Q(status="IN_PROGRESS"),
                name="one_open_inspection_per_inspector",
            )
        ]

    def __str__(self):
        return f"Inspection #{self.pk} ({self.work_order})"

    def next_field(self):
        done = self.readings.values_list("template_field_id", flat=True)
        return self.template.fields.exclude(pk__in=done).first()


class InspectionReading(models.Model):
    inspection = models.ForeignKey(
        Inspection, on_delete=models.PROTECT, related_name="readings"
    )
    template_field = models.ForeignKey(
        TemplateField, on_delete=models.PROTECT, related_name="+"
    )
    measured_value = models.DecimalField(
        max_digits=10, decimal_places=4, null=True, blank=True
    )
    passed = models.BooleanField()
    gauge = models.ForeignKey(
        "plant.Gauge", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["template_field__sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["inspection", "template_field"], name="one_reading_per_field"
            )
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise PermissionError("Submitted readings cannot be modified.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("Readings cannot be deleted.")

    def __str__(self):
        return f"{self.template_field.name}: {'PASS' if self.passed else 'FAIL'}"


class DefectPhoto(models.Model):
    reading = models.ForeignKey(
        InspectionReading, on_delete=models.PROTECT, related_name="photos"
    )
    image = models.ImageField(
        upload_to="defects/%Y/%m/", validators=[validate_file_size]
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise PermissionError("Defect photos cannot be modified.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("Defect photos cannot be deleted.")
    

# ---------------------------------------------------------------------------
# Supervisor review and MRB models (Phase 4A)
# ---------------------------------------------------------------------------

class SupervisorReview(models.Model):
    class Decision(models.TextChoices):
        APPROVED = "APPROVED", "Approved"
        CONCEDED = "CONCEDED", "Approved with Concession"
        REJECTED = "REJECTED", "Rejected"

    inspection = models.OneToOneField(
        Inspection, on_delete=models.PROTECT, related_name="review"
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    decision = models.CharField(max_length=10, choices=Decision.choices)
    remarks = models.TextField(blank=True)
    decided_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise PermissionError("Review decisions cannot be modified.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("Review decisions cannot be deleted.")

    def __str__(self):
        return f"Review #{self.pk} - {self.get_decision_display()}"


class Concession(models.Model):
    class ReasonCode(models.TextChoices):
        COSMETIC = "COSMETIC", "Cosmetic / appearance only"
        FUNCTIONAL_OK = "FUNCTIONAL_OK", "Functionally acceptable to customer"
        MARGINAL_DIMENSION = "MARGINAL", "Non-critical dimension marginally out"
        OTHER = "OTHER", "Other (explain in justification)"

    inspection = models.OneToOneField(
        Inspection, on_delete=models.PROTECT, related_name="concession"
    )
    reason_code = models.CharField(max_length=20, choices=ReasonCode.choices)
    justification = models.TextField()
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    issued_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise PermissionError("Concessions cannot be modified.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("Concessions cannot be deleted.")

    def __str__(self):
        return f"Concession on #{self.inspection_id}"


class MRBDisposition(models.Model):
    class Decision(models.TextChoices):
        REWORK = "REWORK", "Rework"
        SCRAP = "SCRAP", "Scrap"
        RTV = "RTV", "Return to Vendor"
        CUSTOMER_CONCESSION = "CUSTOMER_CONCESSION", "Customer Special Concession"

    inspection = models.OneToOneField(
        Inspection, on_delete=models.PROTECT, related_name="disposition"
    )
    decision = models.CharField(max_length=20, choices=Decision.choices)
    notes = models.TextField()
    customer_approval = models.FileField(
        upload_to="customer_approvals/%Y/%m/",
        blank=True,
        validators=[
            FileExtensionValidator(["pdf", "jpg", "jpeg", "png"]),
            validate_file_size,
        ],
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    decided_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise PermissionError("MRB dispositions cannot be modified.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("MRB dispositions cannot be deleted.")

    def __str__(self):
        return f"MRB Disposition #{self.pk} - {self.get_decision_display()}"