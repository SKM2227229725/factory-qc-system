"""Helper for writing audit entries.

Call record() inside the same transaction as the state change so the log
entry and the change commit or roll back together.
"""

from .models import AuditLog


def _client_ip(request):
    if request is None:
        return None
    return request.META.get("REMOTE_ADDR")


def record(action, obj, user=None, request=None, old_value="", new_value=""):
    """Write one audit row for a change to obj. Returns the row."""
    return AuditLog.objects.create(
        user=user,
        action=action,
        object_type=obj.__class__.__name__,
        object_id=str(obj.pk),
        old_value=str(old_value or ""),
        new_value=str(new_value or ""),
        ip_address=_client_ip(request),
    )