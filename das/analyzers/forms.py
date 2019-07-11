import json
import logging

import geojson
import requests
from django import forms
from django.conf import settings
from django.utils.translation import ugettext_lazy as _
from rest_framework import status

from analyzers.environmental import EnvironmentalSubjectAnalyzerConfig
from analyzers.models.gfw import GlobalForestWatchSubscription
from core.forms_utils import JSONFieldFormMixin, FixedWidthFontTextArea
from django.urls import reverse
from sensors.gfw_alert_handler import GFWAlertHandler

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

        fields = '__all__'
        json_fields = ('alert_types', 'gfw_auth_token')

    alert_types = forms.MultipleChoiceField(choices=(
        ('glad-alerts', _('Deforestation alerts (GLAD) / weekly / 30m')),
        ('terrai-alerts', _('Deforestation alerts (Terra-i) / monthly / 250m')),
        ('viirs-active-fires', _('Fire Alerts (VIIRS) / daily / 375m')),
    ))

    gfw_auth_token = forms.CharField(max_length=300, help_text=_('Authorization token for Global Forest Watch API.'))

    def save(self, commit=True):
        # TODO: how is this commit flag used?? seems to be set as false when save is called.
        # logger.debug('GlobalForestWatchSubscriptionForm SAVE ENTERED')
        if self.is_valid():
            m = super(GlobalForestWatchSubscriptionForm, self).save(commit=False)

            spatial_features = m.spatial_feature_group.features.all()

            feature_collection = geojson.FeatureCollection([
                geojson.Feature(geometry=geojson.loads(f.feature_geometry.geojson)) for f in spatial_features
            ])

            # subscribe for new or update subscription. subscribe_alerts in subscription_manager.py
            if not m.subscription_id:
                logger.debug('will create new subscription')

                # geostore creation will probably move out of here...
                if not m.geostore_id:
                    rsp = requests.post(url=f'{settings.GFW_API_ROOT}/geostore', json={'geojson': feature_collection})
                    if rsp.status_code == status.HTTP_200_OK:
                        geostore_rsp = json.loads(rsp.text)
                        m.geostore_id = geostore_rsp['data']['id']

                subscribe_json = self._build_subscribe_msg(m)
                rsp = requests.post(url=f'{settings.GFW_API_ROOT}/subscriptions',
                                    headers={'Authorization': f'Bearer {settings.GFW_AUTH_TOKEN}'},
                                    json=subscribe_json)

                if rsp.status_code == status.HTTP_200_OK:
                    m.subscription_id = json.loads(rsp.text)['data']['id']
                    logger.info(f'subscription successful. id: {m.subscription_id}')

            else:
                # TODO
                logger.info('need to modify subscription')

            # TODO:
            if commit:
                m.save()

            return m

    def _build_subscribe_msg(self, model):
        subsciption = dict()
        subsciption.update([
            ('name', model.name),
            ('application', 'gfw'),
            ('language', 'en')
        ])

        subsciption['datasets'] = ["glad-alerts", "terrai-alerts", "viirs-active-fires"],
        subsciption['resource'] = {
            'type': 'URL',
            'content': f'{self.webhook_base_url}/{model.id.hex}/status?auth={settings.ER_APP_AUTH_TOKEN}'}
        subsciption['params'] = {'geostore': model.geostore_id}

        return subsciption
