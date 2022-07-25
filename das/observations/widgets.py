import json
import logging

from django.forms import (CheckboxInput, MultiWidget, Select, Textarea,
                          TextInput, URLInput)
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from observations.message_adapters import ADAPTER_MAPPING
from observations.models import Subject

logger = logging.getLogger(__name__)


class CustomSelectWidgetForContentType(Select):
    def __init__(self, attrs=None, choices=()):
        super().__init__(attrs, choices)

    def create_option(
        self, name, value, label, selected, index, subindex=None, attrs=None
    ):
        options = super().create_option(
            name, value, label, selected, index, subindex, attrs
        )
        try:
            print(f"\noptions: {options['label']}\n")
            label = options["label"]
            if "|" in label:
                label = label.split("|")[1].strip()
                options["label"] = label
            return options
        except IndexError:
            return options


class TransformationRuleWidget(MultiWidget):
    template_name = "admin/transformation_rule.html"

    def __init__(self, attrs=None, provider=None, transform_rules=None):
        self.provider = provider or {}
        self.transform_rules = transform_rules or []
        widgets = [
            CheckboxInput,
            TextInput(attrs={"id": "transform_label"}),
            TextInput({"id": "transform_unit"}),
        ]
        widgets = widgets * len(provider) if provider else widgets
        MultiWidget.__init__(self, widgets, attrs)

    def _get_context(self, name, value, attrs):
        context = {
            "widget": {
                "name": name,
                "is_hidden": self.is_hidden,
                "required": self.is_required,
                "value": self.format_value(value),
                "attrs": self.build_attrs(self.attrs, attrs),
                "template_name": self.template_name,
            }
        }
        return context

    @staticmethod
    def get_dest(key):
        val = key.split(".")
        return val[-1] if val[-1] != "[]" else val[-2]

    def get_context(self, name, value, attrs):
        # value correspondes to values of JSON transformation rules.
        value = self.transform_rules
        context = self._get_context(name, value, attrs)
        if self.is_localized:
            for widget in self.widgets:
                widget.is_localized = self.is_localized
        # value is a list of values, each corresponding to a widget
        # in self.widgets.
        if not isinstance(value, list):
            value = self.decompress(value)

        final_attrs = context["widget"]["attrs"]
        input_type = final_attrs.pop("type", None)
        id_ = final_attrs.get("id")
        subwidgets = []
        list_subwidgets = []

        for _, key in enumerate(sorted(self.provider.keys())):
            for i, widget in enumerate(self.widgets):
                if input_type is not None:
                    widget.input_type = input_type
                widget_name = "%s_%s" % (name, i)
                try:
                    widget_value = None
                    for x in value:
                        if x.get("dest") == self.get_dest(key):
                            vals = list(x.values())
                            widget_value = vals[i]
                except IndexError:
                    widget_value = None
                except AttributeError:
                    widget_value = None
                if id_:
                    widget_attrs = final_attrs.copy()
                    widget_attrs["id"] = "%s_%s" % (
                        widget.attrs.get("id") or id_, _)
                else:
                    widget_attrs = final_attrs
                subwidgets.append(
                    widget.get_context(widget_name, widget_value, widget_attrs)[
                        "widget"
                    ]
                )
            list_subwidgets.append(subwidgets)
            subwidgets = []
        context["widget"]["subwidgets"] = list_subwidgets
        context["sample_data"] = json.loads(
            json.dumps(self.provider, sort_keys=True, indent=4)
        )
        context["default_feature"] = self._get_default_feature(
            self.transform_rules)
        return context

    def render(self, name, value, attrs=None, renderer=None):
        """Render the widget as an HTML string."""
        context = self.get_context(name, value, attrs)
        return self._render(self.template_name, context, renderer)

    def decompress(self, value):
        return [] if value is None else value

    def _get_default_feature(self, transform_rules):
        if transform_rules:
            for rule in transform_rules:
                if rule.get("default"):
                    return rule.get("dest")
        return None


def msg_adapter_choices():
    choices = [(None, "")]
    for key in ADAPTER_MAPPING:
        choices.append((key, key))
    return choices


class MessageConfigurationWidget(MultiWidget):
    template_name = "admin/widgets/message_widget.html"

    def __init__(self, attrs=None):
        widgets = [
            Select(choices=msg_adapter_choices()),
            URLInput(attrs={"size": 40}),
            TextInput(attrs={"size": 40}),
        ]
        super().__init__(widgets, attrs)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context["url_label"] = _("URL: ")
        context["adaptkey_label"] = _("Adapter Type: ")
        context["apikey_label"] = _("API key: ")
        return context

    def decompress(self, value):
        return (
            [value.get("adapter_type"), value.get("url"), value.get("apikey")]
            if value
            else []
        )


class AutoFormatJSONWidget(Textarea):
    def __init__(self, attrs=None):
        # Use slightly better defaults than HTML's 20x2 box
        default_attrs = {"cols": "80", "rows": "30"}
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs)

    def format_value(self, value):
        try:
            deserialize = json.loads(value)
            value = json.dumps(deserialize, indent=2, sort_keys=True)
        except Exception as e:
            logger.warning("Error while formatting JSON: {}".format(e))
            return super().format_value(value)
        else:
            if isinstance(deserialize, dict) and not bool(deserialize):
                return json.dumps([])
            else:
                # these lines will try to adjust size of TextArea to fit to content
                row_lengths = [len(r) for r in value.split("\n")]
                self.attrs["rows"] = min(max(len(row_lengths) + 2, 10), 30)
                return value

    class Media:
        css = {
            "all": ("css/monospace_textarea.css",),
        }


class MessageGenericForeignKeyRawIdWidget(TextInput):
    """Widget for displaying Dynamic GenericForeignkey in 'raw_id' rather than select box"""

    template_name = "admin/widgets/genericforeign_raw_id.html"

    def __init__(self, rel, admin_site, attrs=None, using=None, content_type="subject"):
        self.rel = rel
        self.admin_site = admin_site
        self.db = using
        self.content_type = content_type
        super().__init__(attrs)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        rel_to = Subject  # default to Subject object.
        related_url = reverse(
            "admin:%s_%s_changelist"
            % (
                rel_to._meta.app_label,
                rel_to._meta.model_name,
            ),
            current_app=self.admin_site.name,
        )
        context["related_url"] = related_url
        context["link_title"] = _("Lookup")
        context["widget"]["attrs"].setdefault(
            "class", "vForeignKeyRawIdAdminField")
        if context["widget"]["value"]:
            context["link_label"], context["link_url"] = self.label_and_url_for_value(
                value
            )
        else:
            context["link_label"] = None
        return context

    def label_and_url_for_value(self, value):
        try:
            obj = Subject.objects.get(id=value)
        except Subject.DoesNotExist:
            from accounts.models import User

            obj = User.objects.get(id=value)
        url = reverse(
            "%s:%s_%s_change"
            % (
                self.admin_site.name,
                obj._meta.app_label,
                obj._meta.object_name.lower(),
            ),
            args=(obj.pk,),
        )
        return obj, url
