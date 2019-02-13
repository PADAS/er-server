from datetime import datetime, timedelta
import pytz
import json
from django.test import TestCase

from django.core.management import call_command

from business_rules import export_rule_data, run_all

from activity.businessrules import EventActions, EventVariables, generate_global_event_variables, \
    Schedule

from typing import NamedTuple

from activity.models import EventType
from utils import schema_utils

class Event(NamedTuple):
    state: str
    priority: int = 0
    foo: str = ''


class BusinessRulesTestCase(TestCase):

    def setUp(self):
        super().setUp()
        call_command('loaddata', 'initial_eventdata')
        call_command('loaddata', 'event_data_model')
        call_command('loaddata', 'test_events_schema')


    def test_just_the_rules_engine_variables(self):

        from business_rules import actions, engine, fields, operators, variables, export_rule_data

        alert_actions = []

        class TestEventVariables(variables.BaseVariables):

            def __init__(self, event):
                self.event = event

            @variables.select_multiple_rule_variable(label='Priority', options=[{'name': '0', 'label': 'None'},
                                                                                {'name': '100', 'label': 'Green'}])
            def priority(self):
                return [str(self.event.priority), ]

            @variables.select_multiple_rule_variable(label='State', options=[{'name': 'new', 'label': 'New'},
                                                                             {'name': 'active', 'label': 'Active'},
                                                                             {'name': 'resolved', 'label': 'Resolved'}])
            def state(self):
                return [self.event.state, ]

            @variables.select_multiple_rule_variable(label='Foo', options=[
                {'name': 'bar', 'label': 'Bar'},
                {'name': 'baz', 'label': 'Baz'},
                {'name': 'bat', 'label': 'Bat'}
            ])
            def foo(self):
                return [self.event.foo, ]

        class TestEventActions(actions.BaseActions):

            def __init__(self, event):
                self.event = event

            @actions.rule_action(params={"recipient": fields.FIELD_TEXT, })
            def send_alert(self, recipient):
                print(f'Sending alert for event {self.event} to recipient {recipient}.')
                alert_actions.append(self.event)

        exported_rule_data = export_rule_data(TestEventVariables, EventActions)
        # print(json.dumps(exported_rule_data, indent=2))

        sample_rules = [

            {
                "conditions": {
                    "all": [
                        {
                            "name": "priority",
                            "operator": "shares_at_least_one_element_with",
                            "value": ['200', '100',],
                        },
                        {
                            "name": "state",
                            "operator": "shares_at_least_one_element_with",
                            "value": ['new', 'active',],
                        },
                        {
                            "name": "foo",
                            "operator": "is_contained_by",
                            "value": ['bar', 'baz',],
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

        for event in (Event('new', 200, 'bar'), Event('active', 0)):
            run_all(rule_list=sample_rules,
                    defined_variables=TestEventVariables(event),
                    defined_actions=TestEventActions(event),
                    stop_on_first_trigger=False)

        self.assertEqual(len(alert_actions), 1)

    def test_create_eventtype_variables_class(self):

        snare_et = EventType.objects.get(value='snare_rep')
        variables_class, applies_to = generate_global_event_variables([snare_et,])
        # exported_rule_data = export_rule_data(variables_class, EventActions)
        # print(json.dumps(exported_rule_data, indent=2))

        sample_rules = [
            {
                "conditions": {
                    "all": [
                        {
                            "name": "priority",
                            "operator": "shares_at_least_one_element_with",
                            "value": ['1', '100', '200',],
                        },
                        {
                            "name": "state",
                            "operator": "shares_at_least_one_element_with",
                            "value": ["active", ],
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

        for event in (Event('new', 0), Event('new', 200), Event('active', 0), Event('active', 200)):
            run_all(rule_list=sample_rules,
                    defined_variables=EventVariables(event),
                    defined_actions=EventActions(event),
                    stop_on_first_trigger=False)

    def test_generate_global_eventvariables(self):

        variables_class, _ = generate_global_event_variables(EventType.objects.all(), only_common_factors=True)

        exported_rule_data = export_rule_data(variables_class, EventActions)
        print(json.dumps(exported_rule_data, indent=2))

    def test_filtered_eventvariables(self):

        variables_class, _ = generate_global_event_variables(EventType.objects.filter(value__in=['sit_rep', 'fence_rep']))

        exported_rule_data = export_rule_data(variables_class, EventActions)
        print(json.dumps(exported_rule_data, indent=2))

    def test_schedule_mask(self):

        periods = {
            'monday': [('08:00', '12:00'), ('13:00', '18:30')]
        }

        schedule = Schedule(periods)
        d1 = datetime.now(tz=pytz.timezone('America/Los_Angeles'))

        # Find the most recent Monday.
        d1 = d1 - timedelta(days=d1.weekday())
        self.assertTrue(d1 in schedule)

        # Test a negative
        self.assertFalse(d1.replace(hour=12, minute=30) in schedule)

        # Test a value at the edge of a period
        self.assertTrue(d1.replace(hour=12, minute=0 ) in schedule)

        # Test a day without defined periods
        self.assertFalse(d1 + timedelta(days=1) in schedule)

