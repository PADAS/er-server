import logging

from django import forms
from django.utils.translation import ugettext_lazy as _

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

    gfw_auth_token = forms.CharField(widget=forms.Textarea,
                                     help_text=_('Authorization token for Global Forest Watch API.'))

    def save(self, commit=True):
        # TODO: how is this commit flag used?? seems to be set as false when save is called.
        # logger.debug('GlobalForestWatchSubscriptionForm SAVE ENTERED')
        if self.is_valid():
            m = super(GlobalForestWatchSubscriptionForm, self).save(commit=False)

            # TODO:
            if commit:
                m.save()

            return m
