from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from .roles import user_has_role


def role_required(*roles):
    """Allow only logged-in users who belong to one of the given groups.

    Anonymous users are redirected to login. Logged-in users without the
    required role get a 403 (PermissionDenied), not a redirect, so the
    failure is visible and testable.
    """

    def decorator(view):
        @wraps(view)
        @login_required
        def wrapper(request, *args, **kwargs):
            if not user_has_role(request.user, *roles):
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapper

    return decorator