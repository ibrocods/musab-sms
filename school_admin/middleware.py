from django.shortcuts import redirect
from django.urls import reverse

from core.models import AccountSecurity


class ForcePasswordChangeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if user and user.is_authenticated:
            # Resolved per request, so URLs are loaded by the time we check them
            allowed = {reverse('school_admin:change_password'), reverse('logout')}
            if request.path not in allowed:
                pending = AccountSecurity.objects.filter(user=user, must_change_password=True).exists()
                if pending:
                    return redirect('school_admin:change_password')
        return self.get_response(request)