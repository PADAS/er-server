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


class GlobalForestWatchSubscriptionForm(forms.ModelForm):
    class Meta:
        model = GlobalForestWatchSubscription
        fields = '__all__'

    def save(self, commit=True):
        # TODO: how is this commit flag used?? seems to be set as false when save is called.
        # print('GlobalForestWatchSubscriptionForm SAVE ENTERED')
        m = super(GlobalForestWatchSubscriptionForm, self).save(commit=False)

        spatial_features = m.spatial_feature_group.features.all()

        feature_collection = geojson.FeatureCollection([
            geojson.Feature(geometry=geojson.loads(f.feature_geometry.geojson)) for f in spatial_features
        ])

        # subscribe for new or update subscription. subscribe_alerts in subscription_manager.py
        if not m.subscription_id:
            print('will create new subscription')
            if not m.geostore_id:
                rsp = requests.post(url=f'{settings.GFW_API_ROOT}/geostore', json={'geojson': feature_collection})
                if rsp.status_code == status.HTTP_200_OK:
                    geostore_rsp = json.loads(rsp.text)
                    m.geostore_id = geostore_rsp['data']['id']

            subscribe_json = self._build_subscribe_msg(m)
            rsp = requests.post(url=f'{settings.GFW_API_ROOT}/subscriptions',
                                headers={'Authorization': f'Bearer {settings.GFW_AUTH_TOKEN}'},
                                json=subscribe_json)

        else:
            print('need to modify subscription')

        # TODO:
        if commit:
            m.save()

        return m

    def _build_subscribe_msg(self, model):
        subs = dict()
        subs.update([
            ('name', model.name),
            ('application', 'gfw'),
            ('language', 'en')
        ])

        subs['datasets'] = ["glad-alerts", "terrai-alerts", "viirs-active-fires"],
        subs['resource'] = {'type': 'URL',
                            'content': 'https://gfw-alerts-dev.pamdas.org/alert'}
        subs['params'] = {'geostore': model.geostore_id}

        return subs




