import logging
import math

from django import forms
from django.utils.translation import gettext_lazy as _

import analyzers.models as models
from analyzers.environmental import EnvironmentalSubjectAnalyzerConfig
from analyzers.gfw_alert_schema import GFWLayerSlugs
from analyzers.gfw_outbound import create_subscription, update_subscription
from analyzers.models.gfw import GlobalForestWatchSubscription
from core.forms_utils import FixedWidthFontTextArea, JSONFieldFormMixin

logger = logging.getLogger(__name__)


class TimeFrameWidget(forms.MultiWidget):
    template_name = 'widgets/analyzer_time.html'

    def __init__(self, attrs=None):
        widgets = [forms.NumberInput, forms.NumberInput]
        forms.MultiWidget.__init__(self, widgets, attrs)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context['hour_label'] = _('Hours:')
        context['min_label'] = _('Minutes:')
        return context

    def decompress(self, value):
        if value:
            minutes, hours = math.modf(value)
            return [int(hours), round(minutes*60)]
        return [24, 0]


class TimeFrameField(forms.fields.MultiValueField):
    widget = TimeFrameWidget
    error_message_hours = {
        'min_value': "Ensure 'value for hours' is greater than or equal to 0"}
    error_message_minutes = {'max_value': "Ensure 'value for minutes' is less than or equal to 59",
                             'min_value': "Ensure 'value for minutes' is greater than or equal to 0"}

    def __init__(self, *args, **kwargs):
        _fields = [
            forms.fields.IntegerField(
                min_value=0, max_value=2147483647, error_messages=self.error_message_hours),
            forms.fields.IntegerField(min_value=0, max_value=59, error_messages=self.error_message_minutes)]
        super().__init__(_fields, *args, **kwargs)

    def compress(self, values):
        hours, minutes = values[0], values[1]
        return hours + (minutes / 60)


class EnvironmentalAnalyzerAdminForm(JSONFieldFormMixin, forms.ModelForm):

    earth_engine_json_key = forms.CharField(label='Earth Engine JSON Key',
                                            widget=FixedWidthFontTextArea(
                                                attrs={'cols': '100', 'rows': '30'}),
                                            required=False,
                                            help_text=_(
                                                'Paste the contents of your Earth Engine JSON key here.'))
    search_time_hours = TimeFrameField(label='Analysis time frame')

    class Meta:
        model = EnvironmentalSubjectAnalyzerConfig
        json_fields = ('earth_engine_json_key',)
        fields = ('additional',) + json_fields


class GlobalForestWatchSubscriptionForm(JSONFieldFormMixin, forms.ModelForm):

    class Meta:
        model = GlobalForestWatchSubscription
        widgets = {'Fire_confidence': forms.RadioSelect,
                   'Deforestation_confidence': forms.RadioSelect}
        labels = {
            'Fire_confidence': _('Fire Alerts (VIIRS) Confidence Level'),
            'Deforestation_confidence': _('Deforestation Alerts (GLAD) Confidence Level')
        }
        fields = '__all__'
        json_fields = ('alert_types',)

    alert_types = forms.MultipleChoiceField(choices=(
        (GFWLayerSlugs.GLAD_ALERTS.value, _(
            'Deforestation alerts (GLAD) / weekly / 30m')),
        (GFWLayerSlugs.VIIRS_ACTIVE_FIRES.value, _(
            'Fire Alerts (VIIRS) / daily / 375m')),
    ), help_text='Click to select one, SHIFT+click to select both')
    glad_confirmed_backfill_days = forms.IntegerField(initial=180,
                                                      max_value=365,
                                                      min_value=10,
                                                      label=_(
                                                          'Number of days to backfill for confirmed GLAD alerts'),
                                                      help_text=_('Valid range: 10-365 days.'))

    def clean(self):
        res = super().clean()

        if len(self.errors) == 0:
            # form data is good, do gfw operations
            model_info = self.get_gfw_info(self.cleaned_data)
            if GlobalForestWatchSubscription.objects.filter(pk=self.instance.pk).exists():
                model = GlobalForestWatchSubscription.objects.get(
                    pk=self.instance.pk)
                model_info['geostore_id'] = model.geostore_id
                model_info['subscription_id'] = model.subscription_id
                geometry_changed = 'subscription_geometry' in self.changed_data
                service_response = update_subscription(
                    model_info, geometry_changed)
            else:
                service_response = create_subscription(model_info)

            status_code = service_response.get('status_code')
            if status_code == 200:
                data = service_response.get('data')
                self.instance.subscription_id = data['subscription_id']
                self.instance.geostore_id = data['geostore_id']
            else:
                raise forms.ValidationError(service_response.get('text'))

        return res

    def get_gfw_info(self, cleaned_data):
        return {
            'name': cleaned_data.get('name'),
            'subscription_id': cleaned_data.get('subscription_id'),
            'geostore_id': cleaned_data.get('geostore_id'),
            'alert_types': cleaned_data['alert_types'],
            'subscription_geometry': cleaned_data['subscription_geometry'],
        }


class BaseAnalyzerForm(forms.ModelForm):
    search_time_hours = TimeFrameField(label='Analysis time frame')

    class Meta:
        fields = '__all__'


class GeofenceSubjectAnalyzerForm(BaseAnalyzerForm):
    BaseAnalyzerForm.Meta.model = models.GeofenceAnalyzerConfig


class ImmobilityAnalyzerForm(BaseAnalyzerForm):
    BaseAnalyzerForm.Meta.model = models.ImmobilityAnalyzerConfig


class FeatureProximityAnalyzerForm(BaseAnalyzerForm):
    BaseAnalyzerForm.Meta.model = models.FeatureProximityAnalyzerConfig


class SubjectProximityAnalyzerForm(forms.ModelForm):
    analysis_search_time_hours = TimeFrameField(
        label='Analysis time frame', initial=1,
        help_text=_(
            'Analysis will be performed on recent data within this time frame.')
    )
    proximity_time = TimeFrameField(
        initial=1, label='Proximity Time',
        help_text=_("A proximity event will only occur when the two subject's position points occur within this time."))

    class Meta:
        fields = '__all__'
        model = models.SubjectProximityAnalyzerConfig


class LowSpeedWilcoxSubjectAnalyzerForm(BaseAnalyzerForm):
    BaseAnalyzerForm.Meta.model = models.LowSpeedWilcoxAnalyzerConfig


class LowSpeedPercentileSubjectAnalyzerForm(BaseAnalyzerForm):
    BaseAnalyzerForm.Meta.model = models.LowSpeedPercentileAnalyzerConfig
