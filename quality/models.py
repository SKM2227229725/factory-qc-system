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