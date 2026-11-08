from .models import SchoolProfile


def school(request):
    return {'school': SchoolProfile.get()}