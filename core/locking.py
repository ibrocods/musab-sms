from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from .models import ResultLock
from .permissions import can


def is_locked(class_subject, term):
    return ResultLock.objects.filter(class_subject=class_subject, term=term, is_locked=True).exists()


def set_lock(class_subject, term, locking, user, reason=''):
    """Lock or unlock one subject's results for one term.

    Only users with the lock_results capability can do this. Unlocking needs a reason.
    """
    if not can(user, 'lock_results'):
        raise PermissionDenied

    lock, _ = ResultLock.objects.get_or_create(class_subject=class_subject, term=term)
    now = timezone.now()

    if locking:
        if lock.is_locked:
            return
        lock.is_locked = True
        lock.locked_by = user
        lock.locked_at = now
    else:
        reason = reason.strip()
        if not reason:
            raise ValidationError('Give a reason for unlocking the results.')
        if not lock.is_locked:
            return
        lock.is_locked = False
        lock.unlocked_by = user
        lock.unlocked_at = now
        lock.unlock_reason = reason

    lock.save()