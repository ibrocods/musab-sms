from .models import SchoolClass, Student

# Roles whose members only see the classes they teach
SCOPED_ROLES = {'Class teacher'}


def visible_classes(user):
    """Return the classes this user is allowed to see."""
    if not user or not user.is_authenticated:
        return SchoolClass.objects.none()
    if user.is_superuser:
        return SchoolClass.objects.all()

    role_names = set(user.groups.values_list('name', flat=True))
    if role_names - SCOPED_ROLES:
        return SchoolClass.objects.all()
    if role_names & SCOPED_ROLES:
        return SchoolClass.objects.filter(class_teacher=user)
    return SchoolClass.objects.none()


def visible_students(user):
    """Return the students this user is allowed to see, following the same rule as classes."""
    if not user or not user.is_authenticated:
        return Student.objects.none()
    if user.is_superuser:
        return Student.objects.all()

    role_names = set(user.groups.values_list('name', flat=True))
    if role_names - SCOPED_ROLES:
        return Student.objects.all()
    if role_names & SCOPED_ROLES:
        return Student.objects.filter(school_class__in=visible_classes(user))
    return Student.objects.none()