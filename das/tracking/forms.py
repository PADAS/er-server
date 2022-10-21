import re

from django import forms
from django.contrib.contenttypes.models import ContentType
from django.utils.translation import gettext_lazy as _

from tracking.models import (AWETelemetryPlugin, AwtPlugin, FirmsPlugin,
                             InreachKMLPlugin, InreachPlugin, SavannahPlugin,
                             SirtrackPlugin, SkygisticsSatellitePlugin,
                             SourcePlugin, SpiderTracksPlugin,
                             VectronicsPlugin)


def list_of_plugins():
    for cls in (
        SavannahPlugin,
        AWETelemetryPlugin,
        AwtPlugin,
        SkygisticsSatellitePlugin,
        FirmsPlugin,
        SpiderTracksPlugin,
        InreachKMLPlugin,
        InreachPlugin,
        VectronicsPlugin,
        SirtrackPlugin,
    ):
        yield from list(cls.objects.all())


class SourcePluginForm(forms.ModelForm):

    plugin_choice = forms.ChoiceField(
        required=False, label=_("Plugin Configuration"))
    status = forms.ChoiceField(
        choices=(
            ("enabled", "Enabled"),
            ("disabled", "Disabled"),
        )
    )

    class Meta:
        model = SourcePlugin

        fields = (
            "source",
            "plugin_choice",
            "cursor_data",
            "status",
        )

    @staticmethod
    def _encode_plugin_identifier(obj):
        type_id = ContentType.objects.get_for_model(obj.__class__).id
        obj_id = obj.id
        form_value = f"{type_id}:::{obj_id}"
        display_text = f"{obj.name} ({obj._meta.verbose_name})"
        return (form_value, display_text)

    @staticmethod
    def _decode_plugin_identifier(encvalue):
        matches = re.match("(\d+):::([\w\-]+)", encvalue).groups()

        print(matches)
        plugin_type_id = matches[0]
        plugin_object_id = matches[1]
        return (plugin_type_id, plugin_object_id)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["plugin_choice"].choices = sorted(
            [self._encode_plugin_identifier(obj) for obj in list_of_plugins()],
            key=lambda x: x[1],
        )

    def get_initial_for_field(self, field, field_name):

        if field_name == "plugin_choice":
            try:
                if self.instance:
                    plugin = self.instance.plugin
            except AttributeError:
                pass
            else:
                if plugin:
                    return self._encode_plugin_identifier(plugin)

        return super().get_initial_for_field(field, field_name)

    def save(self, *args, **kwargs):

        plugin_string = self.cleaned_data["plugin_choice"]

        plugin_type_id, plugin_object_id = self._decode_plugin_identifier(
            plugin_string)
        plugin_type = ContentType.objects.get(id=plugin_type_id)

        self.cleaned_data["plugin_type"] = plugin_type_id
        self.cleaned_data["plugin_id"] = plugin_object_id

        self.instance.plugin_id = plugin_object_id
        self.instance.plugin_type = plugin_type

        return super().save(*args, **kwargs)
