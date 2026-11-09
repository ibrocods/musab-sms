from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .middleware import get_current_user
from .models import AuditLog, SchoolClass, SchoolProfile, Student, TemporaryGrant, Term

TRACKED = (SchoolProfile, SchoolClass, Student, Term, TemporaryGrant)


def _clean(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _snapshot(instance):
    return {f.attname: _clean(getattr(instance, f.attname)) for f in instance._meta.concrete_fields}


def _write(sender, instance, action, changes):
    user = get_current_user()
    if user is not None and user.is_authenticated:
        user_id, username = user.pk, user.get_username()
    else:
        user_id, username = None, ''
    AuditLog.objects.create(
        user_id=user_id,
        username=username,
        action=action,
        model_name=sender._meta.label_lower,
        object_id=str(instance.pk),
        object_repr=str(instance)[:255],
        changes=changes,
    )


@receiver(pre_save)
def capture_before(sender, instance, **kwargs):
    # Keep the stored values so we can list what changed after the save
    instance._audit_before = {}
    if sender in TRACKED and instance.pk:
        old = sender.objects.filter(pk=instance.pk).first()
        if old:
            instance._audit_before = _snapshot(old)


@receiver(post_save)
def log_save(sender, instance, created, **kwargs):
    if sender not in TRACKED:
        return
    after = _snapshot(instance)
    if created:
        _write(sender, instance, 'create', {k: v for k, v in after.items() if v not in (None, '')})
        return
    before = getattr(instance, '_audit_before', {})
    changes = {k: [before.get(k), v] for k, v in after.items() if before.get(k) != v}
    if changes:
        _write(sender, instance, 'update', changes)


@receiver(post_delete)
def log_delete(sender, instance, **kwargs):
    if sender in TRACKED:
        _write(sender, instance, 'delete', {})


@receiver(user_logged_in)
def log_login(sender, request, user, **kwargs):
    AuditLog.objects.create(
        user=user, username=user.get_username(), action='login',
        model_name='auth.user', object_id=str(user.pk), object_repr=user.get_username(),
    )


@receiver(user_logged_out)
def log_logout(sender, request, user, **kwargs):
    if user is None:
        return
    AuditLog.objects.create(
        user=user, username=user.get_username(), action='logout',
        model_name='auth.user', object_id=str(user.pk), object_repr=user.get_username(),
    )