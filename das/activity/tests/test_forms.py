import itertools
import json
from unittest import skipIf

import pytest

from django import forms
from django.contrib.staticfiles import finders
from django.test import TestCase

from activity.exceptions import SCHEMA_ERROR_MISSING_DOLLAR_SIGN_SCHEMA
from activity.forms import (
    SCHEMA_ERROR_JSON_DECODE_ERROR,
    AlertRuleForm,
    EventTypeForm,
    PrettyReadOnlyJSONWidget,
)
from activity.models import AlertRule

EVENT_SCHEMA = """{\n    "schema": {\n        "$schema": "http://json-schema.org/draft-04/schema#",\n        "title": "Rhino Sighting (rhino_sighting_rep)",\n      \n        "type": "object",\n\n        "properties": \n        {\n            "rhinosightingrep_Rhino": {\n                "type": "string",\n                "title": "Individual Rhino ID",\n                "enum": {{query___blackRhinos___values}},\n                "enumNames": {{query___blackRhinos___names}}\n            },\n            "rhinosightingrep_earnotchcount": {\n                "type":"number",\n                "title": "Ear notch count"\n            },\n            "rhinosightingrep_condition":{\n                "type": "string",\n                "title": "Condition",\n               "enum": {{enum___rhinosightingrep_condition___values}},\n               "enumNames": {{enum___rhinosightingrep_condition___names}}                   \n            },\n            "rhinosightingrep_activity": {\n                "type": "string",\n                "title": "Activity",\n               "enum": {{enum___rhinosightingrep_activity___values}},\n               "enumNames": {{enum___rhinosightingrep_activity___names}}            \n            }\n        }\n    },\n    "definition": [\n    {\n        "key":         "rhinosightingrep_Rhino",\n        "htmlClass": "col-lg-6"\n    }, \n    {\n        "key":         "rhinosightingrep_earnotchcount",\n        "htmlClass": "col-lg-6"\n    }, \n    {\n        "key":         "rhinosightingrep_condition",\n        "htmlClass": "col-lg-6"\n    }, \n    {\n        "key":         "rhinosightingrep_activity",\n        "htmlClass": "col-lg-6"\n    }\n    ]\n}"""

EVENT_SCHEMA_MISSING_BRACE_ON_VARIABLE = """{\n    "schema": {\n        "$schema": "http://json-schema.org/draft-04/schema#",\n        "title": "Rhino Sighting (rhino_sighting_rep)",\n      \n        "type": "object",\n\n        "properties": \n        {\n            "rhinosightingrep_Rhino": {\n                "type": "string",\n                "title": "Individual Rhino ID",\n                "enum": {{query___blackRhinos___values}}\n                "enumNames": {{query___blackRhinos___names}}\n            },\n            "rhinosightingrep_earnotchcount": {\n                "type":"number",\n                "title": "Ear notch count"\n            },\n            "rhinosightingrep_condition":{\n                "type": "string",\n                "title": "Condition",\n               "enum": {{enum___rhinosightingrep_condition___values}},\n               "enumNames": {{enum___rhinosightingrep_condition___names}}                   \n            },\n            "rhinosightingrep_activity": {\n                "type": "string",\n                "title": "Activity",\n               "enum": {{enum___rhinosightingrep_activity___values}},\n               "enumNames": {{enum___rhinosightingrep_activity___names}}            \n            }\n        }\n    },\n    "definition": [\n    {\n        "key":         "rhinosightingrep_Rhino",\n        "htmlClass": "col-lg-6"\n    }, \n    {\n        "key":         "rhinosightingrep_earnotchcount",\n        "htmlClass": "col-lg-6"\n    }, \n    {\n        "key":         "rhinosightingrep_condition",\n        "htmlClass": "col-lg-6"\n    }, \n    {\n        "key":         "rhinosightingrep_activity",\n        "htmlClass": "col-lg-6"\n    }\n    ]\n}"""

