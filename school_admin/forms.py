from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError

from core.models import ClassSubject, SchoolClass
from core.permissions import ROLE_CAPABILITIES

ROLE_CHOICES = [(role, role) for role in ROLE_CAPABILITIES]


class ClassChoice(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        teacher = obj.class_teacher.get_username() if obj.class_teacher else 'no class teacher yet'
        return f'{obj.name} (currently: {teacher})'


class AssignmentChoice(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        teacher = obj.teacher.get_username() if obj.teacher else 'unassigned'
        return f'{obj.subject.name} in {obj.school_class.name} (currently: {teacher})'


class StaffCreateForm(forms.Form):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    username = forms.CharField(
        max_length=150,
        validators=[UnicodeUsernameValidator()],
        help_text='Used to sign in. Letters, numbers and @ . + - _ only.',
    )
    email = forms.EmailField(required=False)
    role = forms.ChoiceField(choices=ROLE_CHOICES)
    class_led = ClassChoice(
        queryset=SchoolClass.objects.filter(is_active=True).select_related('class_teacher'),
        required=False,
        empty_label='No class',
        label='Class to lead',
    )
    teaching = AssignmentChoice(
        queryset=ClassSubject.objects.select_related('school_class', 'subject', 'teacher')
        .order_by('school_class__name', 'subject__name'),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label='Subjects to teach',
    )
    replace = forms.BooleanField(
        required=False,
        label='Replace current teachers',
        help_text='Moves any class or subject already held by someone else to this person.',
    )
    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError('That username is already taken.')
        return username

    def clean(self):
        from .assignments import TEACHER_ROLES
        cleaned = super().clean()
        role = cleaned.get('role')

        # Teacher roles can hold a class and subjects. Other roles hold neither.
        if role not in TEACHER_ROLES:
            cleaned['class_led'] = None
            cleaned['teaching'] = []
        elif role == 'Subject teacher' and not cleaned.get('teaching'):
            raise ValidationError('Choose at least one class and subject for a subject teacher.')
        return cleaned