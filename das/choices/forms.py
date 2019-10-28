import os

from django import forms
from django.contrib.staticfiles.storage import staticfiles_storage
from django.forms.widgets import Widget

from core.widget import IconKeyInput, get_icon_select_list
from choices.models import Choice


class ChoiceForm(forms.ModelForm):
    icon = forms.CharField(
        required=False,
        widget=IconKeyInput(image_list_fn=get_icon_select_list))

    class Meta:
        model = Choice
        fields = '__all__'