EVENT_SCHEMA_MISSING_COMMA_AFTER_VARIABLE = """{\n    "schema": {\n        "$schema": "http://json-schema.org/draft-04/schema#",\n        "title": "Rhino Sighting (rhino_sighting_rep)",\n      \n        "type": "object",\n\n        "properties": \n        {\n            "rhinosightingrep_Rhino": {\n                "type": "string",\n                "title": "Individual Rhino ID",\n                "enum": {{query___blackRhinos___values}}\n                "enumNames": {{query___blackRhinos___names}}\n            },\n            "rhinosightingrep_earnotchcount": {\n                "type":"number",\n                "title": "Ear notch count"\n            },\n            "rhinosightingrep_condition":{\n                "type": "string",\n                "title": "Condition",\n               "enum": {{enum___rhinosightingrep_condition___values}},\n               "enumNames": {{enum___rhinosightingrep_condition___names}}                   \n            },\n            "rhinosightingrep_activity": {\n                "type": "string",\n                "title": "Activity",\n               "enum": {{enum___rhinosightingrep_activity___values}},\n               "enumNames": {{enum___rhinosightingrep_activity___names}}            \n            }\n        }\n    },\n    "definition": [\n    {\n        "key":         "rhinosightingrep_Rhino",\n        "htmlClass": "col-lg-6"\n    }, \n    {\n        "key":         "rhinosightingrep_earnotchcount",\n        "htmlClass": "col-lg-6"\n    }, \n    {\n        "key":         "rhinosightingrep_condition",\n        "htmlClass": "col-lg-6"\n    }, \n    {\n        "key":         "rhinosightingrep_activity",\n        "htmlClass": "col-lg-6"\n    }\n    ]\n}"""

EVENT_SCHEMA_INCORRECT_TAG = """{\n    "schema": {\n        "$schema": "http://json-schema.org/draft-04/schema#",\n        "title": "Rhino Sighting (rhino_sighting_rep)",\n      \n        "type": "object",\n\n        "properties": \n        {\n            "rhinosightingrep_Rhino": {\n                "type": "string",\n                "title": "Individual Rhino ID",\n                "enum": {{query___blackRhinos___values}}\n                "enumNames": {{query_blackRhinos___names}}\n            },\n            "rhinosightingrep_earnotchcount": {\n                "type":"number",\n                "title": "Ear notch count"\n            },\n            "rhinosightingrep_condition":{\n                "type": "string",\n                "title": "Condition",\n               "enum": {{enum___rhinosightingrep_condition___values}},\n               "enumNames": {{enum___rhinosightingrep_condition___names}}                   \n            },\n            "rhinosightingrep_activity": {\n                "type": "string",\n                "title": "Activity",\n               "enum": {{enum___rhinosightingrep_activity___values}},\n               "enumNames": {{enum___rhinosightingrep_activity___names}}            \n            }\n        }\n    },\n    "definition": [\n    {\n        "key":         "rhinosightingrep_Rhino",\n        "htmlClass": "col-lg-6"\n    }, \n    {\n        "key":         "rhinosightingrep_earnotchcount",\n        "htmlClass": "col-lg-6"\n    }, \n    {\n        "key":         "rhinosightingrep_condition",\n        "htmlClass": "col-lg-6"\n    }, \n    {\n        "key":         "rhinosightingrep_activity",\n        "htmlClass": "col-lg-6"\n    }\n    ]\n}"""

EVENT_SCHEMA_EMPTY_PROPERTY = """{\n    "schema": {\n        "$schema": "http://json-schema.org/draft-04/schema#",\n        "title": "Rhino Sighting (rhino_sighting_rep)",\n      \n        "type": "object",\n\n        "properties": \n        {\n            "rhinosightingrep_Rhino": {\n            },\n            "rhinosightingrep_earnotchcount": {\n                "type":"number",\n                "title": "Ear notch count"\n            },\n            "rhinosightingrep_condition":{\n                "type": "string",\n                "title": "Condition",\n               "enum": {{enum___rhinosightingrep_condition___values}},\n               "enumNames": {{enum___rhinosightingrep_condition___names}}                   \n            },\n            "rhinosightingrep_activity": {\n                "type": "string",\n                "title": "Activity",\n               "enum": {{enum___rhinosightingrep_activity___values}},\n               "enumNames": {{enum___rhinosightingrep_activity___names}}            \n            }\n        }\n    },\n    "definition": [\n    {\n        "key":         "rhinosightingrep_Rhino",\n        "htmlClass": "col-lg-6"\n    }, \n    {\n        "key":         "rhinosightingrep_earnotchcount",\n        "htmlClass": "col-lg-6"\n    }, \n    {\n        "key":         "rhinosightingrep_condition",\n        "htmlClass": "col-lg-6"\n    }, \n    {\n        "key":         "rhinosightingrep_activity",\n        "htmlClass": "col-lg-6"\n    }\n    ]\n}"""

