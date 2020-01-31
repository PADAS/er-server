from django import forms
from django.core.exceptions import ValidationError

from das_server.models import UserAgreement


class UserEulaModelForm(forms.ModelForm):
    class Meta:
        model = UserAgreement
        fields = ['eula', 'user', 'accepted']
        widgets = {
            'eula': forms.HiddenInput,
            'user': forms.HiddenInput
        }
        labels = {
            "accepted": "Do you agree?",
        }

    def clean_do_you_accept(self):
        accepted = self.cleaned_data['accepted']
        if not accepted:
            raise ValidationError(
                'You must accept the terms of this agreement to continue using this website')
        return accepted
