import secrets

from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied
from django.db import transaction

from core.models import AuditLog, ClassSubject, SchoolClass
from core.permissions import ROLE_CAPABILITIES, can

# Easy to read aloud: no 0/O or 1/l/I
PASSWORD_ALPHABET = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'


def generate_password(length=10):
    return ''.join(secrets.choice(PASSWORD_ALPHABET) for _ in range(length))


def create_staff(*, actor, username, first_name, last_name, email, role, class_led, teaching):
    """Create a staff account with its role and assignments.

    The password is returned once and is never written to the audit log.
    """
    if not can(actor, 'manage_staff'):
        raise PermissionDenied

    password = generate_password()
    with transaction.atomic():
        user = User.objects.create_user(
            username=username, email=email, password=password,
            first_name=first_name, last_name=last_name,
        )
        user.groups.add(Group.objects.get(name=role))

        if role == 'Class teacher' and class_led:
            # Replaces any previous class teacher. The class audit entry records the change.
            class_led.class_teacher = user
            class_led.save()

        if role == 'Subject teacher':
            for link in teaching:
                link.teacher = user
                link.save()

        AuditLog.objects.create(
            user=actor,
            username=actor.get_username(),
            action='create',
            model_name='auth.user',
            object_id=str(user.pk),
            object_repr=user.get_username(),
            changes={'role': role},
        )
    return user, password


def staff_rows():
    """Everyone with a staff role, with the classes and subjects they're responsible for."""
    users = (
        User.objects.filter(groups__name__in=list(ROLE_CAPABILITIES))
        .distinct()
        .order_by('last_name', 'first_name', 'username')
        .prefetch_related('groups')
    )
    rows = []
    for user in users:
        role = next((g.name for g in user.groups.all() if g.name in ROLE_CAPABILITIES), '')
        classes = list(SchoolClass.objects.filter(class_teacher=user).values_list('name', flat=True))
        subjects = [
            f'{link.subject.name} in {link.school_class.name}'
            for link in ClassSubject.objects.filter(teacher=user).select_related('subject', 'school_class')
        ]
        rows.append({'user': user, 'role': role, 'classes': classes, 'subjects': subjects})
    return rows