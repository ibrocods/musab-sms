from django import forms
from django.contrib.auth.models import User
from django.db.models import Q
from django.core.exceptions import ValidationError

from core.models import ClassSubject, SchoolClass, Subject


class SubjectForm(forms.ModelForm):
    class Meta:
        model = Subject
        fields = ['name', 'code', 'is_active']
        help_text = {'is_active': 'Inactive subjects can no longer be added to classes.'}


class ClassForm(forms.ModelForm):
    class_teacher = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        empty_label='No class teacher yet',
        help_text='Only active teachers with the Class teacher role appear here.',
    )

    class Meta:
        model = SchoolClass
        fields = ['name', 'level', 'stream', 'class_teacher', 'is_active']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Keep the current teacher in the list, even if their role has changed,
        # so saving the form doesn't silently clear them
        self.fields['class_teacher'].queryset = (
            User.objects.filter(is_active=True)
            .filter(Q(groups__name='Class teacher') | Q(pk=self.instance.class_teacher_id))
            .distinct()
            .order_by('username')
        )


class ClassSubjectForm(forms.ModelForm):
    class Meta:
        model = ClassSubject
        fields = ['subject', 'teacher']

    def __init__(self, *args, school_class=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.school_class = school_class
        self.fields['subject'].queryset = Subject.objects.filter(is_active=True).order_by('name')
        self.fields['teacher'].queryset = (
            User.objects.filter(is_active=True, groups__name__in=['Subject teacher', 'Class teacher'])
            .distinct()
            .order_by('username')
        )
        self.fields['teacher'].required = False
        self.fields['teacher'].empty_label = 'Assign later'

    def clean_subject(self):
        subject = self.cleaned_data['subject']
        if self.school_class and ClassSubject.objects.filter(
            school_class=self.school_class, subject=subject,
        ).exists():
            raise ValidationError('This class already studies that subject.')
        return subject