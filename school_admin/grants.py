from datetime import datetime, time, timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from core.capabilities import CAPABILITIES
from core.models import TemporaryGrant
from core.permissions import can

MAX_GRANT_DAYS = 90

# Staff management can only come from a role, never as a temporary grant.
# Otherwise someone could widen their own access without a permanent role change.
NEVER_TEMPORARY = {'manage_staff'}


def end_of_day(day):
    """The last moment of a chosen date, in the school's timezone."""
    naive = datetime.combine(day, time(23, 59, 59))
    return timezone.make_aware(naive, timezone.get_current_timezone())


def grant_temporary(*, actor, target, capability, reason, ends_on):
    if not can(actor, 'manage_staff'):
        raise PermissionDenied
    if target == actor:
        raise ValidationError('You cannot give temporary access to your own account.')
    if not target.is_active:
        raise ValidationError('This account is inactive. Reactivate it first.')
    if capability not in CAPABILITIES:
        raise ValidationError('Choose a valid permission.')
    if capability in NEVER_TEMPORARY:
        raise ValidationError('This permission can only come from a role, not as temporary access.')

    reason = (reason or '').strip()
    if not reason:
        raise ValidationError('Give a reason for the temporary access.')

    now = timezone.now()
    ends_at = end_of_day(ends_on)
    if ends_at <= now:
        raise ValidationError('The end date must be today or later.')
    if ends_at > now + timedelta(days=MAX_GRANT_DAYS):
        raise ValidationError(f'Temporary access can last at most {MAX_GRANT_DAYS} days.')

    with transaction.atomic():
        return TemporaryGrant.objects.create(
            user=target,
            capability=capability,
            reason=reason[:200],
            granted_by=actor,
            starts_at=now,
            ends_at=ends_at,
        )


def revoke_grant(*, actor, grant):
    """End a grant now. The record is kept, and the change is logged."""
    if not can(actor, 'manage_staff'):
        raise PermissionDenied
    if grant.revoked_at is not None:
        raise ValidationError('This access has already been ended.')
    if grant.ends_at <= timezone.now():
        raise ValidationError('This access has already expired.')
    grant.revoked_at = timezone.now()
    grant.save()
    return grant