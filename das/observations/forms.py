
from django.utils.translation import ugettext_lazy as _

from django import forms
from django.contrib.admin.helpers import ActionForm
from django.contrib.admin.widgets import FilteredSelectMultiple

from observations.models import Subject, Source, SubjectGroup, SubjectSource, SubjectSubType
from observations.forms_utils import JSONFieldFormMixin, ColorPickerWidget, AssignedDateTimeRangeField

import logging
logger = logging.getLogger(__name__)


class SubjectSourceForm(JSONFieldFormMixin, forms.ModelForm):

    '''
    This provides extra form fields for the attributes we expect to have stored in SubjectSource.additional.
    '''
    data_status = forms.CharField(required=False, label='Data Status')
    data_starts_source = forms.CharField(
        required=False, label='Data Starts Source')
    data_stops_source = forms.CharField(
        required=False, label='Data Stops Source')
    data_stops_reason = forms.CharField(
        required=False, label='Data Stops Reason')

    class Meta:
        model = SubjectSource
        json_fields = ('data_status', 'data_starts_source',
                       'data_stops_source', 'data_stops_reason')
        fields = ('id', 'subject', 'source', 'assigned_range',
                  'additional') + json_fields

    assigned_range = AssignedDateTimeRangeField()

    # For JSONFieldFormMixin -- this identifies the Model attribute that is
    # the JSON Field.
    json_field = 'additional'


class SourceForm(JSONFieldFormMixin, forms.ModelForm):

    '''
    This provides extra form fields for the attributes we expect to have stored in Source.additional.
    '''
    collar_status = forms.CharField(required=False, label='Collar Status')
    collar_model = forms.CharField(required=False, label='Collar Model')
    has_acc_data = forms.BooleanField(
        required=False, label='Has Accelerometer Data')
    data_owners = forms.CharField(required=False, label='Data Owners')
    adjusted_beacon_freq = forms.CharField(
        required=False, label='Adjusted Beacon Frequency')

    class Meta:
        model = Source
        json_fields = ('collar_status', 'collar_model',
                       'has_acc_data', 'data_owners', 'adjusted_beacon_freq')
        fields = ('id', 'manufacturer_id', 'provider', 'source_type',
                  'model_name', 'additional') + json_fields


class SubjectSubtypeChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return '{1} ({0})'.format(obj.subject_type.display, obj.display)


class SubjectForm(forms.ModelForm):

    groups = forms.ModelMultipleChoiceField(
        queryset=SubjectGroup.objects.all(),
        required=False,
        widget=FilteredSelectMultiple(
            verbose_name=_('Groups'),
            is_stacked=False
        )
    )

    subject_subtype = SubjectSubtypeChoiceField(
        queryset=SubjectSubType.objects.all().order_by('display'))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['groups'].initial = self.instance.groups.all()

    class Meta:
        fields = '__all__'

    def _save_m2m(self):
        groups = self.cleaned_data['groups']
        self.instance.groups.set(groups)
        return super()._save_m2m()


class SubjectFormWithAttributes(JSONFieldFormMixin, SubjectForm):
    '''
    This provides extra form fields for the attributes we expect to have stored in Subject.additional.
    '''
    rgb = forms.CharField(required=False, widget=ColorPickerWidget(), label='Color',
                          help_text=_('This is a color value in r,g,b format (ex. "100, 150, 102") for displaying the subject\'s tracks.'))
    sex = forms.ChoiceField(required=False, choices=(
        ('male', _('Male')),
        ('female', _('Female'))
    ))
    region = forms.CharField(
        required=False, help_text='This is the region that will be shown in the DAS Mobile App.')
    country = forms.CharField(
        required=False, help_text='This is the country that will be shown in the DAS Mobile App.')

    class Meta(SubjectForm.Meta):
        json_fields = ('rgb', 'sex', 'region', 'country')
        fields = ('name', 'subject_subtype',
                  'common_name', 'groups', json_fields)

    json_field = 'additional'


class SubjectChangeListForm(forms.ModelForm):

    subject_subtype = SubjectSubtypeChoiceField(
        queryset=SubjectSubType.objects.all())

    class Meta:
        model = Subject
        fields = ('name', 'is_active')


class SetRandomColorForm(ActionForm):
    pass
