import re

from django.utils.translation import ugettext_lazy as _
from django.utils.dateparse import parse_duration

from django import forms
from django.contrib.admin.helpers import ActionForm
from django.contrib.admin.widgets import FilteredSelectMultiple, AdminDateWidget

from observations.models import Subject, Source, SubjectGroup, SubjectSource, SubjectSubType, SourceProvider
from core.forms_utils import JSONFieldFormMixin, ColorPickerWidget, AssignedDateTimeRangeField
from choices.models import Choice

import logging
logger = logging.getLogger(__name__)


class SubjectSourceForm(JSONFieldFormMixin, forms.ModelForm):

    '''
    This provides extra form fields for the attributes we expect to have stored in SubjectSource.additional.
    '''
    chronofile = forms.IntegerField(required=False, label='Chronofile')
    data_status = forms.CharField(required=False, label='Data Status')
    data_starts_source = forms.CharField(
        required=False, label='Data Starts Source')
    data_stops_source = forms.CharField(
        required=False, label='Data Stops Source')
    data_stops_reason = forms.ChoiceField(required=False,
                                          help_text='Reason for Stop')
    comments = forms.CharField(required=False, label='Comments',
                               widget=forms.Textarea)

    @staticmethod
    def fetch_stop_reasons():
        stop_reasons_choices = {'': ''}
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
        json_fields = ('chronofile', 'data_status', 'data_starts_source',
                       'data_stops_source', 'data_stops_reason', 'comments')
        fields = ('id', 'subject', 'source', 'assigned_range',
                  'additional') + json_fields

    assigned_range = AssignedDateTimeRangeField()

    # For JSONFieldFormMixin -- this identifies the Model attribute that is
    # the JSON Field.
    json_field = 'additional'

    source = forms.ModelChoiceField(
        queryset=Source.objects.all().order_by('manufacturer_id').prefetch_related('provider',))


silence_notification_threshold_help_text_for_source =  \
    _('Threshold in hours:minutes:seconds that indicates an abnormal period without new data for this Source.')


