from math import isclose
from django import forms
from django.contrib.admin.widgets import FilteredSelectMultiple, AdminDateWidget
from django.contrib.gis.geos import Point
from django.contrib.postgres.forms import JSONField

from core.forms_utils import JSONFieldFormMixin, ColorPickerWidget, AssignedDateTimeRangeField
from mapping.models import Map, TileLayer
from choices.models import Choice


class MapCenterForm(forms.ModelForm):

    latitude = forms.FloatField(
        min_value=-90,
        max_value=90,
        required=True,
    )
    longitude = forms.FloatField(
        min_value=-180,
        max_value=180,
        required=True,
    )

    class Meta(object):
        model = Map
        exclude = []
        widgets = {'center': forms.HiddenInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.starting_center = self.initial.get('center', None)
        if not isinstance(self.starting_center, Point):
            self.starting_center = Point(0, 0)

        if 'longitude' not in self.initial:
            self.initial['longitude'], self.initial['latitude'] = self.starting_center.tuple

    def clean(self):
        data = super().clean()
        map_control_center = data.get('center', None)
        latitude = data.get('latitude', None)
        longitude = data.get('longitude', None)
        if latitude and longitude:
            manual_center = Point(float(longitude), float(latitude))
        else:
            manual_center = None

        # If map control center exists and it's changed from the starting center
        # Use the data specified in the map control
        if map_control_center and not self.samepoint(map_control_center, self.starting_center):
            data['center'] = map_control_center
        # If the map control has not been changed, see if the manual latlon has
        # been changed, and use those as the new values
        elif manual_center and not self.samepoint(manual_center, self.starting_center):
            data['center'] = manual_center
        else:
            pass

        return data

    def samepoint(self, point_a, point_b):
        return isclose(point_a.x, point_b.x, rel_tol=1e-10) and \
            isclose(point_a.y, point_b.y, rel_tol=1e-10)


class TileLayerForm(forms.ModelForm):
    class Meta:
        fields = '__all__'
        model = TileLayer


class TileLayerFormWithAttributes(JSONFieldFormMixin, TileLayerForm):
    type = forms.ChoiceField(
        required=True, label='Map Layer service Type')
    title = forms.CharField(required=False, label='Title')
    url = forms.CharField(required=False, label='URL')
    icon_url = forms.CharField(required=False, label='Icon URL')
    configuration = JSONField(required=False, label='Service Configuration',
                              widget=forms.Textarea(
                                  attrs={'rows': 4, 'cols': 80}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['type'].choices = self.fetch_service_types()

    @staticmethod
    def fetch_service_types():
        service_type_choices = {}
        for service_type in Choice.objects.filter(
                model='mapping.TileLayer',
                field='service_type').order_by('ordernum'):
            service_type_choices[service_type.value] = service_type.display
        return tuple([(key, value)
                      for key, value in service_type_choices.items()])

    class Meta(TileLayerForm.Meta):
        json_fields = ('type', 'title', 'url', 'icon_url', 'configuration')

    json_field = 'attributes'

    def save(self, *args, **kwargs):
        commit = kwargs.pop('commit', True)
        instance = super().save(*args,
                                commit=False,
                                **kwargs)

        # clear out null json fields
        for field in self.Meta.json_fields:
            attributes = getattr(instance, self.json_field)
            if (attributes[field] is None or
                    (isinstance(attributes[field], str) and attributes[field] == '')):
                del attributes[field]
        if commit:
            instance.save()
        return instance
