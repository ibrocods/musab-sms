from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from core.permissions import require_capability

from .forms import StaffCreateForm
from .staff import create_staff, staff_rows


@login_required
@require_capability('manage_staff')
@require_GET
def staff_list(request):
    return render(request, 'school_admin/staff_list.html', {'rows': staff_rows()})


@login_required
@require_capability('manage_staff')
@require_http_methods(['GET', 'POST'])
def staff_create(request):
    form = StaffCreateForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        data = form.cleaned_data
        teaching = list(data['teaching'])
        try:
            user, password = create_staff(
                actor=request.user,
                username=data['username'],
                first_name=data['first_name'],
                last_name=data['last_name'],
                email=data['email'],
                role=data['role'],
                class_led=data['class_led'],
                teaching=teaching,
            )
        except PermissionDenied:
            form.add_error(None, 'You do not have permission to add staff.')
        else:
            summary = []
            if data['role'] == 'Class teacher' and data['class_led']:
                summary.append(f"Class teacher of {data['class_led'].name}")
            for link in teaching:
                summary.append(f'Teaches {link.subject.name} in {link.school_class.name}')

            # Held in the session only until the confirmation page is opened, then removed
            request.session['new_staff'] = {
                'username': user.get_username(),
                'password': password,
                'role': data['role'],
                'summary': summary,
            }
            return redirect('school_admin:staff_created')

    return render(request, 'school_admin/staff_form.html', {'form': form})


@login_required
@require_capability('manage_staff')
@require_GET
def staff_created(request):
    new = request.session.pop('new_staff', None)
    if not new:
        return redirect('school_admin:staff_list')
    return render(request, 'school_admin/staff_created.html', {'new': new})