import json

import jsonschema

from django import forms
from django.contrib import messages
from django.contrib.admin.widgets import (AdminSplitDateTime,
                                          FilteredSelectMultiple)
from django.contrib.auth import get_user_model
from django.forms import TextInput
from django.forms.boundfield import mark_safe
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _

from activity.alerting.conditions import Conditions
from activity.exceptions import (SCHEMA_ERROR_JSON_DECODE_ERROR,
                                 SchemaValidationError)
from activity.models import (PROVENANCE_CHOICES, Community, EventGeometry,
                             EventProvider, EventType, NotificationMethod,
                             Patrol, PatrolSegment, PatrolType)
from core.common import TIMEZONE_USED
from core.forms_utils import JSONFieldFormMixin
from core.inline_openlayer import InlineOSMGeoAdmin
from core.utils import OneWeekSchedule
from core.widget import IconKeyInput, get_icon_select_list
from observations.models import Subject
from utils.gis import get_polygon_info
from utils.schema_utils import (get_schema_renderer_method,
                                validate_rendered_schema_is_wellformed)


class MonospaceTextWidget(forms.Textarea):
    template_name = 'admin/activity/monospace_textarea.html'

    def __init__(self, attrs=None):
        # Use slightly better defaults than HTML's 20x2 box
        default_attrs = {'cols': '70', 'rows': '30'}
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs)

    class Media:
        css = {
            'all': ('css/monospace_textarea.css',),
        }


class SchemaWidget(forms.Textarea):
    template_name = 'admin/activity/eventtype/schema_textarea.html'

    def __init__(self, attrs=None):
        # Use slightly better defaults than HTML's 20x2 box
        default_attrs = {'cols': '50', 'rows': '100'}
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs)

    class Media:
        css = {
            'all': ('css/schema_textarea.css',),
        }


class AutoResolveWidget(forms.MultiWidget):
    template_name = 'admin/activity/eventtype/auto_resolve.html'

    def __init__(self, attrs=None):
        attrs = {'class': 'auto-resolve-start'}
        widgets = [forms.CheckboxInput, forms.NumberInput]
        forms.MultiWidget.__init__(self, widgets, attrs)

    def get_context(self, name, value, attrs):
        context = super(AutoResolveWidget, self).get_context(
            name, value, attrs)
        return context

    def decompress(self, value):
        return [] if value is None else value


class AutoResolveField(forms.fields.MultiValueField):
    widget = AutoResolveWidget
    error_message_hours = {'min_value': "Ensure 'value for hour' is greater than or equal to 1",
                           'max_value': "Ensure 'value for hour' is less than or equal to 10,000"}

    def __init__(self, *args, **kwargs):
        _fields = [
            forms.fields.BooleanField(),
            forms.fields.IntegerField(required=False, min_value=1, max_value=10000, error_messages=self.error_message_hours)]
        super().__init__(_fields, *args, **kwargs)

    def compress(self, values):
        return values


def validate_schema_is_well_formed(schema):

    try:
        rendered_schema = get_schema_renderer_method()(schema)
    except NameError as ne:
        raise forms.ValidationError(
            f'Schema includes an invalid token {str(ne)}')
    except Exception:
        raise forms.ValidationError(SCHEMA_ERROR_JSON_DECODE_ERROR)
    else:
        try:
            validate_rendered_schema_is_wellformed(rendered_schema)
        except SchemaValidationError as e:
            raise forms.ValidationError(str(e))


class PrettyReadOnlyJSONWidget(forms.widgets.Widget):
    def render(self, name, value, attrs=None, renderer=None):
        return render_to_string('json_readonly.html', {'name': name, 'value': value, 'attrs': attrs})

    class Media:
        css = {'all': ('css/prism-default.css', 'json_readonly.css')}
        js = ['js/json_readonly.js', 'js/prism.js']


