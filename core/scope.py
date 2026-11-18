from django.db.models import Q

from .models import ClassSubject, SchoolClass, Student

# Roles that see every class and student
SCHOOL_WIDE_ROLES = {
    'Head teacher', 'Bursar', 'Exams officer', 'Records officer', 'School administrator',
}

# Roles that see only the classes they lead or teach
CLASS_SCOPED_ROLES = {'Class teacher', 'Subject teacher'}

# Read-only staff are deliberately in neither set, so they see nothing by default.
# If the school wants them to see every class, add 'Read-only staff' to SCHOOL_WIDE_ROLES.


def _roles(user):
    return set(user.groups.values_list('name', flat=True))


def visible_classes(user):
    """Classes this user may see. Anything not explicitly allowed is hidden."""
    if not user or not user.is_authenticated:
        return SchoolClass.objects.none()
    if user.is_superuser:
        return SchoolClass.objects.all()

    roles = _roles(user)
    if roles & SCHOOL_WIDE_ROLES:
        return SchoolClass.objects.all()
    if roles & CLASS_SCOPED_ROLES:
        taught = ClassSubject.objects.filter(teacher=user).values('school_class')
        return SchoolClass.objects.filter(Q(class_teacher=user) | Q(pk__in=taught)).distinct()
    return SchoolClass.objects.none()


def visible_students(user):
    """Students in the classes this user may see."""
    if not user or not user.is_authenticated:
        return Student.objects.none()
    if user.is_superuser or _roles(user) & SCHOOL_WIDE_ROLES:
        return Student.objects.all()
    if _roles(user) & CLASS_SCOPED_ROLES:
        return Student.objects.filter(school_class__in=visible_classes(user))
    return Student.objects.none()