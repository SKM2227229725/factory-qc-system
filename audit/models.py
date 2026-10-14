"""Append-only audit log."""

from django.conf import settings
from django.db import models


class AppendOnlyQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise PermissionError("Audit records cannot be modified.")

    def delete(self):
        raise PermissionError("Audit records cannot be deleted.")


class AuditLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.PROTECT, related_name="+",
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    action = models.CharField(max_length=60, db_index=True)
    object_type = models.CharField(max_length=60)
    object_id = models.CharField(max_length=40)
    old_value = models.TextField(blank=True)
    new_value = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        ordering = ["-timestamp"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise PermissionError("Audit records cannot be modified.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("Audit records cannot be deleted.")

    def __str__(self):
        return f"{self.timestamp:%Y-%m-%d %H:%M} {self.action} {self.object_type}#{self.object_id}"