class EventTypeForm(forms.ModelForm):
    schema = forms.CharField(widget=SchemaWidget(
        attrs={'rows': 30, 'cols': 100}))

    icon = forms.CharField(required=False,
                           label='Icon Override',
                           widget=IconKeyInput(image_list_fn=get_icon_select_list))

    auto_eventtype_resolve = AutoResolveField(label='', required=False)

    class Meta:
        model = EventType
        fields = ['icon', 'display', 'schema', 'auto_eventtype_resolve']
        help_texts = {
            'geometry_type': mark_safe(f"<strong>{_('WARNING: After this event type is created, its geometry type cannot be changed.')}</strong>"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = kwargs.get('instance')

        if instance and instance.auto_resolve:
            self.fields["auto_eventtype_resolve"].initial = [
                instance.auto_resolve,
                instance.resolve_time,
            ]

    def clean_schema(self):
        schema = self.cleaned_data.get('schema')
        name = self.cleaned_data['display']
        schema_warning = f'Warning: The event type schema for {name} is not properly formatted JSON. '
        try:
            rendered_schema = get_schema_renderer_method()(schema)
        except NameError as ne:
            schema_warning += f'Received the following error: {ne}'
            messages.add_message(
                self.request, messages.WARNING, schema_warning)
        except Exception as exc:
            schema_warning += f'Received the following error: {exc}'
            messages.add_message(
                self.request, messages.WARNING, schema_warning)
        else:
            try:
                validate_rendered_schema_is_wellformed(rendered_schema)
            except SchemaValidationError as e:
                schema_warning += f'Received the following error: {e}'
                messages.add_message(
                    self.request, messages.WARNING, schema_warning)
        return schema

    def clean_auto_eventtype_resolve(self):
        data = self.cleaned_data.get('auto_eventtype_resolve')
        self.cleaned_data['auto_resolve'] = data[0]
        self.cleaned_data['resolve_time'] = data[1]
        if data[0] and not data[1]:
            raise forms.ValidationError('Please specify the number of hours')
        return data


class NotificationMethodSelectField(forms.ModelMultipleChoiceField):

    def label_from_instance(self, obj):
        return f'owner > {obj.owner.username} | {obj.method} : {obj.value}'


class AlertRuleForm(forms.ModelForm):

    def get_initial_for_field(self, field, field_name):
        value = super().get_initial_for_field(field, field_name)

        if field_name in ('conditions', 'schedule',):
            return json.dumps(value, indent=2)
        return value

    conditions = forms.CharField(widget=MonospaceTextWidget,
                                 help_text=_('The data in this field is generated by the system. Do not edit it directly.'))
    schedule = forms.CharField(widget=MonospaceTextWidget,
                               help_text=_('The data in this field is generated by the system. Do not edit it directly.'))

    notification_methods = NotificationMethodSelectField(
        queryset=NotificationMethod.objects.all(),
        required=True,
        widget=FilteredSelectMultiple(
            verbose_name=_('Notification Methods'),
            is_stacked=False))

    event_types = forms.ModelMultipleChoiceField(
        queryset=EventType.objects.all(),
        required=True,
        widget=FilteredSelectMultiple(
            verbose_name=_('Event Types'),
            is_stacked=False))

    def clean_conditions(self):

        value = self.clean_jsonfield('conditions')
        try:
            Conditions(value)
            return value
        except jsonschema.ValidationError as ve:
            rpath = '/'.join([''] + [str(x) for x in ve.relative_path])
            error_message = f'JSON schema validation error at {rpath}. Value {ve.instance} failed {ve.validator} ' \
                f'validation against {ve.validator_value}'
            raise forms.ValidationError(error_message)

    def clean_schedule(self):
        value = self.clean_jsonfield('schedule')
        try:
            OneWeekSchedule(value)
            return value
        except jsonschema.ValidationError as ve:
            rpath = '/'.join([''] + [str(x) for x in ve.relative_path])
            error_message = f'JSON schema validation error at {rpath}. Value {ve.instance} failed {ve.validator} ' \
                f'validation against {ve.validator_value}'
            raise forms.ValidationError(error_message)

    def clean_jsonfield(self, key):
        value = self.cleaned_data[key]
        try:
            return json.loads(value)
        except json.JSONDecodeError as ex:
            raise forms.ValidationError(str(ex))


class EventProviderForm(JSONFieldFormMixin, forms.ModelForm):

    provider_api = forms.URLField(label='Provider API', required=True, widget=TextInput(attrs={'size': '100'}),
                                  help_text=_('A URL or web service endpoint for the external data source.'))
    provider_username = forms.CharField(label='Provider API Username', required=False,
                                        help_text=_('If the external data source requires a username, enter it here.'))
    provider_password = forms.CharField(label='Provider API Password', required=False,
                                        help_text=_('If the external data source requires a password, enter it here.'))
    provider_token = forms.CharField(label='Provider Authorization Token', widget=TextInput(attrs={'size': '100'}),
                                     required=False,
                                     help_text=_('If you were given an authorization token for the external data source, enter it here.'))

    icon_url = forms.CharField(label='Provider Icon URL', required=False, widget=TextInput(attrs={'size': '100'}),
                               help_text=_(
                                   'A URL for an Icon to use with this Event Provider.'),
                               initial='/static/smart-logo.svg')
    external_event_url = forms.CharField(label='Provider Link', required=False, widget=TextInput(attrs={'size': '100'}),
                                         help_text=_('A web link to the user interface for this Event Provider\'s data'))

    class Meta:
        model = EventProvider
        json_fields = ('provider_api', 'provider_username',
                       'provider_password', 'provider_token',
                       'icon_url', 'external_event_url',)
        fields = ('additional',) + json_fields


class EventForm(forms.ModelForm):
    class Meta:
        labels = {
            'created_at': f'Created at {TIMEZONE_USED}',
            'updated_at': f'Updated at {TIMEZONE_USED}',
            'event_time': f'Event time in {TIMEZONE_USED}',
            'end_time': f'End Time in {TIMEZONE_USED}'
        }


class EventGeometryForm(forms.ModelForm):
    class Meta:
        model = EventGeometry
        fields = "__all__"

    def save(self, commit=True):
        if "geometry" in self.changed_data or "area" in self.changed_data:
            self.instance.properties["area"] = get_polygon_info(
                self.instance.geometry, "area")
            self.instance.properties["perimeter"] = get_polygon_info(
                self.instance.geometry, "length")
        return super().save(commit)


def reported_by_lookup():
    user_qs = get_user_model().objects.values_list('username', flat=True)
    community_qs = Community.objects.values_list('name', flat=True)
    subject_qs = Subject.objects.values_list('name', flat=True)
    return subject_qs.union(user_qs, community_qs).order_by('name')


class PatrolForm(forms.ModelForm):
    patrol_status = forms.CharField(required=False)

    class Meta:
        model = Patrol
        fields = '__all__'


class PatrolTypeForm(forms.ModelForm):
    icon = forms.CharField(required=False,
                           label='Icon',
                           widget=IconKeyInput(image_list_fn=get_icon_select_list))

    class Meta:
        model = PatrolType
        fields = '__all__'


def queryset_chain(iterables):
    for it in iterables:
        for element in it:
            yield str(element), element


def chained_tracked_by(user=None):
    query_list = [
        PatrolSegment.objects.get_leader_for_provenance(p[0], user)
        for p in PROVENANCE_CHOICES
    ]
    choices = [(None, "-----------")] + list(queryset_chain(query_list))
    return choices


class OverrideChoiceField(forms.ChoiceField):
    def to_python(self, value):
        """Return a queryset"""
        if value in self.empty_values:
            return ''
        combined_choices = dict(self.choices)
        return combined_choices.get(value)


class PatrolSegmentForm(forms.ModelForm):
    start_time = forms.SplitDateTimeField(
        widget=AdminSplitDateTime(), label="Actual start date", required=False
    )
    end_time = forms.SplitDateTimeField(
        widget=AdminSplitDateTime(), label="Actual end date", required=False
    )
    tracked_subject = OverrideChoiceField(
        label="Tracked subject name", required=False)

    class Meta:
        model = PatrolSegment
        exclude = ('time_range', 'id')
        labels = {
            "scheduled_start": "Scheduled start date",
            "scheduled_end": "Scheduled end date"
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = kwargs.get('instance')
        if instance and instance.time_range:
            self.fields['start_time'].initial = instance.time_range.lower
            self.fields['end_time'].initial = instance.time_range.upper
        if instance:
            choices = chained_tracked_by(instance.user)
            self.fields['tracked_subject'].choices = choices
            self.fields['tracked_subject'].initial = instance.leader \
                if instance.leader in dict(choices).values() else None


class PatrolSegmentStackedInline(InlineOSMGeoAdmin):
    template = 'admin/edit_inline/stacked.html'
