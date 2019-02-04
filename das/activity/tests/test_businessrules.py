import json
from django.test import TestCase

from django.core.management import call_command

from business_rules import export_rule_data, run_all

from activity.businessrules import EventActions, EventVariables, generate_eventvariables_class, \
    generate_global_event_variables

from typing import NamedTuple

from activity.models import EventType
from utils import schema_utils

class Event(NamedTuple):
    state: str
    priority: int = 0


# export_rule_data()

class BusinessRulesTestCase(TestCase):

    def setUp(self):
        super().setUp()
        call_command('loaddata', 'initial_eventdata')
        call_command('loaddata', 'event_data_model')
        call_command('loaddata', 'test_events_schema')

    # def test_export_rules(self):
    #
    #     exported_rule_data = export_rule_data(EventVariables, EventActions)
    #     print(json.dumps(exported_rule_data, indent=2))
    #
    #     for event in (Event('new', 0), Event('new', 200), Event('active', 0), Event('active', 200)):
    #         run_all(rule_list=sample_rules,
    #                 defined_variables=EventVariables(event),
    #                 defined_actions=EventActions(event),
    #                 stop_on_first_trigger=False)
    #

    def test_create_eventtype_variables_class(self):

        snare_et = EventType.objects.get(value='snare_rep')

        variables_class = generate_eventvariables_class(snare_et)
        print(variables_class)

        exported_rule_data = export_rule_data(variables_class, EventActions)
        print(json.dumps(exported_rule_data, indent=2))

        for event in (Event('new', 0), Event('new', 200), Event('active', 0), Event('active', 200)):
            run_all(rule_list=sample_rules,
                    defined_variables=EventVariables(event),
                    defined_actions=EventActions(event),
                    stop_on_first_trigger=False)

    def test_generate_global_eventvariables(self):

        variables_class = generate_global_event_variables(EventType.objects.all())

        exported_rule_data = export_rule_data(variables_class, EventActions)
        print(json.dumps(exported_rule_data, indent=2))


sample_rules = [

    {
        "conditions": {
            "any": [
            {
                "name": "priority",
                "operator": "greater_than",
                "value": 0,
            },
            {
                "name": "state",
                "operator": "equal_to",
                "value": "active",
            }
        ]
        },

        "actions": [
            {
                "name": "send_alert",
                "params": {
                    "recipient": "somepeople",
                }
            }
        ]
    },
]