EVENT_SCHEMA_MISSING_DOLLAR_SIGN_SCHEMA = """{\n    "schema": {\n        "schema": "http://json-schema.org/draft-04/schema#",\n        "title": "Rhino Sighting (rhino_sighting_rep)",\n      \n        "type": "object",\n\n        "properties": \n        {\n            "rhinosightingrep_Rhino": {\n                "type": "string",\n                "title": "Individual Rhino ID",\n                "enum": {{query___blackRhinos___values}},\n                "enumNames": {{query___blackRhinos___names}}\n            },\n            "rhinosightingrep_earnotchcount": {\n                "type":"number",\n                "title": "Ear notch count"\n            },\n            "rhinosightingrep_condition":{\n                "type": "string",\n                "title": "Condition",\n               "enum": {{enum___rhinosightingrep_condition___values}},\n               "enumNames": {{enum___rhinosightingrep_condition___names}}                   \n            },\n            "rhinosightingrep_activity": {\n                "type": "string",\n                "title": "Activity",\n               "enum": {{enum___rhinosightingrep_activity___values}},\n               "enumNames": {{enum___rhinosightingrep_activity___names}}            \n            }\n        }\n    },\n    "definition": [\n    {\n        "key":         "rhinosightingrep_Rhino",\n        "htmlClass": "col-lg-6"\n    }, \n    {\n        "key":         "rhinosightingrep_earnotchcount",\n        "htmlClass": "col-lg-6"\n    }, \n    {\n        "key":         "rhinosightingrep_condition",\n        "htmlClass": "col-lg-6"\n    }, \n    {\n        "key":         "rhinosightingrep_activity",\n        "htmlClass": "col-lg-6"\n    }\n    ]\n}"""

EVENT_SCHEMA_WITH_MISSING_PROPERTY_IN_DEFINITION = """{
    "schema": {
        "$schema": "http://json-schema.org/draft-04/schema#",
        "title": "Rhino Sighting (rhino_sighting_rep)",

        "type": "object",

        "properties":
        {
            "rhinosightingrep_earnotchcount": {
                "type":"number",
                "title": "Ear notch count"
            },
            "rhinosightingrep_condition":{
                "type": "string",
                "title": "Condition",
               "enum": {{enum___rhinosightingrep_condition___values}},
               "enumNames": {{enum___rhinosightingrep_condition___names}}
            },
            "rhinosightingrep_activity": {
                "type": "string",
                "title": "Activity",
               "enum": {{enum___rhinosightingrep_activity___values}},
               "enumNames": {{enum___rhinosightingrep_activity___names}}
            }
        }
    },
    "definition": [
    {
        "key":         "rhinosightingrep_earnotchcount",
        "htmlClass": "col-lg-6"
    },
    {
        "key":         "rhinosightingrep_condition",
        "htmlClass": "col-lg-6"
    },
    {
        "key":         "rhinosightingrep_activity",
        "htmlClass": "col-lg-6"
    },
    {
         "key": "this_key_should_be_missing_from_schema",
         "htmlClass": "col-lg-6"
    ]
}"""


