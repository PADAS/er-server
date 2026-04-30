import re
from math import isclose

from django import forms
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.contrib.gis.geos import Point
from django.core.exceptions import ValidationError
from django.forms import JSONField
from django.utils.translation import gettext_lazy as _

from choices.models import Choice
from core.common import TIMEZONE_USED
from core.forms_utils import JSONFieldFormMixin
from mapping.models import (
    ArcgisConfiguration,
    DisplayCategory,
    Map,
    SpatialFeatureGroupStatic,
    SpatialFeatureType,
    TileLayer,
)


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
        exclude = [
            "das_tenant",
        ]
        widgets = {"center": forms.HiddenInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.starting_center = self.initial.get("center", None)
        if not isinstance(self.starting_center, Point):
            self.starting_center = Point(0, 0)

        if "longitude" not in self.initial:
            self.initial["longitude"], self.initial["latitude"] = self.starting_center.tuple

    def clean(self):
        data = super().clean()
        map_control_center = data.get("center", None)
        latitude = data.get("latitude", None)
        longitude = data.get("longitude", None)
        if latitude and longitude:
            manual_center = Point(float(longitude), float(latitude))
        else:
            manual_center = None

        # If map control center exists and it's changed from the starting center
        # Use the data specified in the map control
        if map_control_center and not self.samepoint(map_control_center, self.starting_center):
            data["center"] = map_control_center
        # If the map control has not been changed, see if the manual latlon has
        # been changed, and use those as the new values
        elif manual_center and not self.samepoint(manual_center, self.starting_center):
            data["center"] = manual_center
        else:
            pass

        return data

    def samepoint(self, point_a, point_b):
        return isclose(point_a.x, point_b.x, rel_tol=1e-10) and isclose(point_a.y, point_b.y, rel_tol=1e-10)


class TileLayerForm(forms.ModelForm):
    class Meta:
        fields = "__all__"
        model = TileLayer
        labels = {
            "created_at": f"Created at {TIMEZONE_USED}",
            "updated_at": f"Updated at {TIMEZONE_USED}",
        }


class TileLayerFormWithAttributes(JSONFieldFormMixin, TileLayerForm):
    type = forms.ChoiceField(required=True, label="Map Layer service Type")
    title = forms.CharField(required=False, label="Title")
    url = forms.CharField(required=False, label="URL")
    icon_url = forms.CharField(required=False, label="Icon URL")
    configuration = JSONField(
        required=False, label="Service Configuration", widget=forms.Textarea(attrs={"rows": 4, "cols": 80})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["type"].choices = self.fetch_service_types()

    @staticmethod
    def fetch_service_types():
        service_type_choices = {}
        for service_type in Choice.objects.filter(model="mapping.TileLayer", field="service_type").order_by("ordernum"):
            service_type_choices[service_type.value] = service_type.display
        return tuple([(key, value) for key, value in service_type_choices.items()])

    class Meta(TileLayerForm.Meta):
        json_fields = ("type", "title", "url", "icon_url", "configuration")

    json_field = "attributes"

    def save(self, *args, **kwargs):
        commit = kwargs.pop("commit", True)
        instance = super().save(*args, commit=False, **kwargs)

        # clear out null json fields
        for field in self.Meta.json_fields:
            attributes = getattr(instance, self.json_field)
            if attributes[field] is None or (isinstance(attributes[field], str) and attributes[field] == ""):
                del attributes[field]
        if commit:
            instance.save()
        return instance


class SpatialFeatureGroupStaticForm(forms.ModelForm):
    spatial_feature_groupstatic = forms.ModelChoiceField(
        queryset=SpatialFeatureGroupStatic.objects.all(), label="Feature Groups"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["spatial_feature_groupstatic"].queryset = SpatialFeatureGroupStatic.objects.all()

    class Meta:
        model = SpatialFeatureGroupStatic
        fields = ("spatial_feature_groupstatic",)


class ColorPickerWidget(forms.TextInput):
    template_name = "admin/mapping/spatialfeaturetype/color_picker_widget.html"

    def __init__(self, *args, default_color=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.default_color = default_color or ""

    def get_context(self, name, value, attrs):
        ctx = super().get_context(name, value, attrs)
        ctx["widget"]["default_color"] = self.default_color
        return ctx

    class Media:
        css = {
            "all": ("css/color_picker_widget.css",),
        }


class SpatialFeatureTypeForm(forms.ModelForm):
    # Maps form field names to their keys in the presentation JSON.
    PRESENTATION_FORM_FIELDS = {
        "stroke": "stroke",
        "stroke_width": "stroke-width",
        "stroke_opacity": "stroke-opacity",
        "point_image": "image",
        "point_width": "width",
        "point_height": "height",
        "fill_opacity": "fill-opacity",
        "fill_outline_color": "fill-outline-color",
        "fill_color": "fill",
    }

    presentation = JSONField(
        widget=forms.Textarea(attrs={"rows": 20, "cols": 80}),
        required=False,
        help_text="Live JSON representation of the formatting controls above. Edit directly for advanced use.",
    )

    def validate_hex_color(value):
        if value and not re.fullmatch(r"#[0-9a-fA-F]{3}([0-9a-fA-F]{3})?", value):
            raise ValidationError(_("Enter a valid hex color (e.g. #fff or #ffffff)."))

    stroke_width = forms.IntegerField(
        min_value=1,
        required=False,
        label="Stroke Width",
        initial=2,
    )
    stroke_opacity = forms.FloatField(
        min_value=0,
        max_value=1,
        required=False,
        label="Stroke Opacity",
        initial=1,
        widget=forms.NumberInput(attrs={"type": "range", "min": "0", "max": "1", "step": "0.01"}),
    )
    fill_opacity = forms.FloatField(
        min_value=0,
        max_value=1,
        required=False,
        label="Fill Opacity",
        initial=0.25,
        widget=forms.NumberInput(attrs={"type": "range", "min": "0", "max": "1", "step": "0.01"}),
    )
    point_image = forms.CharField(max_length=500, required=False, label="Image")
    point_width = forms.FloatField(min_value=1, required=False, label="Width", initial=20, max_value=100)
    point_height = forms.FloatField(min_value=1, required=False, label="Height", initial=20, max_value=100)
    stroke = forms.CharField(
        max_length=50,
        required=False,
        label="Stroke Color",
        initial="#FF6600",
        widget=ColorPickerWidget,
        validators=[validate_hex_color],
    )
    fill_outline_color = forms.CharField(
        max_length=50,
        required=False,
        label="Fill Outline Color",
        initial="#FF6600",
        widget=ColorPickerWidget,
        validators=[validate_hex_color],
    )
    fill_color = forms.CharField(
        max_length=50,
        required=False,
        label="Fill Color",
        initial="#FF6600",
        widget=ColorPickerWidget,
        validators=[validate_hex_color],
    )

    class Meta:
        model = SpatialFeatureType
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.presentation:
            presentation = self.instance.presentation
            for field_name, json_key in self.PRESENTATION_FORM_FIELDS.items():
                if json_key in presentation:
                    self.initial[field_name] = presentation[json_key]
            # Legacy synonym: SimpleStyle uses "fill"; older data may have "fill-color".
            if "fill" not in presentation and "fill-color" in presentation:
                self.initial["fill_color"] = presentation["fill-color"]
        for field_name, form_field in self.fields.items():
            if isinstance(form_field.widget, ColorPickerWidget):
                form_field.widget.default_color = self.initial.get(field_name) or form_field.initial or ""

    def save(self, commit=True):
        instance = super().save(commit=False)
        if not self.cleaned_data.get("presentation"):
            presentation = {}
            for field_name, json_key in self.PRESENTATION_FORM_FIELDS.items():
                value = self.cleaned_data.get(field_name)
                if value not in (None, ""):
                    presentation[json_key] = value
            instance.presentation = presentation
        # Drop the legacy Mapbox paint name once the canonical SimpleStyle "fill" is set.
        if instance.presentation and "fill" in instance.presentation:
            instance.presentation.pop("fill-color", None)
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class DisplayCategoryForm(forms.ModelForm):
    class Meta:
        model = DisplayCategory
        fields = [
            "id",
            "name",
            "feature_classes",
            "description",
        ]

    feature_classes = forms.ModelMultipleChoiceField(
        queryset=SpatialFeatureType.objects.none(),
        required=False,
        label=_("Feature Types"),
        widget=FilteredSelectMultiple(verbose_name=_("Feature Types"), is_stacked=False),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["feature_classes"].queryset = SpatialFeatureType.objects.all().order_by("name")

        if self.instance and self.instance.pk:
            self.fields["feature_classes"].initial = self.instance.spatialfeaturetype_set.all()

    def clean_name(self):
        name = self.cleaned_data.get("name")
        if not name:
            return name
        qs = DisplayCategory.objects.filter(name=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(
                _("A display category with this name already exists for this tenant."),
                code="unique",
            )
        return name

    def save(self, commit: bool = True) -> DisplayCategory:
        instance = super().save(commit=False)
        if commit:
            instance.save()
            self.save_m2m()
        return instance

    def _save_m2m(self) -> None:
        # feature_classes is a reverse-FK pseudo-M2M not handled by Django's standard _save_m2m.
        super()._save_m2m()
        self.instance.spatialfeaturetype_set.set(self.cleaned_data.get("feature_classes", []))


class ArcgisConfigurationForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput(render_value=True))
    disable_import_feature_class_presentation = forms.BooleanField(
        widget=forms.CheckboxInput(),
        help_text=(
            "Check to pause the importing of Feature Type presentation.  "
            "Note, Feature Type names will still be imported. This will not "
            "affect the importing of Features."
        ),
        required=False,
    )

    class Meta:
        model = ArcgisConfiguration
        fields = "__all__"
