import json
import logging
import random
import re
from datetime import datetime, timedelta

import pytz

from django import forms
from django.contrib.admin.helpers import ActionForm
from django.contrib.admin.widgets import (AdminDateWidget,
                                          FilteredSelectMultiple)
from django.contrib.auth import get_user_model
from django.contrib.postgres.forms import JSONField
from django.core.exceptions import ValidationError
from django.utils.dateparse import parse_duration
from django.utils.translation import gettext_lazy as _

from choices.models import Choice
from core.forms_utils import (AssignedDateTimeRangeField, ColorPickerWidget,
                              JSONFieldFormMixin)
from observations.models import (GPXTrackFile, Message, Observation, Source,
                                 SourceProvider, Subject, SubjectGroup,
                                 SubjectSource, SubjectSubType, SubjectType)
from observations.utils import find_paths
from observations.widgets import (AutoFormatJSONWidget,
                                  CustomSelectWidgetForContentType,
                                  MessageConfigurationWidget,
                                  TransformationRuleWidget)

logger = logging.getLogger(__name__)


def validate_assigned_range(value):
    lower, upper = value
    if lower and upper:
        if lower > upper:
            raise forms.ValidationError(
                _('range lower bound must be less than or equal to range upper bound'))


class SubjectSourceForm(JSONFieldFormMixin, forms.ModelForm):
    """This provides extra form fields for the attributes we expect to have stored in SubjectSource.additional."""
    chronofile = forms.IntegerField(required=False, label="Chronofile")
    data_status = forms.CharField(required=False, label="Data Status")
    data_starts_source = forms.CharField(
        required=False, label="Data Starts Source")
    data_stops_source = forms.CharField(
        required=False, label="Data Stops Source")
    data_stops_reason = forms.ChoiceField(
        required=False, help_text="Reason for Stop")
    date_off_or_removed = forms.CharField(
        required=False, label="Date Off or Removed")
    comments = forms.CharField(
        required=False, label="Comments", widget=forms.Textarea)
    assigned_range = AssignedDateTimeRangeField(
        label=f"Assigned Range in GMT",
        required=True,
        validators=[validate_assigned_range],
    )
    source = forms.ModelChoiceField(
        queryset=Source.objects.all()
        .order_by("manufacturer_id")
        .prefetch_related(
            "provider",
        )
    )
    json_field = "additional"

    class Meta:
        model = SubjectSource
        json_fields = (
            "chronofile",
            "data_status",
            "data_starts_source",
            "data_stops_source",
            "data_stops_reason",
            "date_off_or_removed",
            "comments",
        )
        fields = (
            "id",
            "subject",
            "source",
            "assigned_range",
            "location",
            "additional",
        ) + json_fields

    def __init__(self, *args, **kwargs):
        super(SubjectSourceForm, self).__init__(*args, **kwargs)
        self.fields["data_stops_reason"].choices = self.fetch_stop_reasons()

    @staticmethod
    def fetch_stop_reasons():
        stop_reasons_choices = {"": ""}
        for stop_reason in Choice.objects.filter(
            model="observations.Source", field="data stops reason"
        ).order_by("ordernum"):
            stop_reasons_choices[stop_reason.value] = stop_reason.display
        return tuple([(key, value) for key, value in stop_reasons_choices.items()])


silence_notification_threshold_help_text_for_source =  \
    _('Threshold in hours:minutes:seconds. If no new data is received from this Source within this threshold, a '
      'report will be created. This will override the "Default silence notification threshold" if set for the '
      'source provider.')


two_way_help_text = \
    _('specify whether the source supports two-way messaging')


def two_way_choices(source_provider_enable=False):
    if source_provider_enable:
        return (
            ('unknown', _('Enabled by Source Provider')),
            ('true', _('Enabled')),
            ('false', _('Disabled'))
        )
    else:
        return (
            ('unknown', _('')),
            ('true', _('Enabled')),
            ('false', _('Disabled'))
        )


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
    datasource = forms.CharField(required=False,
                                 label='Data Source')
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
    two_way_messaging = forms.NullBooleanField(
        label='Two-way messaging', help_text=two_way_help_text, required=False)

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

    @staticmethod
    def fetch_2way_messaging_choices(instance):
        if instance:
            provider_2way_conf = instance.provider.additional.get(
                'two_way_messaging', False)
            return two_way_choices(source_provider_enable=provider_2way_conf)
        return two_way_choices()

    def __init__(self, *args, **kwargs):
        super(SourceForm, self).__init__(*args, **kwargs)
        instance = kwargs.get('instance')
        self.fields['data_owners'].choices = self.fetch_organizations()
        self.fields['collar_status'].choices = self.fetch_collar_status()
        self.fields['two_way_messaging'].widget.choices = self.fetch_2way_messaging_choices(
            instance)

    class Meta:
        model = Source
        json_fields = ('collar_key', 'collar_status', 'collar_model',
                       'collar_manufacturer', 'datasource', 'has_acc_data', 'data_owners',
                       'feed_id', 'feed_passwd',
                       'adjusted_beacon_freq', 'frequency',
                       'adjusted_frequency',
                       'backup_frequency', 'predicted_expiry', 'silence_notification_threshold', 'two_way_messaging')
        json_date_fields = ('predicted_expiry',)
        fields = ('id', 'manufacturer_id', 'provider', 'source_type',
                  'model_name') + json_fields


class SubjectSubtypeChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return '{1} ({0})'.format(obj.subject_type.display, obj.display)


def get_subject_subtype_choices():
    choices = []
    subjects_type = SubjectType.objects.all().order_by("value")
    if subjects_type:
        for subject_type in subjects_type:
            subjects_subtype = subject_type.subjectsubtype_set.all().order_by("display")
            subjects_subtype = [
                (subject_subtype.value, subject_subtype.display)
                for subject_subtype in subjects_subtype
            ]
            choices.append((subject_type.display.upper(),
                           (list(subjects_subtype))))
    return choices


class SubjectForm(JSONFieldFormMixin, forms.ModelForm):
    groups = forms.ModelMultipleChoiceField(
        queryset=SubjectGroup.objects.all(),
        required=False,
        widget=FilteredSelectMultiple(
            verbose_name=_('Groups'),
            is_stacked=False
        )
    )
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
        self.fields['subject_subtype'] = forms.ChoiceField(
            choices=get_subject_subtype_choices()
        )

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

    def clean_subject_subtype(self):
        subject_subtype = self.cleaned_data["subject_subtype"]
        try:
            return SubjectSubType.objects.get(value=subject_subtype)
        except SubjectSubType.DoesNotExist:
            raise ValidationError(
                f"The value for this subject subtype {subject_subtype} does not exists"
            )


class SubjectChangeListForm(forms.ModelForm):

    subject_subtype = SubjectSubtypeChoiceField(
        queryset=SubjectSubType.objects.order_by('display').select_related('subject_type'))

    class Meta:
        model = Subject
        fields = ('name', 'is_active')


lag_notification_threshold_help_text =  \
    _('Threshold in hours:minutes:seconds that indicates an abnormal delay in data for this Source Provider.')

silence_notification_threshold_help_text =  \
    _('Threshold in hours:minutes:seconds. If ALL of the Sources for this Source Provider fail to submit new data '
      'within this threshold, a report will be created for the Source Provider.')

default_silence_notification_threshold_help_text = _('Threshold in hours:minutes. If any specific Sources for '
                                                     'this Source Provider fail to submit new data within '
                                                     'this threshold, a report will be created for each of them.')

days_data_retain_help_text =  \
    _('Observations records outside the configured number of days will be removed permanently and cannot be retrieved.')

two_way_help_text_sp = \
    _('specify whether the source provider supports two-way messaging')


def generate_sample_data(provider):
    accum = {}
    rows = 4
    dt_filter = datetime.now(tz=pytz.utc) - timedelta(days=3)

    observations = Observation.objects.raw("""
     select ob.id, 
            jsonb_agg(to_jsonb(ob.additional))
                over (partition by ob.source_id order by ob.recorded_at desc ROWS BETWEEN UNBOUNDED PRECEDING AND %s FOLLOWING) 
                    AS agg_data
    from (select row_number()
            over (partition by o.source_id order by o.recorded_at DESC) as rn, o.*
            from observations_observation o inner join observations_source 
                on (o.source_id = observations_source.id) where 
                    observations_source.provider_id = %s and o.recorded_at >= %s) ob
        where ob.rn <= %s
     """, [rows, provider.id, dt_filter, rows])

    [find_paths(aggregate_data, accum=accum)
     for observation in observations for aggregate_data in observation.agg_data]

    for k, v in accum.items():
        accum[k] = random.sample(v, min(3, len(v)))
    return accum


class TransformationRuleField(forms.fields.MultiValueField):
    widget = TransformationRuleWidget

    def __init__(self, *args, **kwargs):
        _fields = [
            forms.fields.BooleanField(required=False),
            forms.fields.CharField(required=False),
            forms.CharField(required=False),
            forms.CharField(required=False)]
        super().__init__(_fields, *args, **kwargs)

    def compress(self, values):
        return values


class MessageField(forms.MultiValueField):
    widget = MessageConfigurationWidget

    def __init__(self, *args, **kwargs):
        fields = [forms.CharField(required=False),
                  forms.URLField(required=False),
                  forms.CharField(required=False)]
        super().__init__(fields, *args, **kwargs)

    def compress(self, data_list):
        return {'adapter_type': data_list[0], 'url': data_list[1], 'apikey': data_list[2]} if data_list else data_list


class JSONString(str):
    pass


class InvalidJSONInput(str):
    pass


