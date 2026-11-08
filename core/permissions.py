from datetime import timedelta
from functools import wraps

from django.core.exceptions import PermissionDenied
from django.utils import timezone

# Which capabilities each role gets. Change this map to change what a role can do.
# The Administrator is the superuser account, which can do everything.
ROLE_CAPABILITIES = {
    'Head teacher': [
        'view_students', 'view_attendance', 'view_grades',
        'lock_results', 'approve_report_cards', 'view_fees',
    ],
    'Bursar': ['view_students', 'view_fees', 'collect_fees'],
    'Class teacher': [
        'view_students', 'view_attendance', 'mark_attendance',
        'view_grades', 'enter_grades', 'comment_report_cards',
    ],
    'Subject teacher': ['view_students', 'view_grades', 'enter_grades'],
    'Exams officer': [
        'view_students', 'view_grades', 'setup_assessments',
        'lock_results', 'generate_report_cards',
    ],
    'Records officer': ['view_students', 'manage_students'],
    'Read-only staff': ['view_students', 'view_attendance', 'view_grades'],
}


def can(user, capability):
    """The single place where access is checked. Every feature calls this."""
    from .models import TemporaryGrant

    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    # Covers capabilities from the user's groups and any direct permissions
    if user.has_perm(f'core.{capability}'):
        return True

    now = timezone.now()
    return TemporaryGrant.objects.filter(
        user=user,
        capability=capability,
        revoked_at__isnull=True,
        starts_at__lte=now,
        ends_at__gt=now,
    ).exists()


def require_capability(capability):
    """Use on a view to block users who don't have the capability."""
    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not can(request.user, capability):
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return wrapper
    return decorator