import logging

from django import forms
from django.utils.translation import ugettext_lazy as _

from analyzers.environmental import EnvironmentalSubjectAnalyzerConfig
from analyzers.models.gfw import GlobalForestWatchSubscription
from analyzers.gfw_outbound import create_subscription, update_subscription
from core.forms_utils import JSONFieldFormMixin, FixedWidthFontTextArea

logger = logging.getLogger(__name__)


class EnvironmentalAnalyzerAdminForm(JSONFieldFormMixin, forms.ModelForm):

    earth_engine_json_key = forms.CharField(label='Earth Engine JSON Key',
                                            widget=FixedWidthFontTextArea(attrs={'cols': '100', 'rows': '30'}),
                                            required=False,
                                            help_text=_(
                                                'Paste the contents of your Earth Engine JSON key here.'))

    class Meta:
        model = EnvironmentalSubjectAnalyzerConfig
        json_fields = ('earth_engine_json_key',)
        fields = ('additional',) + json_fields


class GlobalForestWatchSubscriptionForm(JSONFieldFormMixin, forms.ModelForm):

    class Meta:
        model = GlobalForestWatchSubscription
        widgets = {'Fire_confidence': forms.RadioSelect, 'Deforestation_confidence': forms.RadioSelect}
        labels = {
            'Fire_confidence': 'Fire Alerts (VIIRS) Confidence Level',
            'Deforestation_confidence': 'Deforestation Alerts (GLAD) Confidence Level'
        }
        fields = '__all__'
        json_fields = ('alert_types',)

    alert_types = forms.MultipleChoiceField(choices=(
        ('glad-alerts', _('Deforestation alerts (GLAD) / weekly / 30m')),
        ('viirs-active-fires', _('Fire Alerts (VIIRS) / daily / 375m')),
    ), help_text='Click to select one, SHIFT+click to select both')

    def clean(self):
        res = super().clean()

        if len(self.errors) == 0:
            # form data is good, do gfw operations
            model_info = self.get_gfw_info(self.cleaned_data)
            if GlobalForestWatchSubscription.objects.filter(pk=self.instance.pk).exists():
                model = GlobalForestWatchSubscription.objects.get(pk=self.instance.pk)
                model_info['geostore_id'] = model.geostore_id
                model_info['subscription_id'] = model.subscription_id
                geometry_changed = 'subscription_geometry' in self.changed_data
                service_response = update_subscription(model_info, geometry_changed)
            else:
                service_response = create_subscription(model_info)

            status_code = service_response.get('status_code')
            if status_code == 200:
                data = service_response.get('data')
                self.instance.subscription_id = data['subscription_id']
                self.instance.geostore_id = data['geostore_id']
            else:
                err_text = service_response.get('text')
                raise forms.ValidationError(f'Error code: {status_code} message: {err_text}')

        return res

    def get_gfw_info(self, cleaned_data):
        return {
            'name': cleaned_data.get('name'),
            'subscription_id': cleaned_data.get('subscription_id'),
            'geostore_id': cleaned_data.get('geostore_id'),
            'alert_types': cleaned_data['alert_types'],
            'subscription_geometry': cleaned_data['subscription_geometry'],
        }

