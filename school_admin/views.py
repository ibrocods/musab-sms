from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.models import AccountSecurity, ClassSubject, SchoolClass

from .accounts import deactivate_staff, reactivate_staff, reset_password, update_details
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_http_methods
from core.permissions import ROLE_CAPABILITIES, require_capability

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


@login_required
@require_capability('manage_staff')
@require_http_methods(['GET', 'POST'])
def staff_edit(request, user_pk):
    target = get_object_or_404(User, pk=user_pk)
    current_role = next(
        (g.name for g in target.groups.all() if g.name in ROLE_CAPABILITIES), '',
    )
    if request.method == 'POST':
        role = request.POST.get('role', '')
        class_led = None
        if role == 'Class teacher' and request.POST.get('class_led'):
            class_led = SchoolClass.objects.filter(pk=request.POST['class_led']).first()
        teaching = []
        if role == 'Subject teacher':
            ids = request.POST.getlist('teaching')
            teaching = list(ClassSubject.objects.filter(pk__in=ids))
        try:
            update_details(
                actor=request.user, target=target,
                first_name=request.POST.get('first_name', '').strip(),
                last_name=request.POST.get('last_name', '').strip(),
                email=request.POST.get('email', '').strip(),
                role=role, class_led=class_led, teaching=teaching,
            )
        except (ValidationError, PermissionDenied) as error:
            messages.error(request, ' '.join(getattr(error, 'messages', ['You do not have permission.'])))
        else:
            messages.success(request, 'Details saved.')
            return redirect('school_admin:staff_list')

    return render(request, 'school_admin/staff_edit.html', {
        'target': target,
        'current_role': current_role,
        'roles': list(ROLE_CAPABILITIES),
        'classes': SchoolClass.objects.filter(is_active=True).select_related('class_teacher'),
        'links': ClassSubject.objects.select_related('school_class', 'subject', 'teacher'),
    })


@login_required
@require_capability('manage_staff')
@require_POST
def staff_deactivate(request, user_pk):
    target = get_object_or_404(User, pk=user_pk)
    try:
        deactivate_staff(actor=request.user, target=target)
    except (ValidationError, PermissionDenied) as error:
        messages.error(request, ' '.join(getattr(error, 'messages', ['You do not have permission.'])))
    else:
        messages.success(request, f'{target.get_username()} is deactivated. Their assignments were released.')
    return redirect('school_admin:staff_list')


@login_required
@require_capability('manage_staff')
@require_POST
def staff_reactivate(request, user_pk):
    target = get_object_or_404(User, pk=user_pk)
    try:
        reactivate_staff(actor=request.user, target=target)
    except (ValidationError, PermissionDenied) as error:
        messages.error(request, ' '.join(getattr(error, 'messages', ['You do not have permission.'])))
    else:
        messages.success(request, f'{target.get_username()} is active again. Assign their classes and subjects.')
    return redirect('school_admin:staff_list')


@login_required
@require_capability('manage_staff')
@require_POST
def staff_reset(request, user_pk):
    target = get_object_or_404(User, pk=user_pk)
    try:
        password = reset_password(actor=request.user, target=target)
    except (ValidationError, PermissionDenied) as error:
        messages.error(request, ' '.join(getattr(error, 'messages', ['You do not have permission.'])))
        return redirect('school_admin:staff_list')

    request.session['new_staff'] = {
        'username': target.get_username(),
        'password': password,
        'role': 'Password reset',
        'summary': ['They must choose a new password at their next sign-in.'],
    }
    return redirect('school_admin:staff_created')


@login_required
@require_http_methods(['GET', 'POST'])
def change_password(request):
    """Used by everyone to change their own password, and required after a reset."""
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            AccountSecurity.objects.update_or_create(
                user=user,
                defaults={'must_change_password': False, 'password_changed_at': timezone.now()},
            )
            messages.success(request, 'Your password has been changed.')
            return redirect('home')
    else:
        form = PasswordChangeForm(request.user)
    pending = AccountSecurity.objects.filter(user=request.user, must_change_password=True).exists()
    return render(request, 'school_admin/change_password.html', {'form': form, 'pending': pending})