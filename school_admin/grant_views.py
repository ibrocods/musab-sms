from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from core.capabilities import CAPABILITIES
from core.models import TemporaryGrant
from core.permissions import require_capability

from .grant_forms import GrantForm
from .grants import grant_temporary, revoke_grant


def _error_text(error):
    return ' '.join(getattr(error, 'messages', ['You do not have permission.']))


@login_required
@require_capability('manage_staff')
@require_GET
def grant_list(request):
    now = timezone.now()
    active, past = [], []
    grants = TemporaryGrant.objects.select_related('user', 'granted_by').order_by('-starts_at')
    for grant in grants:
        row = {'grant': grant, 'label': CAPABILITIES.get(grant.capability, grant.capability)}
        if grant.revoked_at is None and grant.starts_at <= now < grant.ends_at:
            active.append(row)
        else:
            row['status'] = 'Ended early' if grant.revoked_at else 'Expired'
            past.append(row)
    return render(request, 'school_admin/grants.html', {'active': active, 'past': past})


@login_required
@require_capability('manage_staff')
@require_http_methods(['GET', 'POST'])
def grant_create(request):
    form = GrantForm(
        request.POST or None,
        actor=request.user,
        initial={'ends_on': timezone.localdate() + timedelta(days=1)},
    )
    if request.method == 'POST' and form.is_valid():
        data = form.cleaned_data
        try:
            grant_temporary(
                actor=request.user,
                target=data['user'],
                capability=data['capability'],
                reason=data['reason'],
                ends_on=data['ends_on'],
            )
        except (ValidationError, PermissionDenied) as error:
            form.add_error(None, _error_text(error))
        else:
            messages.success(request, f"Temporary access given to {data['user'].get_username()}.")
            return redirect('school_admin:grant_list')

    return render(request, 'school_admin/form_page.html', {
        'form': form,
        'title': 'Give temporary access',
        'subtitle': 'The access starts now and ends automatically. It can be ended earlier from the list.',
        'submit_label': 'Give access',
        'cancel_url': '/administration/grants/',
    })


@login_required
@require_capability('manage_staff')
@require_POST
def grant_revoke(request, pk):
    grant = get_object_or_404(TemporaryGrant.objects.select_related('user'), pk=pk)
    try:
        revoke_grant(actor=request.user, grant=grant)
    except (ValidationError, PermissionDenied) as error:
        messages.error(request, _error_text(error))
    else:
        messages.success(request, f'Access ended for {grant.user.get_username()}.')
    return redirect('school_admin:grant_list')