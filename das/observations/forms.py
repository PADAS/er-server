import json
import logging
import random
import re
from datetime import datetime, timedelta

import pytz
from choices.models import Choice
from core.common import TIMEZONE_USED
from core.forms_utils import (AssignedDateTimeRangeField, ColorPickerWidget,
                              JSONFieldFormMixin)
from django import forms
from django.contrib.admin.helpers import ActionForm
from django.contrib.admin.widgets import (AdminDateWidget,
                                          FilteredSelectMultiple)
from django.contrib.auth import get_user_model
from django.contrib.gis.forms import OSMWidget, PointField
from django.contrib.postgres.forms import JSONField
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils.dateparse import parse_duration
from django.utils.translation import ugettext_lazy as _
from observations.message_adapters import ADAPTER_MAPPING
from observations.models import (GPXTrackFile, Message, Observation, Source,
                                 SourceProvider, Subject, SubjectGroup,
                                 SubjectSource, SubjectSubType, SubjectType)
from observations.utils import find_paths

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
        label=f"Assigned Range in {TIMEZONE_USED}",
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
    static_sensor_position = PointField(
        srid=4326,
        widget=OSMWidget(
            attrs={
                "default_zoom": 4,
                "display_wkt": True,
                "map_width": 700,
                "map_height": 500,
                "map_srid": 4326
            }
        ), required=False
    )
    # For JSONFieldFormMixin -- this identifies the Model attribute that is the JSON Field.
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
            "static_sensor_position",
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
    _('Threshold in hours:minutes:seconds that indicates an abnormal period without new data for this Source.')


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
        except SubjectSubType.DoesNotExits:
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
    _('Threshold in hours:minutes:seconds that indicates an abnormal period without new data for this Source Provider.')

days_data_retain_help_text =  \
    _('Observations records outside the configured number of days will be removed permanently and cannot be retrieved.')

two_way_help_text_sp = \
    _('specify whether the source provider supports two-way messaging')


class TranformationRuleWidget(forms.MultiWidget):
    template_name = 'admin/transformation_rule.html'

    def __init__(self, attrs=None, provider=None, transform_rules=None):
        self.provider = provider or {}
        self.transform_rules = transform_rules or []
        widgets = [forms.CheckboxInput,
                   forms.TextInput(attrs={"id": "transform_label"}),
                   forms.TextInput({"id": "transform_unit"})]
        widgets = widgets * len(provider) if provider else widgets
        forms.MultiWidget.__init__(self, widgets, attrs)

    def _get_context(self, name, value, attrs):
        context = {'widget': {
            'name': name,
            'is_hidden': self.is_hidden,
            'required': self.is_required,
            'value': self.format_value(value),
            'attrs': self.build_attrs(self.attrs, attrs),
            'template_name': self.template_name,
        }}
        return context

    @staticmethod
    def get_dest(key):
        val = key.split('.')
        return val[-1] if val[-1] != '[]' else val[-2]

    def get_context(self, name, value, attrs):
        # value correspondes to values of JSON transformation rules.
        value = self.transform_rules
        context = self._get_context(name, value, attrs)
        if self.is_localized:
            for widget in self.widgets:
                widget.is_localized = self.is_localized
        # value is a list of values, each corresponding to a widget
        # in self.widgets.
        if not isinstance(value, list):
            value = self.decompress(value)

        final_attrs = context['widget']['attrs']
        input_type = final_attrs.pop('type', None)
        id_ = final_attrs.get('id')
        subwidgets = []
        list_subwidgets = []

        for _, key in enumerate(sorted(self.provider.keys())):
            for i, widget in enumerate(self.widgets):
                if input_type is not None:
                    widget.input_type = input_type
                widget_name = '%s_%s' % (name, i)
                try:
                    widget_value = None
                    for x in value:
                        if x.get('dest') == self.get_dest(key):
                            vals = list(x.values())
                            widget_value = vals[i]
                except IndexError:
                    widget_value = None
                except AttributeError:
                    widget_value = None
                if id_:
                    widget_attrs = final_attrs.copy()
                    widget_attrs['id'] = '%s_%s' % (
                        widget.attrs.get('id') or id_, _)
                else:
                    widget_attrs = final_attrs
                subwidgets.append(widget.get_context(
                    widget_name, widget_value, widget_attrs)['widget'])
            list_subwidgets.append(subwidgets)
            subwidgets = []
        context['widget']['subwidgets'] = list_subwidgets
        context['sample_data'] = json.loads(
            json.dumps(self.provider, sort_keys=True, indent=4))
        context["default_feature"] = self._get_default_feature(
            self.transform_rules)
        return context

    def render(self, name, value, attrs=None, renderer=None):
        """Render the widget as an HTML string."""
        context = self.get_context(name, value, attrs)
        return self._render(self.template_name, context, renderer)

    def decompress(self, value):
        return [] if value is None else value

    def _get_default_feature(self, transform_rules):
        for rule in transform_rules:
            if rule.get("default"):
                return rule.get("dest")
        return None


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