class SourceForm(JSONFieldFormMixin, forms.ModelForm):

    '''
    This provides extra form fields for the attributes we expect to have stored
    in Source.additional.
    '''
    collar_status = forms.ChoiceField(required=False,
                                      label='Collar Status')
    collar_model = forms.CharField(required=False, label='Collar Model')
    collar_manufacturer = forms.CharField(required=False,
                                          label='Collar Manufacturer')
    has_acc_data = forms.BooleanField(
        required=False, label='Has Accelerometer Data')
    data_owners = forms.TypedMultipleChoiceField(
        required=False, label='Data Owners', widget=FilteredSelectMultiple(
            verbose_name='Data Owners', is_stacked=False))
    adjusted_beacon_freq = forms.CharField(
        required=False, label='Adjusted Beacon Frequency')
    frequency = forms.CharField(required=False,
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
    feed_id = forms.CharField(required=False, label='Feed Id')
    feed_passwd = forms.CharField(required=False, label='Feed Password')

    silence_notification_threshold = forms.CharField(max_length=8, required=False, empty_value=None,
                                                     help_text=silence_notification_threshold_help_text_for_source)

    @staticmethod
    def fetch_organizations():
        org_choices = {'': ''}
        for organization in Choice.objects.filter(
                model='accounts.user.User',
                field='organization').order_by('ordernum'):
            org_choices[organization.value] = organization.display
        return tuple([(key, value) for key, value in org_choices.items()])

    @staticmethod
    def fetch_collar_status():
        choices = {'': ''}
        for choice in Choice.objects.filter(
                model='observations.Source',
                field='collar_status').order_by('ordernum'):
            choices[choice.value] = choice.display
        return tuple([(key, value) for key, value in choices.items()])

    def __init__(self, *args, **kwargs):
        super(SourceForm, self).__init__(*args, **kwargs)
        self.fields['data_owners'].choices = self.fetch_organizations()
        self.fields['collar_status'].choices = self.fetch_collar_status()

    class Meta:
        model = Source
        json_fields = ('collar_key', 'collar_status', 'collar_model',
                       'collar_manufacturer', 'has_acc_data', 'data_owners',
                       'feed_id', 'feed_passwd',
                       'adjusted_beacon_freq', 'frequency',
                       'adjusted_frequency',
                       'backup_frequency', 'predicted_expiry', 'silence_notification_threshold')
        json_date_fields = ('predicted_expiry',)
        fields = ('id', 'manufacturer_id', 'provider', 'source_type',
                  'model_name', 'additional') + json_fields


class SubjectSubtypeChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return '{1} ({0})'.format(obj.subject_type.display, obj.display)


class SubjectForm(JSONFieldFormMixin, forms.ModelForm):

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

    '''
    This provides extra form fields for the attributes we expect to have stored
     in Subject.additional.
    '''
    rgb = forms.CharField(required=False, widget=ColorPickerWidget(),
                          label='Color',
                          help_text=_('This is a color value in r,g,b format'
                                      ' (ex. "100, 150, 102") for displaying '
                                      'the subject\'s tracks.'))
    sex = forms.ChoiceField(required=False, choices=(
        ('male', _('Male')),
        ('female', _('Female'))
    ))
    region = forms.ChoiceField(required=False,
                               help_text='Region that will be shown in the DAS'
                                         ' Mobile App.')
    country = forms.ChoiceField(required=False,
                                help_text='Country that will be shown in the '
                                          'DAS Mobile App.')
    tm_animal_id = forms.CharField(required=False, label='Animal ID')
    # other_id = forms.CharField(required=False, label='Other id')

    class Meta:
        fields = '__all__'
        model = Subject

        json_fields = ('rgb', 'sex', 'region', 'country', 'tm_animal_id')

    json_field = 'additional'

    def __init__(self, *args, **kwargs):
        super(SubjectForm, self).__init__(*args, **kwargs)

        if self.instance and self.instance.pk:
            self.fields['groups'].initial = self.instance.groups.all()

        # Get country and region choices from static methods
        self.fields['region'].choices = self.fetch_region_choices()
        self.fields['country'].choices = self.fetch_country_choices()

    def _save_m2m(self):
        groups = self.cleaned_data['groups']
        self.instance.groups.set(groups)
        return super()._save_m2m()

    @staticmethod
    def fetch_region_choices():
        region_choices = {'': ''}
        for region in Choice.objects.filter(
                model='observations.region',
                field='region').order_by('ordernum'):
            region_choices[region.value] = region.display
        return tuple([(key, value) for key, value in region_choices.items()])

    @staticmethod
    def fetch_country_choices():
        country_choices = {'': ''}
        for country in Choice.objects.filter(
                model='observations.region',
                field='country').order_by('ordernum'):
            country_choices[country.value] = country.display
        return tuple([(key, value) for key, value in country_choices.items()])

    def save(self, *args, **kwargs):

        commit = kwargs.pop('commit', True)
        instance = super(SubjectForm, self).save(*args,
                                                 commit=False,
                                                 **kwargs)

        if commit:
            instance.save()
        return instance


class SubjectChangeListForm(forms.ModelForm):

    subject_subtype = SubjectSubtypeChoiceField(
        queryset=SubjectSubType.objects.order_by('display').select_related('subject_type'))

    class Meta:
        model = Subject
        fields = ('name', 'is_active')


lag_notification_threshold_help_text =  \
    _('Threshold in hours:minutes:seconds that indicates an abnormal delay in data for this Source Provider.')

silence_notification_threshold_help_text =  \
    _('Threshold in hours:minutes:seconds that indicates an abnormal period without new data for this Source Provider.')

days_data_retain_help_text =  \
    _('Observations records outside the configured number of days will be removed permanently and cannot be retrieved.')


class SourceProviderForm(JSONFieldFormMixin, forms.ModelForm):

    lag_notification_threshold = forms.CharField(max_length=8, required=False, empty_value=None,
                                                 help_text=lag_notification_threshold_help_text)

    silence_notification_threshold = forms.CharField(max_length=8, required=False, empty_value=None,
                                                     help_text=silence_notification_threshold_help_text)

    days_data_retain = forms.IntegerField(required=False,
                                          help_text=days_data_retain_help_text)

    class Meta:
        model = SourceProvider
        fields = ['provider_key', 'display_name', 'additional']
        json_fields = (
            'lag_notification_threshold',
            'silence_notification_threshold',
            'days_data_retain',
        )
        json_date_fields = set()

    # def clean_lag_notification_threshold(self):

    def clean(self):

        cleaned_data = super().clean()
        value = cleaned_data.get('lag_notification_threshold')

        if value and \
                (not parse_duration(value) or
                    not re.match(r'\d{1,2}:\d{2}:\d{2}', value)
                 ):
            raise forms.ValidationError(
                {'lag_notification_threshold': forms.ValidationError(
                    _('Notification threshold must be of the form HH:MM:SS.'), code='invalid')}
            )

        return cleaned_data


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
