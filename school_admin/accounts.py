import secrets

from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from core.models import AccountSecurity, AuditLog, ClassSubject, SchoolClass
from core.permissions import ROLE_CAPABILITIES, can

from .staff import PASSWORD_ALPHABET


def _temporary_password(length=10):
    return ''.join(secrets.choice(PASSWORD_ALPHABET) for _ in range(length))


def _is_administrator(user):
    return user.groups.filter(name='School administrator').exists()


def _active_administrators():
    return User.objects.filter(
        is_active=True, groups__name='School administrator',
    ).distinct()


def _log(actor, target, action, changes):
    AuditLog.objects.create(
        user=actor,
        username=actor.get_username(),
        action=action,
        model_name='auth.user',
        object_id=str(target.pk),
        object_repr=target.get_username(),
        changes=changes,
    )


def _release_assignments(user):
    """Remove the user from the classes and subjects they were responsible for."""
    for school_class in SchoolClass.objects.filter(class_teacher=user):
        school_class.class_teacher = None
        school_class.save()
    for link in ClassSubject.objects.filter(teacher=user):
        link.teacher = None
        link.save()


def deactivate_staff(*, actor, target):
    if not can(actor, 'manage_staff'):
        raise PermissionDenied
    if target == actor:
        raise ValidationError('You cannot deactivate your own account.')
    if not target.is_active:
        raise ValidationError('This account is already inactive.')
    if _is_administrator(target) and _active_administrators().count() <= 1:
        raise ValidationError(
            'This is the only active School administrator. Add another administrator first.'
        )

    with transaction.atomic():
        _release_assignments(target)
        target.is_active = False
        target.save()
        _log(actor, target, 'update', {'is_active': [True, False]})


def reactivate_staff(*, actor, target):
    if not can(actor, 'manage_staff'):
        raise PermissionDenied
    if target.is_active:
        raise ValidationError('This account is already active.')

    with transaction.atomic():
        target.is_active = True
        target.save()
        _log(actor, target, 'update', {'is_active': [False, True]})


def reset_password(*, actor, target):
    """Set a temporary password that must be changed at the next sign-in.

    Returns the temporary password once. It is never written to the audit log.
    """
    if not can(actor, 'manage_staff'):
        raise PermissionDenied
    if target == actor:
        raise ValidationError('Use the change password page for your own account.')

    password = _temporary_password()
    with transaction.atomic():
        target.set_password(password)
        target.save()
        security, _ = AccountSecurity.objects.get_or_create(user=target)
        security.must_change_password = True
        security.password_changed_at = None
        security.save()
        _log(actor, target, 'update', {'password': ['(hidden)', '(reset)']})
    return password


def update_details(*, actor, target, first_name, last_name, email, role, class_led, teaching):
    """Change name, email, role and assignments. Changing a role clears the old assignments."""
    if not can(actor, 'manage_staff'):
        raise PermissionDenied
    if role not in ROLE_CAPABILITIES:
        raise ValidationError('Choose a valid role.')
    if target == actor and role != 'School administrator' and _is_administrator(target):
        if _active_administrators().count() <= 1:
            raise ValidationError('You are the only active School administrator and cannot remove that role.')

    with transaction.atomic():
        changes = {}
        for field, value in (('first_name', first_name), ('last_name', last_name), ('email', email)):
            before = getattr(target, field)
            if before != value:
                changes[field] = [before, value]
                setattr(target, field, value)
        target.save()

        current = target.groups.filter(name__in=list(ROLE_CAPABILITIES)).first()
        if current is None or current.name != role:
            if current:
                target.groups.remove(current)
            target.groups.add(Group.objects.get(name=role))
            changes['role'] = [current.name if current else None, role]
            _release_assignments(target)

        if role == 'Class teacher' and class_led:
            if class_led.class_teacher_id != target.pk:
                class_led.class_teacher = target
                class_led.save()
        if role == 'Subject teacher':
            wanted = set(link.pk for link in teaching)
            for link in ClassSubject.objects.filter(teacher=target):
                if link.pk not in wanted:
                    link.teacher = None
                    link.save()
            for link in teaching:
                if link.teacher_id != target.pk:
                    link.teacher = target
                    link.save()

        if changes:
            _log(actor, target, 'update', changes)
    return target