class TranformationRuleField(forms.fields.MultiValueField):
    widget = TranformationRuleWidget

    def __init__(self, *args, **kwargs):
        _fields = [
            forms.fields.BooleanField(required=False),
            forms.fields.CharField(required=False),
            forms.CharField(required=False),
            forms.CharField(required=False)]
        super().__init__(_fields, *args, **kwargs)

    def compress(self, values):
        return values


def msg_adapter_choices():
    choices = [(None, '')]
    for key in ADAPTER_MAPPING:
        choices.append((key, key))
    return choices


class MessageConfigurationWidget(forms.MultiWidget):
    template_name = 'admin/widgets/message_widget.html'

    def __init__(self, attrs=None):
        widgets = [forms.Select(choices=msg_adapter_choices()), forms.URLInput(
            attrs={'size': 40}), forms.TextInput(attrs={'size': 40})]
        super().__init__(widgets, attrs)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context['url_label'] = _('URL: ')
        context['adaptkey_label'] = _('Adapter Type: ')
        context['apikey_label'] = _('API key: ')
        return context

    def decompress(self, value):
        return [value.get('adapter_type'), value.get('url'), value.get('apikey')] if value else []


class MessageField(forms.MultiValueField):
    widget = MessageConfigurationWidget

    def __init__(self, *args, **kwargs):
        fields = [forms.CharField(required=False),
                  forms.URLField(required=False),
                  forms.CharField(required=False)]
        super().__init__(fields, *args, **kwargs)

    def compress(self, data_list):
        return {'adapter_type': data_list[0], 'url': data_list[1], 'apikey': data_list[2]} if data_list else data_list


class AutoFormatJSONWidget(forms.widgets.Textarea):

    def __init__(self, attrs=None):
        # Use slightly better defaults than HTML's 20x2 box
        default_attrs = {'cols': '80', 'rows': '30'}
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs)

    def format_value(self, value):
        try:
            deserialize = json.loads(value)
            value = json.dumps(deserialize, indent=2, sort_keys=True)
        except Exception as e:
            logger.warning("Error while formatting JSON: {}".format(e))
            return super().format_value(value)
        else:
            if isinstance(deserialize, dict) and not bool(deserialize):
                return json.dumps([])
            else:
                # these lines will try to adjust size of TextArea to fit to content
                row_lengths = [len(r) for r in value.split('\n')]
                self.attrs['rows'] = min(max(len(row_lengths) + 2, 10), 30)
                return value

    class Media:
        css = {
            'all': ('css/monospace_textarea.css',),
        }


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

    days_data_retain = forms.IntegerField(required=False, min_value=1, max_value=365,
                                          help_text=days_data_retain_help_text)

    tranformation_rule = TranformationRuleField(required=False)
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
            self.fields['tranformation_rule'].widget.provider = generate_sample_data(
                instance)
            self.fields['tranformation_rule'].widget.transform_rules = instance.transforms

    class Meta:
        model = SourceProvider
        fields = ['provider_key', 'display_name',
                  'additional', 'transforms', 'messaging_config']
        json_fields = (
            'lag_notification_threshold',
            'silence_notification_threshold',
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


class MessageGenericForeignKeyRawIdWidget(forms.TextInput):
    """Widget for displaying Dynamic GenericForeignkey in 'raw_id' rather than select box
    """
    template_name = 'admin/widgets/genericforeign_raw_id.html'

    def __init__(self, rel, admin_site, attrs=None, using=None, content_type="subject"):
        self.rel = rel
        self.admin_site = admin_site
        self.db = using
        self.content_type = content_type
        super().__init__(attrs)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        rel_to = Subject  # default to Subject object.
        related_url = reverse(
            'admin:%s_%s_changelist' % (
                rel_to._meta.app_label, rel_to._meta.model_name,),
            current_app=self.admin_site.name,
        )
        context['related_url'] = related_url
        context['link_title'] = _('Lookup')
        context['widget']['attrs'].setdefault(
            'class', 'vForeignKeyRawIdAdminField')
        if context['widget']['value']:
            context['link_label'], context['link_url'] = self.label_and_url_for_value(
                value)
        else:
            context['link_label'] = None
        return context

    def label_and_url_for_value(self, value):
        try:
            obj = Subject.objects.get(id=value)
        except Subject.DoesNotExist:
            from accounts.models import User
            obj = User.objects.get(id=value)
        url = reverse(
            '%s:%s_%s_change' % (
                self.admin_site.name, obj._meta.app_label, obj._meta.object_name.lower(),
            ), args=(obj.pk,)
        )
        return obj, url


class MessagesForm(forms.ModelForm):
    class Meta:
        model = Message
        fields = '__all__'

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
