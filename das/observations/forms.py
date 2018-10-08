
from django.utils.translation import ugettext_lazy as _

from django import forms
from django.contrib.admin.helpers import ActionForm
from django.contrib.admin.widgets import FilteredSelectMultiple, AdminDateWidget

from observations.models import Subject, Source, SubjectGroup, SubjectSource, SubjectSubType
from core.forms_utils import JSONFieldFormMixin, ColorPickerWidget, AssignedDateTimeRangeField
from choices.models import Choice

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
    data_stops_reason = forms.TypedMultipleChoiceField(
        required=False, label='Data Stops Reason',
        widget=FilteredSelectMultiple(verbose_name='Data Stops Reason',
                                      is_stacked=False))

    @staticmethod
    def fetch_stop_reasons():
        stop_reasons_choices = {}
        for stop_reason in Choice.objects.filter(
                model='observations.Source',
                field='data stops reason').order_by('ordernum'):
            stop_reasons_choices[stop_reason.value] = stop_reason.display
        return tuple([(key, value)
                      for key, value in stop_reasons_choices.items()])

    def __init__(self, *args, **kwargs):
        super(SubjectSourceForm, self).__init__(*args, **kwargs)
        self.fields['data_stops_reason'].choices = self.fetch_stop_reasons()

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

    source = forms.ModelChoiceField(
        queryset=Source.objects.all().order_by('manufacturer_id').prefetch_related('provider',))


class SourceForm(JSONFieldFormMixin, forms.ModelForm):

    '''
    This provides extra form fields for the attributes we expect to have stored
    in Source.additional.
    '''
    collar_status = forms.CharField(required=False, label='Collar Status')
    collar_model = forms.CharField(required=False, label='Collar Model')
    collar_manufacturer = forms.CharField(required=False,
                                          label='Collar Manufacturer')
    has_acc_data = forms.BooleanField(
        required=False, label='Has Accelerometer Data')
    data_owners = forms.TypedMultipleChoiceField(
        required=False, label='Data Owners', widget=FilteredSelectMultiple(
            verbose_name='Data Owners', is_stacked=False))

    # Get clarification on use of adjusted_beacon_freq & adjusted_frequency
    adjusted_beacon_freq = forms.CharField(
        required=False, label='Adjusted Beacon Frequency')
    primary_frequency = forms.CharField(required=False,
                                        label='Primary Frequency')
    backup_frequency = forms.CharField(required=False,
                                       label='Backup Frequency')
    adjusted_frequency = forms.CharField(required=False,
                                         label='Adjusted Frequency')
    predicted_expiry = forms.DateTimeField(required=False,
                                           label='Predicted Expiry',
                                           widget=AdminDateWidget())
    collar_key = forms.CharField(widget=forms.Textarea,
                                 required=False, label='Collar Key')


    @staticmethod
    def fetch_organizations():
        org_choices = {}
        for organization in Choice.objects.filter(
                model='accounts.user.User',
                field='organization').order_by('ordernum'):
            org_choices[organization.value] = organization.display
        return tuple([(key, value) for key, value in org_choices.items()])

    def __init__(self, *args, **kwargs):
        super(SourceForm, self).__init__(*args, **kwargs)
        self.fields['data_owners'].choices = self.fetch_organizations()

    class Meta:
        model = Source
        json_fields = ('collar_key', 'collar_status', 'collar_model',
                       'collar_manufacturer', 'has_acc_data', 'data_owners',
                       'adjusted_beacon_freq', 'primary_frequency',
                       'adjusted_frequency',
                       'backup_frequency', 'predicted_expiry')
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
        queryset=SubjectSubType.objects.all().order_by('display').select_related('subject_type',))

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
        queryset=SubjectSubType.objects.order_by('display').select_related('subject_type'))

    class Meta:
        model = Subject
        fields = ('name', 'is_active')


class SetRandomColorForm(ActionForm):
    pass

# from django.contrib.gis import forms as gisforms
# class SubjectStatusForm(forms.ModelForm):
#     w = gisforms.OSMWidget(attrs={'default_zoom': 10})
#     location = gisforms.PointField(srid=4326, widget=w,)
#
#     def save(self, commit=True):
#         return super().save(commit=commit)
#
