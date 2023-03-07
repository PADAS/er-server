from math import isclose

from django import forms
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.contrib.gis.geos import Point
from django.contrib.postgres.forms import JSONField
from django.utils.translation import gettext_lazy as _

from choices.models import Choice
from core.common import TIMEZONE_USED
from core.forms_utils import JSONFieldFormMixin
from mapping.models import (ArcgisConfiguration, DisplayCategory, FeatureType,
                            Map, SpatialFeatureGroupStatic, SpatialFeatureType,
                            TileLayer)


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
        labels = {
            'created_at': f'Created at {TIMEZONE_USED}',
            'updated_at': f'Updated at {TIMEZONE_USED}',
        }


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


class SpatialFeatureGroupStaticForm(forms.ModelForm):
    spatialfeaturegroupstatic = forms.ModelChoiceField(
        queryset=SpatialFeatureGroupStatic.objects.all(), label='Feature Groups')

    class Meta:
        model = SpatialFeatureGroupStatic
        fields = ('spatialfeaturegroupstatic',)


class PresentationWidget(forms.Textarea):
    template_name = 'admin/mapping/featuretype/presentation_textarea.html'

    def __init__(self, attrs=None):
        # Use slightly better defaults than HTML's 20x2 box
        default_attrs = {'cols': '50', 'rows': '100'}
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs)

    class Media:
        css = {
            'all': ('css/presentation_textarea.css',),
        }


class BaseFeatureTypeForm(forms.ModelForm):
    presentation = JSONField(widget=PresentationWidget(
        attrs={'rows': 20, 'cols': 80}))

    class Meta:
        abstract = True


class FeatureTypeForm(BaseFeatureTypeForm):
    class Meta:
        model = FeatureType
        fields = ['id', 'name', 'presentation', ]


class SpatialFeatureTypeForm(BaseFeatureTypeForm):
    class Meta:
        model = SpatialFeatureType
        fields = '__all__'


class DisplayCategoryForm(forms.ModelForm):
    class Meta:
        model = DisplayCategory
        fields = ['id', 'name', 'feature_classes', 'description', ]

    feature_classes = forms.ModelMultipleChoiceField(
        queryset=SpatialFeatureType.objects.all().order_by('name'),
        required=False,
        widget=FilteredSelectMultiple(
            verbose_name=_('Feature Classes'),
            is_stacked=False))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk:
            self.fields['feature_classes'].initial = self.instance.spatialfeaturetype_set.all()

    def save(self, commit=True):
        instance = super().save(commit)
        instance.spatialfeaturetype_set.set(
            self.cleaned_data['feature_classes'])
        return instance


class ArcgisConfigurationForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput(render_value=True))
    disable_import_feature_class_presentation = forms.BooleanField(
        widget=forms.CheckboxInput(),
        help_text=(
            'Check to pause the importing of Feature Class presentation.  '
            'Note, Feature Class names will still be imported. This will not '
            'affect the importing of Features.'
        ),
        required=False
    )

    class Meta:
        model = ArcgisConfiguration
        fields = '__all__'