class ExtendedJSONField(JSONField):
    default_error_messages = {
        'invalid': _("JSON must be properly formatted. The following error was raised:  %(error)s"),
    }

    def to_python(self, value):
        if self.disabled:
            return value
        if value in self.empty_values:
            return None
        elif isinstance(value, (list, dict, int, float, JSONString)):
            return value
        try:
            converted = json.loads(value)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError(
                self.error_messages['invalid'],
                code='invalid',
                params={'error': exc},
            )

        if isinstance(converted, str):
            return JSONString(converted)
        else:
            return converted


class SourceProviderForm(JSONFieldFormMixin, forms.ModelForm):

    lag_notification_threshold = forms.CharField(max_length=8, required=False, empty_value=None,
                                                 help_text=lag_notification_threshold_help_text)

    silence_notification_threshold = forms.CharField(max_length=8, required=False, empty_value=None,
                                                     help_text=silence_notification_threshold_help_text)

    default_silent_notification_threshold = forms.CharField(max_length=8, required=False, empty_value=None,
                                                            label="Default silence notification threshold",
                                                            help_text=default_silence_notification_threshold_help_text)

    days_data_retain = forms.IntegerField(required=False, min_value=1, max_value=365,
                                          help_text=days_data_retain_help_text)

    transformation_rule = TransformationRuleField(required=False)
    two_way_messaging = forms.BooleanField(required=False, initial=False, label='Two-way messaging',
                                           help_text=two_way_help_text_sp)

    transforms = ExtendedJSONField(widget=AutoFormatJSONWidget, required=False,
                                   label=_("Advanced transformation rules"))

    messaging_config = MessageField(
        label='Messaging Configuration', required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = kwargs.get('instance')
        if instance:
            self.fields['transformation_rule'].widget.provider = generate_sample_data(
                instance)
            self.fields['transformation_rule'].widget.transform_rules = instance.transforms

    class Meta:
        model = SourceProvider
        fields = ['provider_key', 'display_name',
                  'additional', 'transforms', 'messaging_config']
        json_fields = (
            'lag_notification_threshold',
            'silence_notification_threshold',
            'default_silent_notification_threshold',
            'days_data_retain',
            'two_way_messaging',
            'messaging_config'
        )
        json_date_fields = set()

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

    def clean_transforms(self):
        cleaned_data = super().clean()
        schema = cleaned_data.get('transforms')

        if schema is None:  # tranform_rules can be null or a list.
            return schema

        if not isinstance(schema, list) and bool(schema):
            message = _(
                "Tranformation rules must be properly configured, expecting a list or null")
            raise forms.ValidationError(message, code='invalid')
        return schema

    def clean_default_silent_notification_threshold(self):
        data = self.cleaned_data["default_silent_notification_threshold"]
        pattern = re.compile(r"^(\d{2}:[0-5]\d$)")
        if data and not re.fullmatch(pattern, data):
            raise forms.ValidationError(
                _("This field should follow the format HH:MM and have to be lower than 99:59"))
        return data


class SetRandomColorForm(ActionForm):
    pass


class GPXFileForm(forms.ModelForm):
    data = forms.FileField(required=True)

    class Meta:
        model = GPXTrackFile
        fields = '__all__'

    def clean_data(self):
        file_extension = '.gpx'
        error_msg = _('Only .gpx files can be imported.')
        file = self.cleaned_data.get('data')
        file_name = file.name
        if file_name.lower().endswith(file_extension):
            return file
        else:
            raise forms.ValidationError(error_msg, code='invalid')


class MessagesForm(forms.ModelForm):
    class Meta:
        model = Message
        fields = '__all__'
        widgets = {
            'sender_content_type': CustomSelectWidgetForContentType,
            'receiver_content_type': CustomSelectWidgetForContentType
        }

    def clean(self):
        cleaned_data = super().clean()
        map_model = {'subject': Subject, 'user': get_user_model()}

        def validate(content_type, contenttype_id, field):
            if contenttype_id and content_type:
                model = map_model.get(content_type.name)
                try:
                    model.objects.get(id=contenttype_id)
                except Subject.DoesNotExist:
                    raise forms.ValidationError(
                        {field: forms.ValidationError(
                            _(f'Subject with this id "{contenttype_id}" does not exist.'), code='invalid')})
                except Exception:
                    raise forms.ValidationError(
                        {field: forms.ValidationError(
                            _(f'User with this id "{contenttype_id}" does not exist'), code='invalid')})

        # sender_content_type.
        sender_content_type = cleaned_data.get('sender_content_type')
        sender_id = cleaned_data.get('sender_id')
        validate(sender_content_type, sender_id, 'sender_id')

        # receiver_content_type
        receiver_content_type = cleaned_data.get('receiver_content_type')
        receiver_id = cleaned_data.get('receiver_id')
        validate(receiver_content_type, receiver_id, 'receiver_id')

        return cleaned_data
