from django import forms
from django.contrib.auth.models import User

from core.capabilities import CAPABILITIES

from .grants import NEVER_TEMPORARY


class StaffChoice(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        name = obj.get_full_name() or obj.get_username()
        return f'{name} ({obj.get_username()})'


class GrantForm(forms.Form):
    user = StaffChoice(queryset=User.objects.none(), label='Staff member')
    capability = forms.ChoiceField(label='Permission', choices=())
    reason = forms.CharField(max_length=200, help_text='For example "Bursar on leave"')
    ends_on = forms.DateField(
        label='Access ends on',
        widget=forms.DateInput(attrs={'type': 'date'}),
        help_text='Access ends at the end of this day.',
    )

    def __init__(self, *args, actor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['user'].queryset = (
            User.objects.filter(is_active=True, groups__isnull=False)
            .exclude(pk=actor.pk if actor else None)
            .distinct()
            .order_by('username')
        )
        self.fields['capability'].choices = [
            (code, label) for code, label in CAPABILITIES.items() if code not in NEVER_TEMPORARY
        ]