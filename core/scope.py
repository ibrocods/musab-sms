from .models import SchoolClass

# Roles whose members only see the classes they teach
SCOPED_ROLES = {'Class teacher'}


def visible_classes(user):
    """Return the classes this user is allowed to see."""
    if not user or not user.is_authenticated:
        return SchoolClass.objects.none()

    if user.is_superuser:
        return SchoolClass.objects.all()

    role_names = set(user.groups.values_list('name', flat=True))

    # Anyone with a role outside SCOPED_ROLES sees every class
    if role_names - SCOPED_ROLES:
        return SchoolClass.objects.all()

    # Class teachers only see their own classes
    if role_names & SCOPED_ROLES:
        return SchoolClass.objects.filter(class_teacher=user)

    # No recognised role means no access
    return SchoolClass.objects.none()