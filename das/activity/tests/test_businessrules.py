from datetime import datetime, timedelta
import pytz

import jsonschema

from django.utils import timezone

from django.contrib.auth.models import Permission

from django.core.management import call_command

from core.tests import BaseAPITest
from core.utils import NonHttpRequest
from accounts.models import PermissionSet

from activity.serializers import EventSerializer, AlertRuleSerializer
from activity.alerts_views import AlertRuleListView, NotificationMethodListView, NotificationMethodView

from business_rules import run_all

from activity.alerting.businessrules import EventActions, EventVariables, _generate_aggregate_event_variables_class, render_event
from activity.alerting.service import evaluate_event_on_alertrules
from core.utils import OneWeekSchedule

from accounts.models import User

from activity.models import EventType, Event, AlertRule
from activity.tasks import send_alert_to_notificationmethod
from business_rules import actions, fields, variables, export_rule_data

power_user_permissions = [
    'security_read',
    'monitoring_create', 'monitoring_read', 'monitoring_update', 'monitoring_delete',
    'logistics_create', 'logistics_read', 'logistics_update', 'logistics_delete']


class BusinessRulesTestCase(BaseAPITest):

    def setUp(self):
        super().setUp()
        call_command('loaddata', 'initial_eventdata')
        call_command('loaddata', 'event_data_model')
        call_command('loaddata', 'test_events_schema')

        self.power_user = User.objects.create_user(username='poweruser',
                                                   password='asdfo9823sfiu23$',
                                                   email='poweruser@tempuri.org')

        self.power_user_permissionset = PermissionSet.objects.create(name='power_set')
        for perm in power_user_permissions:
            self.power_user_permissionset.permissions.add(
                Permission.objects.get(codename=perm))
        self.power_user.permission_sets.add(self.power_user_permissionset)

    def test_just_the_rules_engine_variables(self):

        alert_actions = []

        class TestEventVariables(variables.BaseVariables):

            def __init__(self, event):
                self.event = event

            @variables.select_multiple_rule_variable(label='Priority', options=[{'name': '0', 'label': 'None'},
                                                                                {'name': '100', 'label': 'Green'}])
            def priority(self):
                return [str(self.event.get('priority')), ]

            @variables.select_multiple_rule_variable(label='State', options=[{'name': 'new', 'label': 'New'},
                                                                             {'name': 'active', 'label': 'Active'},
                                                                             {'name': 'resolved', 'label': 'Resolved'}])
            def state(self):
                return [str(self.event.get('state')), ]

            @variables.select_multiple_rule_variable(label='Foo', options=[
                {'name': 'bar', 'label': 'Bar'},
                {'name': 'baz', 'label': 'Baz'},
                {'name': 'bat', 'label': 'Bat'}
            ])
            def foo(self):
                return [str(self.event.get('foo')), ]

        class TestEventActions(actions.BaseActions):

            def __init__(self, event):
                self.event = event

            @actions.rule_action(params={"recipient": fields.FIELD_TEXT, })
            def send_alert(self, recipient):
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
                            "value": ['200', '100', ],
                        },
                        {
                            "name": "state",
                            "operator": "shares_at_least_one_element_with",
                            "value": ['new', 'active', ],
                        },
                        {
                            "name": "foo",
                            "operator": "is_contained_by",
                            "value": ['bar', 'baz', ],
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

        for event in (dict(state='new', priority=200, foo='bar'), dict(state='active', priority=0)):
            run_all(rule_list=sample_rules,
                    defined_variables=TestEventVariables(event),
                    defined_actions=TestEventActions(event),
                    stop_on_first_trigger=False)

        self.assertEqual(len(alert_actions), 1)

    def test_create_eventtype_variables_class(self):

        snare_et = EventType.objects.get(value='snare_rep')
        variables_class, applies_to = _generate_aggregate_event_variables_class([snare_et, ])
        # exported_rule_data = export_rule_data(variables_class, EventActions)
        # print(json.dumps(exported_rule_data, indent=2))

        sample_rules = [
            {
                "conditions": {
                    "all": [
                        {
                            "name": "priority",
                            "operator": "shares_at_least_one_element_with",
                            "value": ['1', '100', '200', ],
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
                            "alert_rule_id": '1234',
                        }
                    }
                ]
            },
        ]


        for event in (
                dict(id=1, state='new', priority=0),
                dict(id=2, state='new', priority=200),
                dict(id=3, state='active', priority=0),
                dict(id=4, state='active', priority=200)
        ):
            action_list = []
            run_all(rule_list=sample_rules,
                    defined_variables=EventVariables(event),
                    defined_actions=EventActions(event, action_list),
                    stop_on_first_trigger=False)

    @staticmethod
    def test_generate_global_eventvariables():

        variables_class, _ = _generate_aggregate_event_variables_class(EventType.objects.all(), only_common_factors=True)

        exported_rule_data = export_rule_data(variables_class, EventActions)
        # print(json.dumps(exported_rule_data, indent=2))

    @staticmethod
    def test_filtered_eventvariables():

        variables_class, _ = _generate_aggregate_event_variables_class(
            EventType.objects.filter(value__in=['sit_rep', 'fence_rep']))

        exported_rule_data = export_rule_data(variables_class, EventActions)
        # print(json.dumps(exported_rule_data, indent=2))

    def test_schedule_mask(self):

        periods = {
            'sunday': [['08:00', '12:00'], ['13:00', '18:30']]
        }

        schedule = OneWeekSchedule(periods)
        d1 = datetime.now(tz=pytz.timezone('America/Los_Angeles'))

        # Find the most recent Monday.
        d1 = d1 - timedelta(days=d1.isoweekday())
        d1 = d1.replace(hour=17)
        print (f'Testing {d1}')
        self.assertTrue(d1 in schedule)
        d1 = d1.replace(hour=19)
        self.assertFalse(d1 in schedule)

        # Test a negative
        self.assertFalse(d1.replace(hour=12, minute=30) in schedule)

        # Test a value at the edge of a period
        self.assertTrue(d1.replace(hour=12, minute=0) in schedule)

        # Test a day without defined periods
        self.assertFalse(d1 + timedelta(days=1) in schedule)

    def test_event_serialization(self):
        pass

    def test_adding_and_updating_notification_method(self):

        email_1 = 'user1@tempuri.org'
        email_2 = 'user2@tempuri.org'

        # Create a notification method
        notification_method = {
            'contact': {
                'method': 'email',
                'value': email_1
            },
            'title':'Some notification method',
            'is_active': True
        }

        request = self.factory.post(self.api_base + '/activity/notificationmethods', notification_method)
        self.force_authenticate(request, self.power_user)
        response = NotificationMethodListView.as_view()(request)
        self.assertEqual(response.status_code, 201)

        notification_method_id = response.data["id"]
        print(f'NotificationMethod.id: {notification_method_id}')

        self.assertEqual(response.data['contact']['value'], email_1)

        request = self.factory.patch(f'{self.api_base}/activity/notificationmethod/{notification_method_id}',
                                     data={'contact': {'method': 'email', 'value': email_2}},
                                     )
        self.force_authenticate(request, self.power_user)
        response = NotificationMethodView.as_view()(request, id=notification_method_id)
        print(response.data)
        self.assertEqual(response.status_code, 200)

        self.assertEqual(response.data['contact']['value'], email_2)


    def test_create_an_alert_rule(self):

        # Create a notification method
        notification_method = {
            'contact': {
                'method': 'sms',
                'value': '+12062147021'
            },
            'title':'Some notification method',
            'is_active': True
        }

        request = self.factory.post(self.api_base + '/activity/notificationmethods', notification_method)
        self.force_authenticate(request, self.power_user)
        response = NotificationMethodListView.as_view()(request)
        self.assertEqual(response.status_code, 201)

        notification_method_id = response.data["id"]
        # print(f'NotificationMethod.id: {notification_method_id}')

        # Create an alert rule
        alert_rule = {
            'notification_method_ids': [notification_method_id, ],
            'reportTypes': ['carcass_rep', ],
            'schedule': {
                "monday": [("08:00", "12:00"), ("13:00", "17:30")],
                "wednesday": [("08:00", "12:00"), ("13:00", "17:30")]
            },
            'conditions': {
                "all": [
                    {
                        "name": "priority",
                        "operator": "shares_at_least_one_element_with",
                        "value": ['1', '100', '200', ],
                    },
                    {
                        "name": "state",
                        "operator": "shares_at_least_one_element_with",
                        "value": ["active", "new", ],
                    },
                    {
                        'name': 'carcassrep_species',
                        'operator': 'is_contained_by',
                        'value': ['redriverhog', ],
                    }
                ]
            },
            'display': 'Test alert rule for carcass report.',
        }

        request = self.factory.post(self.api_base + '/activity/alerts', alert_rule)
        self.force_authenticate(request, self.power_user)
        response = AlertRuleListView.as_view()(request)
        self.assertEqual(response.status_code, 201)
        alert_rule_id = response.data['id']
        # print(f'AlertRule.id: {alert_rule_id}')

        # Get the alert rule from the database
        request = NonHttpRequest()
        request.user = self.power_user
        ar = AlertRule.objects.get(id=alert_rule_id)
        ar_repr = AlertRuleSerializer(context={'request': request}).to_representation(ar)
        # print(json.dumps(ar_repr, indent=2, default=str))

    def _create_a_period_from_datetime(self, dt=None, including_time=True):
        '''
        Given a datetime, create a OneWeekSchedule with periods that include (or exclude) it.
        :param dt: defaults to now (in the django app's timezone).
        :param including_time: whether the schedule should include the given time.
        :return: a 'periods' dict.
        '''
        dt = dt or timezone.localtime()

        day_key = ['1', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'][dt.isoweekday()]

        if including_time:
            h1 = dt - timedelta(minutes=30)
            h2 = dt + timedelta(minutes=30)
        else:
            h1 = dt + timedelta(minutes=30)
            h2 = dt + timedelta(minutes=30)

        h1 = f'{h1.hour:02}:{h1.minute:02}'
        h2 = f'{h2.hour:02}:{h2.minute:02}'

        periods = {
            day_key: [[h1, h2]]
        }

        return periods


    def test_for_confiscation_rep_with_select_multiple(self):

        # Create a carcass event with some details
        my_test_event_type = EventType.objects.get(value='confiscation_rep')

        event_details = {
            'confiscationrep_itemsconfiscated': {'name': 'Bush Meat', 'value': 'bushmeat'},
            'confiscationrep_numberofitems': 3
        }

        event_data = dict(
            state='active',
            title='Test Event No. 1',
            event_time=datetime.now(tz=pytz.utc),
            provenance=Event.PC_STAFF,
            event_type=my_test_event_type.value,
            priority=Event.PRI_IMPORTANT,
            location=dict(longitude=37.5123, latitude=1.4590),
            event_details=event_details,
            # related_subjects=[{'id': self.subject.id}, ],
        )

        request = NonHttpRequest()
        request.user = self.power_user
        ser = EventSerializer(data=event_data, context={'request': request})

        if not ser.is_valid():
            print(f'Event is not valid. Errors are: {ser.errors}')
        else:
            event = ser.create(ser.validated_data)
            event = Event.objects.get(id=event.id)

        eventdata = render_event(event, self.power_user)
        # print(json.dumps(eventdata, indent=2, default=str))

        # Create a notification method
        notification_method = {
            'contact': {
                'method': 'sms',
                'value': '+12062147021'
            },
            'title':'Some notification method',
            'is_active': True
        }

        request = self.factory.post(self.api_base + '/activity/notificationmethods', notification_method)
        self.force_authenticate(request, self.power_user)
        response = NotificationMethodListView.as_view()(request)
        self.assertEqual(response.status_code, 201)

        notification_method_id = response.data["id"]
        # print(f'NotificationMethod.id: {notification_method_id}')

        # Create an alert rule
        alert_rule_1 = dict(
            reportTypes=[my_test_event_type.value, ],
            notification_method_ids=[notification_method_id, ],
            conditions={"all": [{"name": "confiscationrep_itemsconfiscated", "value": ["bushmeat"],
                                 "operator": "shares_at_least_one_element_with"},
                                {"name": "confiscationrep_numberofitems", "value": 2, "operator": "greater_than_or_equal_to"},]}
            ,
            schedule=self._create_a_period_from_datetime(including_time=True)
        )
        alert_rules_list = []
        for ar in [alert_rule_1,]:
            request = NonHttpRequest()
            request.user = self.power_user
            ser = AlertRuleSerializer(data=ar, context={'request': request})
            if not ser.is_valid():
                print(f'AlertRule is not valid. Errors are: {ser.errors}')
            else:
                rule = ser.create(ser.validated_data)
                rule = AlertRule.objects.get(id=rule.id)
                alert_rules_list.append(rule)

        self.assertEqual(len(AlertRule.objects.filter(event_types=event.event_type)), 1)

        action_list = evaluate_event_on_alertrules(alert_rules_list, event)
        self.assertEqual(len(action_list), 1)

        print(action_list)

    def test_a_real_event_against_a_defined_alert_rule(self):

        # Create a carcass event with some details
        carcass_eventtype = EventType.objects.get(value='carcass_rep')

        event_details = {
            'carcassrep_ageofanimal': {'name': 'Juvenile', 'value': 'juvenile'},
            'carcassrep_ageofcarcass': {'name': 'Fresh (within a week)', 'value': 'within_a_week'},
            'carcassrep_causeofdeath': {'name': 'Unnatural - Shot', 'value': 'unnaturalshot'},
            'carcassrep_sex': {'name': 'Male', 'value': 'male'},
            'carcassrep_species': {'name': 'Red River Hog', 'value': 'redriverhog'},
            'carcassrep_trophystatus': {'name': 'Intact', 'value': 'intact'},
        }

        event_data = dict(
            state='active',
            title='Test Event No. 1',
            event_time=datetime.now(tz=pytz.utc),
            provenance=Event.PC_STAFF,
            event_type=carcass_eventtype.value,
            priority=Event.PRI_IMPORTANT,
            location=dict(longitude=37.5123, latitude=1.4590),
            event_details=event_details,
            # related_subjects=[{'id': self.subject.id}, ],
        )

        request = NonHttpRequest()
        request.user = self.power_user
        ser = EventSerializer(data=event_data, context={'request': request})

        if not ser.is_valid():
            print(f'Event is not valid. Errors are: {ser.errors}')
        else:
            event = ser.create(ser.validated_data)
            event = Event.objects.get(id=event.id)

        eventdata = render_event(event, self.power_user)
        # print(json.dumps(eventdata, indent=2, default=str))

        # Create a notification method
        notification_method = {
            'contact': {
                'method': 'sms',
                'value': '+12062147021'
            },
            'title':'Some notification method',
            'is_active': True
        }

        request = self.factory.post(self.api_base + '/activity/notificationmethods', notification_method)
        self.force_authenticate(request, self.power_user)
        response = NotificationMethodListView.as_view()(request)
        self.assertEqual(response.status_code, 201)

        notification_method_id = response.data["id"]
        # print(f'NotificationMethod.id: {notification_method_id}')

        # Create an alert rule
        alert_rule_1 = dict(
            reportTypes=[carcass_eventtype.value, ],
            notification_method_ids=[notification_method_id, ],
            conditions={
                "all": [
                    {
                        "name": "title",
                        "operator": "contains",
                        "value": "Test Event No"
                    },
                    {
                        "name": "priority",
                        "operator": "shares_at_least_one_element_with",
                        "value": ['1', '100', '200', ],
                    },
                    {
                        "name": "state",
                        "operator": "shares_at_least_one_element_with",
                        "value": ["active", "new", ],
                    },
                    {
                        'name': 'carcassrep_species',
                        'operator': 'is_contained_by',
                        'value': ['redriverhog', ],
                    }
                ]
            },
            schedule=self._create_a_period_from_datetime(including_time=True)
        )
        alert_rule_2 = dict(
            reportTypes=[carcass_eventtype.value, ],
            notification_method_ids=[notification_method_id, ],
            conditions={
                "all": [
                    {
                        "name": "title",
                        "operator": "contains",
                        "value": "Elephant"
                    },
                ]
            },
            schedule=self._create_a_period_from_datetime(including_time=False)
        )

        alert_rules_list = []
        for ar in [alert_rule_1, alert_rule_2]:
            request = NonHttpRequest()
            request.user = self.power_user
            ser = AlertRuleSerializer(data=ar, context={'request': request})
            if not ser.is_valid():
                print(f'AlertRule is not valid. Errors are: {ser.errors}')
            else:
                rule = ser.create(ser.validated_data)
                rule = AlertRule.objects.get(id=rule.id)
                alert_rules_list.append(rule)

        self.assertEqual(len(AlertRule.objects.filter(event_types=event.event_type)), 2)

        action_list = evaluate_event_on_alertrules(alert_rules_list, event)
        self.assertEqual(len(action_list), 1)

        print(action_list)

    def test_alert_rule_with_empty_schedule(self):

        # Create a carcass event with some details
        carcass_eventtype = EventType.objects.get(value='carcass_rep')

        event_details = {
            'carcassrep_ageofanimal': {'name': 'Juvenile', 'value': 'juvenile'},
            'carcassrep_ageofcarcass': {'name': 'Fresh (within a week)', 'value': 'within_a_week'},
            'carcassrep_causeofdeath': {'name': 'Unnatural - Shot', 'value': 'unnaturalshot'},
            'carcassrep_sex': {'name': 'Male', 'value': 'male'},
            'carcassrep_species': {'name': 'Red River Hog', 'value': 'redriverhog'},
            'carcassrep_trophystatus': {'name': 'Intact', 'value': 'intact'},
        }

        event_data = dict(
            state='active',
            title='Test Event No. 1',
            event_time=datetime.now(tz=pytz.utc),
            provenance=Event.PC_STAFF,
            event_type=carcass_eventtype.value,
            priority=Event.PRI_IMPORTANT,
            location=dict(longitude=37.5123, latitude=1.4590),
            event_details=event_details,
            # related_subjects=[{'id': self.subject.id}, ],
        )

        request = NonHttpRequest()
        request.user = self.power_user
        ser = EventSerializer(data=event_data, context={'request': request})

        if not ser.is_valid():
            print(f'Event is not valid. Errors are: {ser.errors}')
        else:
            event = ser.create(ser.validated_data)
            event = Event.objects.get(id=event.id)

        # Create a notification method
        notification_method = {
            'contact': {
                'method': 'sms',
                'value': '+12062147021'
            },
            'title':'Some notification method',
            'is_active': True
        }

        request = self.factory.post(self.api_base + '/activity/notificationmethods', notification_method)
        self.force_authenticate(request, self.power_user)
        response = NotificationMethodListView.as_view()(request)
        self.assertEqual(response.status_code, 201)

        notification_method_id = response.data["id"]
        # print(f'NotificationMethod.id: {notification_method_id}')

        # Create an alert rule
        alert_rule_1 = dict(
            reportTypes=[carcass_eventtype.value, ],
            notification_method_ids=[notification_method_id, ],

        )

        alert_rules_list = []
        for ar in [alert_rule_1,]:
            request = NonHttpRequest()
            request.user = self.power_user
            ser = AlertRuleSerializer(data=ar, context={'request': request})
            if not ser.is_valid():
                print(f'AlertRule is not valid. Errors are: {ser.errors}')
            else:
                rule = ser.create(ser.validated_data)
                rule = AlertRule.objects.get(id=rule.id)
                alert_rules_list.append(rule)

        action_list = evaluate_event_on_alertrules(alert_rules_list, event)
        self.assertEqual(len(action_list), 1)

        print(action_list)

    def test_sending_a_message_for_an_event_alert(self):

        # Create a carcass event with some details
        carcass_eventtype = EventType.objects.get(value='carcass_rep')

        event_details = {
            'carcassrep_ageofanimal': {'name': 'Juvenile', 'value': 'juvenile'},
            'carcassrep_ageofcarcass': {'name': 'Fresh (within a week)', 'value': 'within_a_week'},
            'carcassrep_causeofdeath': {'name': 'Unnatural - Shot', 'value': 'unnaturalshot'},
            'carcassrep_sex': {'name': 'Male', 'value': 'male'},
            'carcassrep_species': {'name': 'Red River Hog', 'value': 'redriverhog'},
            'carcassrep_trophystatus': {'name': 'Intact', 'value': 'intact'},
        }

        event_data = dict(
            state='active',
            title='Test Event No. 1',
            event_time=datetime.now(tz=pytz.utc),
            provenance=Event.PC_STAFF,
            event_type=carcass_eventtype.value,
            priority=Event.PRI_IMPORTANT,
            location=dict(longitude=37.5123, latitude=1.4590),
            event_details=event_details,
            # related_subjects=[{'id': self.subject.id}, ],
        )

        request = NonHttpRequest()
        request.user = self.power_user
        ser = EventSerializer(data=event_data, context={'request': request})

        if not ser.is_valid():
            print(f'Event is not valid. Errors are: {ser.errors}')
        else:
            event = ser.create(ser.validated_data)
            event = Event.objects.get(id=event.id)

        # Create a notification method
        notification_method = {
            'contact': {
                'method': 'email',
                'value': 'chrisdo@vulcan.com'
            },
            'title':'Some notification method',
            'is_active': True
        }

        request = self.factory.post(self.api_base + '/activity/notificationmethods', notification_method)
        self.force_authenticate(request, self.power_user)
        response = NotificationMethodListView.as_view()(request)
        self.assertEqual(response.status_code, 201)

        notification_method_id = response.data["id"]
        # print(f'NotificationMethod.id: {notification_method_id}')

        # Create an alert rule
        alert_rule_1 = dict(
            reportTypes=[carcass_eventtype.value, ],
            notification_method_ids=[notification_method_id, ],
        )

        alert_rules_list = []
        for ar in [alert_rule_1,]:
            request = NonHttpRequest()
            request.user = self.power_user
            ser = AlertRuleSerializer(data=ar, context={'request': request})
            if not ser.is_valid():
                print(f'AlertRule is not valid. Errors are: {ser.errors}')
            else:
                rule = ser.create(ser.validated_data)
                rule = AlertRule.objects.get(id=rule.id)
                alert_rules_list.append(rule)


        send_alert_to_notificationmethod(alert_rule_id=str(rule.id), event_id=str(event.id),
                                         notification_method_id=str(notification_method_id))



    def test_schedule_schema(self):
        valid_document_1 = {
            "schedule_type": "week",
            "monday": [["00:00", "23:00"]],
            "tuesday": [["06:00", "11:00"], ["12:30", "18:30"]]
        }

        try:
            assumed_valid = False
            jsonschema.validate(valid_document_1, OneWeekSchedule.json_schema)
            assumed_valid = True
        finally:
            self.assertTrue(assumed_valid, msg='Incorrectly assumed a schema is valid.')

        invalid_document_1 = {
            "monday": [["00:00", "23:00"]],
            "wednesday": [["00:01", "11:00", "12:30"]], # <-- invalid
            "thurs": [["01:01", "12:30"]]
        }

        with self.assertRaises(jsonschema.ValidationError, msg="Expected error for invalid time-range tuple."):
            #jsonschema.validate(invalid_document_1, OneWeekSchedule.json_schema)
            schedule = OneWeekSchedule(invalid_document_1)

        invalid_document_2 = {
            "monday": [["00:00", "23:00"]],
            "thurs": [["01:01", "12:30"]] # <-- invalid
        }

        with self.assertRaises(jsonschema.ValidationError, msg="Expected error for disallowed additional property."):
            jsonschema.validate(invalid_document_2, OneWeekSchedule.json_schema)

        invalid_document_3 = {
            "monday": [["00:00", "23:00"]],
            "friday": [["01:01", "12:30"]],
            "somerandomkey": { 'something': 1} # <-- invalid
        }

        with self.assertRaises(jsonschema.ValidationError, msg="Expected error for disallowed additional property."):
            jsonschema.validate(invalid_document_3, OneWeekSchedule.json_schema)

        invalid_document_4 = {
            "schedule_type": "month",
            "monday": [["00:00", "23:00"]],
            "friday": [["01:01", "12:30"]]
        }

        with self.assertRaises(jsonschema.ValidationError, msg="Expected error for invalid schedule_type."):
            jsonschema.validate(invalid_document_4, OneWeekSchedule.json_schema)

