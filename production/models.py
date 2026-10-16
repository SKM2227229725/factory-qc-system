"""Work orders, routing, and the operations on the digital traveler.

A WorkOrder is released against a Cleared heat lot and a specific PDI
template revision. The routing steps are copied onto the work order at
release time, so later edits to the master routing do not affect jobs
already on the floor (BRD §7.1).
"""

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class RoutingStep(models.Model):
    """Master routing: the ordered operations a part goes through."""

    part = models.ForeignKey(
        "plant.Part", on_delete=models.PROTECT, related_name="routing_steps"
    )
    op_number = models.PositiveSmallIntegerField(help_text="e.g. 10, 20, 30")
    name = models.CharField(max_length=100)
    hold_minutes = models.PositiveIntegerField(
        default=0,
        help_text="Mandatory cooling/curing hold after this operation (BRD §8.1).",
    )

    class Meta:
        ordering = ["part", "op_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["part", "op_number"], name="unique_routing_op_per_part"
            )
        ]

    def __str__(self):
        return f"{self.part} Op {self.op_number}: {self.name}"


class WorkOrder(models.Model):
    class Status(models.TextChoices):
        RELEASED = "RELEASED", "Released"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        QUARANTINED = "QUARANTINED", "Quarantined"
        COMPLETED = "COMPLETED", "Completed"
        DISPATCHED = "DISPATCHED", "Dispatched"

    number = models.CharField(max_length=30, unique=True)
    part = models.ForeignKey(
        "plant.Part", on_delete=models.PROTECT, related_name="work_orders"
    )
    intake = models.ForeignKey(
        "materials.RawMaterialIntake",
        on_delete=models.PROTECT,
        related_name="work_orders",
        verbose_name="Raw material heat lot",
    )
    pdi_template = models.ForeignKey(
        "quality.PDITemplate",
        on_delete=models.PROTECT,
        related_name="work_orders",
    )
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.RELEASED
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.number

    def completed_operations(self):
        return self.operations.filter(
            status=WorkOrderOperation.Status.COMPLETED
        ).count()


class WorkOrderOperation(models.Model):
    """One operation on the digital traveler. Start/complete logic is in services."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        COMPLETED = "COMPLETED", "Completed"

    work_order = models.ForeignKey(
        WorkOrder, on_delete=models.PROTECT, related_name="operations"
    )
    op_number = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=100)
    hold_minutes = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.PENDING
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    hold_until = models.DateTimeField(
        null=True, blank=True,
        help_text="Earliest time the next operation can start (BRD §8.2).",
    )
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.PROTECT, related_name="+",
    )
    workstation = models.ForeignKey(
        "plant.Workstation",
        null=True, blank=True,
        on_delete=models.PROTECT, related_name="+",
    )
    shift = models.CharField(max_length=10, blank=True)

    class Meta:
        ordering = ["op_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["work_order", "op_number"],
                name="unique_op_per_work_order",
            )
        ]

    def __str__(self):
        return f"{self.work_order} Op {self.op_number}"

    @property
    def is_hold_active(self):
        from django.utils import timezone
        return self.hold_until is not None and self.hold_until > timezone.now()

    def previous_operation(self):
        return (
            WorkOrderOperation.objects.filter(
                work_order=self.work_order, op_number__lt=self.op_number
            )
            .order_by("-op_number")
            .first()
        )