from django import forms
from django.contrib.admin.helpers import ActionForm
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.utils.translation import ugettext_lazy as _

from observations.models import Subject, SubjectGroup, SubjectSource

import logging
logger = logging.getLogger(__name__)

# class LoggingMixin(object):
#     def full_clean(self):
#         super(LoggingMixin, self).full_clean()
#         for field, errors in self.errors.items():
#             logger.info('Form error in %s: %s', ', '.join(errors))


class SubjectSourceForm(forms.ModelForm):
    def full_clean(self):
        super().full_clean()

    def clean(self):
        super().clean()

    class Meta:
        model = SubjectSource
        fields = ('id', 'subject', 'source', 'assigned_range', 'additional')


class SubjectForm(forms.ModelForm):

    groups = forms.ModelMultipleChoiceField(
        queryset=SubjectGroup.objects.all(),
        required=False,
        widget=FilteredSelectMultiple(
            verbose_name=_('Groups'),
            is_stacked=False
        )
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['groups'].initial = self.instance.groups.all()

    class Meta:
        fields = '__all__'
        # exclude = ['subject_type', 'subject_subtype']

    def _save_m2m(self):
        groups = self.cleaned_data['groups']
        self.instance.groups.set(groups)
        return super()._save_m2m()


class SubjectChangeListForm(forms.ModelForm):
    class Meta:
        model = Subject
        # , 'get_attributes', 'all_groups', 'all_sources')
        fields = ('name', 'is_active')


class SetRandomColorForm(ActionForm):
    pass
