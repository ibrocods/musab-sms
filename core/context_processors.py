from .models import SchoolProfile
from .permissions import can


def school(request):
    return {'school': SchoolProfile.get()}


class _Capabilities:
    """Lets templates write {% if caps.view_students %}. Each check runs only when used."""

    def __init__(self, user):
        self._user = user

    def __getattr__(self, name):
        return can(self._user, name)


def capabilities(request):
    return {'caps': _Capabilities(getattr(request, 'user', None))}