@skipIf(True, "Skipping tests because we turned off validation in EventTypeForm")
class TestEventTypeForm(TestCase):
    def test_schema_with_missing_comma_returns_error(self):
        form = EventTypeForm(data={"schema": EVENT_SCHEMA_MISSING_COMMA_AFTER_VARIABLE})
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["schema"], [SCHEMA_ERROR_JSON_DECODE_ERROR])

    def test_schema_with_malformed_enum_returns_error(self):
        form = EventTypeForm(data={"schema": EVENT_SCHEMA_MISSING_BRACE_ON_VARIABLE})
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["schema"], [SCHEMA_ERROR_JSON_DECODE_ERROR])

    def test_schema_with_missing_dollar_sign_schema(self):
        form = EventTypeForm(data={"schema": EVENT_SCHEMA_MISSING_DOLLAR_SIGN_SCHEMA})
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["schema"], [SCHEMA_ERROR_MISSING_DOLLAR_SIGN_SCHEMA])

    def test_correct_schema_form_is_valid(self):
        form = EventTypeForm(data={"schema": EVENT_SCHEMA})
        self.assertTrue(form.is_valid())

    def test_incorrect_event_render_tag_throws_error(self):
        form = EventTypeForm(data={"schema": EVENT_SCHEMA_INCORRECT_TAG})
        self.assertFalse(form.is_valid())
        self.assertTrue("query_blackRhinos___names" in str(form.errors["schema"]))

    def test_empty_property_throws_an_error(self):
        form = EventTypeForm(data={"schema": EVENT_SCHEMA_EMPTY_PROPERTY})
        self.assertFalse(form.is_valid())
        self.assertTrue("rhinosightingrep_Rhino" in str(form.errors["schema"]))

    def test_missing_properties_in_definition(self):
        form = EventTypeForm(data={"schema": EVENT_SCHEMA_WITH_MISSING_PROPERTY_IN_DEFINITION})
        self.assertFalse(form.is_valid())


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestAlertRuleFormGetInitialForField(TestCase):
    """A brand-new AlertRule admin "add" form must show an empty JSON object,
    not the literal string "null", for the conditions/schedule fields.

    AlertRuleForm has no Meta of its own (the admin binds it to AlertRule via
    modelform_factory at request time), so tests build the same bound form
    class explicitly.

    Constructing an AlertRule (directly, or implicitly via the unbound form)
    falls back to AlertRule.das_tenant's default (default_tenant_id), which
    reads the current tenant from thread-local context. Without a tenant set,
    that default hits DASTenantManagement.get_tenant_id() -- a cache/TMS
    lookup this unit test must not depend on. `das_tenant_monkeypatch` pins a
    tenant on the thread-local context so default_tenant_id() resolves from
    there instead (see das/utils/migrations/columns.py:default_tenant_id).

    See das/activity/forms.py:AlertRuleForm.get_initial_for_field.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.BoundAlertRuleForm = forms.modelform_factory(AlertRule, form=AlertRuleForm, fields="__all__")

    def test_add_form_renders_empty_dict_for_conditions_and_schedule(self):
        form = self.BoundAlertRuleForm()

        conditions_initial = form.get_initial_for_field(form.fields["conditions"], "conditions")
        schedule_initial = form.get_initial_for_field(form.fields["schedule"], "schedule")

        self.assertEqual(conditions_initial, "{}")
        self.assertEqual(schedule_initial, "{}")

    def test_existing_instance_still_renders_its_stored_dict(self):
        instance = AlertRule(conditions={"foo": "bar"}, schedule={"days": [1, 2, 3]})
        form = self.BoundAlertRuleForm(instance=instance)

        conditions_initial = form.get_initial_for_field(form.fields["conditions"], "conditions")
        schedule_initial = form.get_initial_for_field(form.fields["schedule"], "schedule")

        self.assertEqual(conditions_initial, json.dumps({"foo": "bar"}, indent=2))
        self.assertEqual(schedule_initial, json.dumps({"days": [1, 2, 3]}, indent=2))


class TestPrettyReadOnlyJSONWidgetMedia(TestCase):
    """Guard against Media asset paths that don't resolve to a real static file.

    A mis-pathed entry produces a /static/ URL that 404s (and, under
    ManifestStaticFilesStorage, never gets hashed) — this is what broke the
    EventType admin when "json_readonly.css" was referenced without its "css/"
    directory prefix.
    """

    def test_every_media_asset_resolves_to_a_static_file(self):
        media = PrettyReadOnlyJSONWidget.Media
        css_assets = itertools.chain.from_iterable(media.css.values())
        for asset in itertools.chain(css_assets, media.js):
            with self.subTest(asset=asset):
                self.assertIsNotNone(
                    finders.find(asset),
                    f"Media asset {asset!r} is not locatable by the staticfiles finders",
                )
