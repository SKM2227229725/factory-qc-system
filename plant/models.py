"""Plant master data: factories, workstations, parts, gauges."""

from django.db import models
from django.utils import timezone


class Factory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name_plural = "factories"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Workstation(models.Model):
    factory = models.ForeignKey(
        Factory, on_delete=models.PROTECT, related_name="workstations"
    )
    name = models.CharField(max_length=100)
    code = models.CharField(
        max_length=30, unique=True,
        help_text="Printed on the station QR plate. Example: WS-CNC-04",
    )
    pm_due_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["factory", "code"]

    def __str__(self):
        return f"{self.code} - {self.name}"

    @property
    def is_pm_overdue(self):
        if self.pm_due_date is None:
            return False
        return self.pm_due_date < timezone.localdate()


class Part(models.Model):
    part_number = models.CharField(max_length=50, unique=True)
    description = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["part_number"]

    def __str__(self):
        return self.part_number


class Gauge(models.Model):
    serial = models.CharField(max_length=30, unique=True)
    gauge_type = models.CharField(max_length=60)
    calibration_expiry = models.DateField()

    class Meta:
        ordering = ["serial"]

    def __str__(self):
        return f"{self.serial} ({self.gauge_type})"

    @property
    def is_calibration_valid(self):
        return self.calibration_expiry >= timezone.localdate()