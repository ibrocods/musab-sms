from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from core.terms import current_term

from .services import build_dashboard


@login_required
@require_GET
def home(request):
    hour = timezone.localtime().hour
    greeting = 'morning' if hour < 12 else 'afternoon' if hour < 18 else 'evening'
    term = current_term()
    return render(request, 'dashboard/home.html', {
        'd': build_dashboard(request.user, term),
        'greeting': greeting,
        'today': timezone.localdate(),
        'term': term,
    })

@login_required
@require_GET
def showcase(request):
    return render(request, 'dashboard/showcase.html', {})