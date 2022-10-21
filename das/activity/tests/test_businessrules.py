import json
from datetime import datetime, timedelta
from unittest import mock
import logging

import jsonschema
import pytz
from business_rules import actions, fields, variables, export_rule_data
from business_rules import run_all
from django.contrib.auth.models import Permission
from django.core import mail
from django.core.management import call_command
from django.template.loader import get_template
from django.utils import timezone

from accounts.models import PermissionSet
from accounts.models import User
from activity.alerting.businessrules import EventActions, EventVariables, _generate_aggregate_event_variables_class, \
    render_event
from activity.alerting.service import evaluate_event_on_alertrules, \
    evaluate_event
from activity.alerts_views import AlertRuleListView, NotificationMethodListView, \
    NotificationMethodView, EventAlertConditionsListView
from activity.alerts import create_alerts_permissionset
from activity.models import EventType, Event, AlertRule, NotificationMethod, \
    EventCategory, EventDetails

from activity.serializers import EventSerializer, AlertRuleSerializer
from activity.tasks import send_alert_to_notificationmethod, \
    evaluate_alert_rules, evaluate_conditions_for_sending_alerts
from core.tests import BaseAPITest
from core.utils import NonHttpRequest
from core.utils import OneWeekSchedule
from observations.models import Subject, SubjectGroup, CommonName

logger = logging.getLogger(__name__)

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
        call_command('loaddata', 'initial_choices')
        call_command('loaddata', 'initial_common_name')

        self.alerts_perms_user = User.objects.create_user(
            username='alertsuser',
            password='asdfo9823sfiu23$',
            email='alertsuser@tempuri.org')
        self.alerts_permissionset = PermissionSet.objects.get(
            name='Alert Rule Permissions')
        self.alerts_perms_user.permission_sets.add(self.alerts_permissionset)
        self.power_user = User.objects.create_user(username='poweruser',
                                                   password='asdfo9823sfiu23$',
                                                   email='poweruser@tempuri.org')
        self.admin_user = User.objects.create_superuser(username="superuser",
                                                        password="adfsfds32423",
                                                        email="super@user.com")

        self.power_user_permissionset = PermissionSet.objects.create(
            name='power_set')
        for perm in power_user_permissions:
            self.power_user_permissionset.permissions.add(
                Permission.objects.get(codename=perm))
        self.power_user.permission_sets.add(self.power_user_permissionset)

        self.subjectgroup_test_perm = PermissionSet.objects.create(
            name='subject_view')
        self.subjectgroup_test_perm.permissions.add(Permission.objects.get_by_natural_key(
            'view_subjectgroup', 'observations', 'subjectgroup'
        ))

        self.subjectgroup_user = User.objects.create_user(
            username='subGrp',
            password='asdfo9823sfiu23$',
            email='subgrpr@tempuri.org')

        self.subjectgroup_user.permission_sets.add(self.subjectgroup_test_perm)
        self.subjectgroup_user.save()

        self.notification_method = {
            'contact': {
                'method': 'sms',
                'value': '+12062147021'
            },
            'title': 'Some notification method',
            'is_active': True
        }

    def create_notification_method(self):
        request = self.factory.post(
            self.api_base + '/activity/notificationmethods', self.notification_method)
        self.force_authenticate(request, self.power_user)
        return NotificationMethodListView.as_view()(request)

    def create_alert(self, user):
        # Create a notification method
        notification = self.create_notification_method()

        # Create a notification method
        alert_rule = {
            'notification_method_ids': [notification.data["id"], ],
            'reportTypes': ['carcass_rep', ],
            'schedule': {
                "periods": {
                    "monday": [("08:00", "12:00"), ("13:00", "17:30")],
                    "wednesday": [("08:00", "12:00"), ("13:00", "17:30")]
                }
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

        request = self.factory.post(
            self.api_base + '/activity/alerts', alert_rule)
        self.force_authenticate(request, user)
        return AlertRuleListView.as_view()(request)

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
                                                                             {'name': 'active',
                                                                                 'label': 'Active'},
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
        variables_class, applies_to = _generate_aggregate_event_variables_class([
                                                                                snare_et, ])
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

        variables_class, _ = _generate_aggregate_event_variables_class(
            EventType.objects.all(), only_common_factors=True)

        exported_rule_data = export_rule_data(variables_class, EventActions)
        # print(json.dumps(exported_rule_data, indent=2))

    @staticmethod
    def test_filtered_eventvariables():

        variables_class, _ = _generate_aggregate_event_variables_class(
            EventType.objects.filter(value__in=['sit_rep', 'fence_rep']))

        exported_rule_data = export_rule_data(variables_class, EventActions)
        # print(json.dumps(exported_rule_data, indent=2))

    def test_schedule_mask(self):
        # Don't use US timezone as the week of daylight savings time, this will break
        test_timezone = "GMT"
        schedule = {
            'periods': {
                'sunday': [['08:00', '12:00'], ['13:00', '18:30']]
            },
            'timezone': test_timezone
        }

        schedule = OneWeekSchedule(schedule)
        d1 = datetime.now(tz=pytz.timezone(test_timezone))

        # Find the most recent Monday.
        d1 = d1 - timedelta(days=d1.isoweekday())
        d1 = d1.replace(hour=17)
        logger.info(f'Testing {d1}')
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

        email_2 = 'user2@tempuri.org'

        # Create a notification method
        response = self.create_notification_method()

        self.assertEqual(response.status_code, 201)

        notification_method_id = response.data["id"]
        print(f'NotificationMethod.id: {notification_method_id}')

        self.assertEqual(response.data['contact']['value'], '+12062147021')

        request = self.factory.patch(f'{self.api_base}/activity/notificationmethod/{notification_method_id}',
                                     data={'contact': {
                                         'method': 'email', 'value': email_2}},
                                     )
        self.force_authenticate(request, self.power_user)
        response = NotificationMethodView.as_view()(request, id=notification_method_id)
        self.assertEqual(response.status_code, 200)

        self.assertEqual(response.data['contact']['value'], email_2)

    def test_create_an_alert_rule(self):
        response = self.create_alert(self.alerts_perms_user)
        self.assertEqual(response.status_code, 201)

    def test_create_an_alert_rule_with_no_permissions(self):
        response = self.create_alert(self.power_user)
        self.assertEqual(response.status_code, 403)

    def test_view_alert_rules_with_no_permissions(self):
        request = self.factory.get(self.api_base + '/activity/alerts/')
        self.force_authenticate(request, self.power_user)
        response = AlertRuleListView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def _create_a_period_from_datetime(self, dt=None, including_time=True):
        '''
        Given a datetime, create a OneWeekSchedule with periods that include (or exclude) it.
        :param dt: defaults to now (in the django app's timezone).
        :param including_time: whether the schedule should include the given time.
        :return: a 'periods' dict.
        '''
        dt = dt or timezone.localtime()

        day_key = ['1', 'monday', 'tuesday', 'wednesday', 'thursday',
                   'friday', 'saturday', 'sunday'][dt.isoweekday()]

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

        return {"periods": periods}

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
        notification_method_id = self.create_notification_method().data["id"]

        # Create an alert rule
        alert_rule_1 = dict(
            reportTypes=[my_test_event_type.value, ],
            notification_method_ids=[notification_method_id, ],
            conditions={"all": [{"name": "confiscationrep_itemsconfiscated", "value": ["bushmeat"],
                                 "operator": "shares_at_least_one_element_with"},
                                {"name": "confiscationrep_numberofitems", "value": 2, "operator": "greater_than_or_equal_to"}, ]},
            schedule=self._create_a_period_from_datetime(including_time=True)
        )
        alert_rules_list = []
        for ar in [alert_rule_1, ]:
            request = NonHttpRequest()
            request.user = self.power_user
            ser = AlertRuleSerializer(data=ar, context={'request': request})
            if not ser.is_valid():
                print(f'AlertRule is not valid. Errors are: {ser.errors}')
            else:
                rule = ser.create(ser.validated_data)
                rule = AlertRule.objects.get(id=rule.id)
                alert_rules_list.append(rule)

        self.assertEqual(len(AlertRule.objects.filter(
            event_types=event.event_type)), 1)

        action_list = evaluate_event_on_alertrules(alert_rules_list, event)
        # self.assertEqual(len(action_list), 1)
        #
        # print(action_list)

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
            # state='active',
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
        notification_method_id = self.create_notification_method().data["id"]

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
                        "value": "test event"
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

        self.assertEqual(len(AlertRule.objects.filter(
            event_types=event.event_type)), 2)

        action_list = evaluate_event_on_alertrules(alert_rules_list, event)
        self.assertEqual(len(action_list), 1)

        print(action_list)

    def test_rule_with_state_exclusion_including_updates(self):

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
        notification_method_id = self.create_notification_method().data["id"]

        # print(f'NotificationMethod.id: {notification_method_id}')

        # Create an alert rule
        alert_rule_1 = dict(
            reportTypes=[carcass_eventtype.value, ],
            notification_method_ids=[notification_method_id, ],
            conditions={
                "all": [
                    {
                        "name": "state",
                        "value": [
                            "active",
                            "resolved"
                        ],
                        "operator": "shares_no_elements_with"
                    }
                ]
            },
            schedule=self._create_a_period_from_datetime(including_time=True)
        )

        alert_rules_list = []
        for ar in [alert_rule_1, ]:
            request = NonHttpRequest()
            request.user = self.power_user
            ser = AlertRuleSerializer(data=ar, context={'request': request})
            if not ser.is_valid():
                print(f'AlertRule is not valid. Errors are: {ser.errors}')
            else:
                rule = ser.create(ser.validated_data)
                rule = AlertRule.objects.get(id=rule.id)
                alert_rules_list.append(rule)

        self.assertEqual(len(AlertRule.objects.filter(
            event_types=event.event_type)), 1)

        action_list = evaluate_event_on_alertrules(alert_rules_list, event)
        self.assertEqual(len(action_list), 1)

        # print(action_list)

        request = NonHttpRequest()
        request.user = self.power_user
        ser = EventSerializer(event, data={'title': 'This is a new title.'}, context={
                              'request': request}, partial=True)

        if not ser.is_valid():
            print(f'Event is not valid. Errors are: {ser.errors}')
        else:
            event = ser.update(event, ser.validated_data)
            event = Event.objects.get(id=event.id)

        # print(event.title)

        action_list = evaluate_event_on_alertrules(alert_rules_list, event)
        self.assertEqual(len(action_list), 0)

        # print(action_list)

    def test_a_arrest_report_against_a_defined_alert_rule(self):
        schema = """{
   "schema": 
   {
       "$schema": "http://json-schema.org/draft-04/schema#",
       "title": "Arrest Report (arrest_rep)",
     
       "type": "object",

       "properties": 
       {
            "arrestrep_fullname": {
                "type": "string",
                "title": "Line 1: Name of Arrestee"
            }, 
            "arrestrep_age": {
                "type": "number",
                "title": "Line 2: Age",
                "minimum": 0
            },             
            "arrestrep_dateofbirth": {
                "type": "string",
                "title": "Line 3: Date of Birth"
            },
            "arrestrep_villagename": {
                "type": "string",
                "title": "Line 4: Village Name",
                "enum": {{enum___villagename___values}},
                "enumNames": {{enum___villagename___names}}                  
            },
            "arrestrep_nationality": {
                "type": "string",
                "title": "Line 5: Nationality",
                "enum": {{enum___nationality___values}},
                "enumNames": {{enum___nationality___names}}              
            },
            "arrestrep_reasonforarrest": {
                "type": "string",
                "title": "Line 6: Reason for Arrest",
                "enum": {{enum___arrestrep_reasonforarrest___values}},
                "enumNames": {{enum___arrestrep_reasonforarrest___names}}                    
            },                
            "arrestrep_time": {
                "type": "string",
                "title": "Line 7: Time of Arrest"
            },                                    
            "arrestrep_location": {
                "type": "string",
                "title": "Line 8: Place of Arrest"
            }, 
            "arrestrep_area": {
                "type": "string",
                "title": "Line 9: Area",
                "enum": {{enum___arrestrep_area___values}},
                "enumNames": {{enum___arrestrep_area___names}}
            },      
            "arrestrep_asset": {
                "type": "string",
                "title": "Line 10: Asset"                 
           },                      
            "arrestrep_zapnumberofarrestingscout": {
                "type": "string",
                "title": "Line 11: Arresting Scout",
                "enum": {{query___blackRhinos___values}},
                "enumNames": {{query___blackRhinos___names}}                       
            },
            "arrestrep_nameofranger": {
                "type": "string",
                "title": "Line 12: Name of Ranger"
            },            
            "arrestrep_zapnumberoftawarep": {
                "type": "string",
                "title": "Line 13: TAWA Scout ID"
            },

            "arrestrep_irnumber": {
                "type": "string",
                "title": "Line 14: IR Number"
            },    
"ARCHIVED FIELDS BEGIN": {"title": "==========================================="},
"arrestrep_assetusedpicklist": {
    "title": "Line 10: Assets Used",
    "type": "object"
},              
 
"ARCHIVED FIELDS END": {"title": "==========================================="}
       }
   },
 "definition": [

   {
       "key": "arrestrep_fullname",
        "htmlClass": "col-lg-6"
    },       
    {
       "key": "arrestrep_age",
        "htmlClass": "col-lg-6"
    },       
    {
       "key": "arrestrep_dateofbirth",
        "htmlClass": "col-lg-6"
    },       
    {
       "key": "arrestrep_villagename",
        "htmlClass": "col-lg-6"
    },       
    {
       "key": "arrestrep_nationality",
        "htmlClass": "col-lg-6"
    },       
    {
       "key": "arrestrep_reasonforarrest",
        "htmlClass": "col-lg-6"
    },       
    {
       "key": "arrestrep_time",
       "fieldHtmlClass": "date-time-picker json-schema",
       "readonly": false,
       "htmlClass": "col-lg-6"
    },
    {
       "key": "arrestrep_location",
        "htmlClass": "col-lg-6"
    },
    {
       "key": "arrestrep_area",
       "htmlClass": "col-lg-6"
    },            
    {
       "key": "arrestrep_asset",
        "htmlClass": "col-lg-6"
    },      
    {
       "key": "arrestrep_zapnumberofarrestingscout",
        "htmlClass": "col-lg-6"
    }, 
    {
       "key": "arrestrep_nameofranger",
        "htmlClass": "col-lg-6"
    },       
    {
       "key": "arrestrep_zapnumberoftawarep",
        "htmlClass": "col-lg-6"
    },

    {
       "key": "arrestrep_irnumber",
        "htmlClass": "col-lg-6"
    }          
 ]
}"""
        subj = Subject.objects.create(
            name="Roni",
            common_name=CommonName.objects.get(value="black_rhino")
        )
        arrest_eventtype = EventType.objects.get(value='arrest_rep')
        arrest_eventtype.schema = schema
        arrest_eventtype.save()

        event_details = {
            "arrestrep_age": 20,
            "arrestrep_area": {"name": "IGGR", "value": "iggr"},
            "arrestrep_time": "2019-10-07T02:00:00.000Z",
            "arrestrep_fullname": "Y",
            "arrestrep_irnumber": "M",
            "arrestrep_location": "Wisero",
            "arrestrep_nationality": "tanzania", "arrestrep_villagename": "marakopo",
            "arrestrep_reasonforarrest": {"name": "Torch / Panga", "value": "torch"},
            "arrestrep_zapnumberofarrestingscout": str(subj.id)
        }

        event_data = dict(
            state='active',
            title='Test Event No. 1',
            event_time=datetime.now(tz=pytz.utc),
            provenance=Event.PC_STAFF,
            event_type=arrest_eventtype.value,
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
        notification_method_id = self.create_notification_method().data["id"]

        # print(f'NotificationMethod.id: {notification_method_id}')

        # Create an alert rule
        alert_rule_1 = dict(
            reportTypes=[arrest_eventtype.value, ],
            notification_method_ids=[notification_method_id, ],
            conditions={
                "all": [
                    {
                        "name": "arrestrep_area",
                        "value": [
                            "senapa",
                            "iggr",
                            "wma",
                            "grumetireserves"
                        ],
                        "operator": "shares_at_least_one_element_with"
                    },
                    # {
                    #     "name": "arrestrep_zapnumberofarrestingscout",
                    #     "value": [],
                    #     "operator": "shares_at_least_one_element_with"
                    # },
                    {
                        "name": "arrestrep_reasonforarrest",
                        "value": [
                            "bushmeat/trophypossession",
                            "elephantpoaching",
                            "firearmpoaching",
                            "illegalgrazing",
                            "snaring",
                            "dogpoaching",
                            "motorbikepoaching",
                            "footpoaching",
                            "torch",
                        ],
                        "operator": "shares_at_least_one_element_with"
                    },
                    # {
                    #     "name": "arrestrep_location",
                    #     "value": None,
                    #     "operator": "contains"
                    # },
                    # {
                    #     "name": "arrestrep_asset",
                    #     "value": None,
                    #     "operator": "contains"
                    # }
                ]
            },
            schedule=self._create_a_period_from_datetime(including_time=True)
        )
        alert_rules_list = []
        for ar in [alert_rule_1, ]:
            request = NonHttpRequest()
            request.user = self.power_user
            ser = AlertRuleSerializer(data=ar, context={'request': request})
            if not ser.is_valid():
                print(f'AlertRule is not valid. Errors are: {ser.errors}')
            else:
                rule = ser.create(ser.validated_data)
                rule = AlertRule.objects.get(id=rule.id)
                alert_rules_list.append(rule)

        self.assertEqual(len(AlertRule.objects.filter(
            event_types=event.event_type)), 1)

        action_list = evaluate_event_on_alertrules(alert_rules_list, event)
        self.assertEqual(len(action_list), 1)

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
        notification = self.create_notification_method()
        self.assertEqual(notification.status_code, 201)

        notification_method_id = notification.data["id"]

        # Create an alert rule
        alert_rule_1 = dict(
            reportTypes=[carcass_eventtype.value, ],
            notification_method_ids=[notification_method_id, ],

        )

        alert_rules_list = []
        for ar in [alert_rule_1, ]:
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
            raise ValueError(f'Event is not valid. Errors are: {ser.errors}')
        else:
            event = ser.create(ser.validated_data)
            event = Event.objects.get(id=event.id)

        print(
            f'Event Details: {event.event_details.latest("updated_at").data}')

        ed = event.event_details.latest('updated_at')
        ed.data['event_details']['carcassrep_sex'] = {
            'name': 'Female', 'value': 'female'}
        ed.save()

        event.state = 'resolved'
        event.save()
        # Create a notification method
        self.notification_method["contact"] = {
            'method': 'email',
            'value': 'chrisdo@vulcan.com'
        }

        notification_method_id = self.create_notification_method().data["id"]

        # Create an alert rule
        alert_rule_1 = dict(
            reportTypes=[carcass_eventtype.value, ],
            notification_method_ids=[notification_method_id, ],
        )

        alert_rules_list = []
        for ar in [alert_rule_1, ]:
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

    def test_event_alert_template(self):

        get_template('eventalert.html')

    def test_schedule_schema(self):
        valid_document_1 = {
            "schedule_type": "week",
            "periods": {
                "monday": [["00:00", "23:00"]],
                "tuesday": [["06:00", "11:00"], ["12:30", "18:30"]]
            }
        }

        try:
            assumed_valid = False
            jsonschema.validate(valid_document_1, OneWeekSchedule.json_schema)
            assumed_valid = True
        finally:
            self.assertTrue(
                assumed_valid, msg='Incorrectly assumed a schema is valid.')

        invalid_document_1 = {
            "periods": {
                "monday": [["00:00", "23:00"]],
                "wednesday": [["00:01", "11:00", "12:30"]],  # <-- invalid
                "thursday": [["01:01", "12:30"]]
            }
        }

        with self.assertRaises(jsonschema.ValidationError, msg="Expected error for invalid time-range tuple."):
            #jsonschema.validate(invalid_document_1, OneWeekSchedule.json_schema)
            schedule = OneWeekSchedule(invalid_document_1)

        invalid_document_2 = {
            "periods": {
                "monday": [["00:00", "23:00"]],
                "thurs": [["01:01", "12:30"]]  # <-- invalid
            }
        }

        with self.assertRaises(jsonschema.ValidationError, msg="Expected error for disallowed additional property."):
            jsonschema.validate(invalid_document_2,
                                OneWeekSchedule.json_schema)

        invalid_document_3 = {
            "periods": {
                "monday": [["00:00", "23:00"]],
                "friday": [["01:01", "12:30"]],
                "somerandomkey": {'something': 1}  # <-- invalid
            }
        }

        with self.assertRaises(jsonschema.ValidationError, msg="Expected error for disallowed additional property."):
            jsonschema.validate(invalid_document_3,
                                OneWeekSchedule.json_schema)

        invalid_document_4 = {
            "schedule_type": "month",
            "periods": {
                "monday": [["00:00", "23:00"]],
                "friday": [["01:01", "12:30"]]
            }
        }

        with self.assertRaises(jsonschema.ValidationError, msg="Expected error for invalid schedule_type."):
            jsonschema.validate(invalid_document_4,
                                OneWeekSchedule.json_schema)

    def test_notification_triggered_for_subject_group(self):
        NOTIFICATION_METHOD_EMAIL_ADDRESS = "phillip@email.com"
        notification_method = NotificationMethod.objects.create(title="test",
                                                                owner=self.admin_user,
                                                                method="email",
                                                                value=NOTIFICATION_METHOD_EMAIL_ADDRESS)
        notification_method.save()
        self.assertEqual(1, NotificationMethod.objects.count())

        subj = Subject.objects.create(
            name="test_subject",
            owner=self.admin_user,
        )

        subj_group = SubjectGroup.objects.create(name="subject_group")
        subj_group.subjects.set([subj])
        subj_group.permission_sets.set([self.subjectgroup_test_perm])
        subj_group.save()

        conditions = {
            "all": [
                {
                    "name": "subject_group",
                    "value": [
                        str(subj_group.id)
                    ],
                    "operator": "shares_at_least_one_element_with"
                }
            ]
        }

        immobility = EventType.objects.get(display='Immobility')

        TEST_ALERT_RULE_TITLE = "test_alert_rule"

        alert_rule = AlertRule.objects.create(
            owner=self.power_user, title=TEST_ALERT_RULE_TITLE)
        alert_rule.conditions = conditions
        alert_rule.notification_methods.set([notification_method, ])
        alert_rule.event_types.set([immobility, ])
        alert_rule.save()
        # 3. Create event
        TEST_EVENT_TITLE = "Test Subject Group Email"
        event_data = dict(
            state='active',
            title=TEST_EVENT_TITLE,
            event_time=datetime.now(tz=pytz.utc),
            provenance=Event.PC_STAFF,
            event_type=immobility.value,
            priority=Event.PRI_IMPORTANT,
            location=dict(longitude=37.5123, latitude=1.4590),
            event_details={},
            related_subjects=[{'id': subj.id}, ],
        )

        request = NonHttpRequest()
        request.user = self.power_user
        ser = EventSerializer(data=event_data, context={'request': request})

        if not ser.is_valid():
            self.fail(f'Event is not valid. Errors are: {ser.errors}')
        else:
            event = ser.create(ser.validated_data)
            event = Event.objects.get(id=event.id)

        action_list = evaluate_event(event)
        alert_rule_ids = [action['alert_rule_id'] for action in action_list]

        already_queued_nids = set()
        for alert_rule in AlertRule.objects.filter(id__in=alert_rule_ids).order_by('ordernum', 'title'):
            for notification_method in alert_rule.notification_methods.filter(is_active=True):

                if notification_method.id not in already_queued_nids:
                    kwargs = {
                        'alert_rule_id': str(alert_rule.id),
                        'event_id': str(event.id),
                        'notification_method_id': str(notification_method.id)
                    }

                    send_alert_to_notificationmethod(**kwargs)
                already_queued_nids.add(notification_method.id)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual([NOTIFICATION_METHOD_EMAIL_ADDRESS],
                         mail.outbox[0].to)
        self.assertIn(TEST_EVENT_TITLE, mail.outbox[0].subject)

    def test_notification_not_triggered_for_wrong_subject_group(self):
        NOTIFICATION_METHOD_EMAIL_ADDRESS = "phillip@email.com"
        notification_method = NotificationMethod.objects.create(title="test",
                                                                owner=self.admin_user,
                                                                method="email",
                                                                value=NOTIFICATION_METHOD_EMAIL_ADDRESS)
        self.assertEqual(1, NotificationMethod.objects.count())

        subj2 = Subject.objects.create(
            name="test_subject",
            owner=self.admin_user,
        )
        subj_group = SubjectGroup.objects.create(
            name="subject_group"
        )

        conditions = {
            "all": [
                {
                    "name": "subject_group",
                    "value": [
                        str(subj_group.id)
                    ],
                    "operator": "shares_at_least_one_element_with"
                }
            ]
        }

        immobility = EventType.objects.get(display='Immobility')

        TEST_ALERT_RULE_TITLE = "test_alert_rule"

        alert_rule = AlertRule.objects.create(
            owner=self.power_user, title=TEST_ALERT_RULE_TITLE)
        alert_rule.conditions = conditions
        alert_rule.notification_methods.set([notification_method, ])
        alert_rule.event_types.set([immobility, ])
        alert_rule.save()
        # 3. Create event
        TEST_EVENT_TITLE = "Test Subject Group Email"
        event_data = dict(
            state='active',
            title=TEST_EVENT_TITLE,
            event_time=datetime.now(tz=pytz.utc),
            provenance=Event.PC_STAFF,
            event_type=immobility.value,
            priority=Event.PRI_IMPORTANT,
            location=dict(longitude=37.5123, latitude=1.4590),
            event_details={},
            related_subjects=[{'id': subj2.id}, ],
        )

        request = NonHttpRequest()
        request.user = self.power_user
        ser = EventSerializer(data=event_data, context={'request': request})

        if not ser.is_valid():
            self.fail(f'Event is not valid. Errors are: {ser.errors}')
        else:
            event = ser.create(ser.validated_data)
            event = Event.objects.get(id=event.id)

        action_list = evaluate_event(event)
        alert_rule_ids = [action['alert_rule_id'] for action in action_list]

        already_queued_nids = set()
        for alert_rule in AlertRule.objects.filter(id__in=alert_rule_ids).order_by('ordernum', 'title'):
            for notification_method in alert_rule.notification_methods.filter(is_active=True):

                if notification_method.id not in already_queued_nids:
                    kwargs = {
                        'alert_rule_id': str(alert_rule.id),
                        'event_id': str(event.id),
                        'notification_method_id': str(notification_method.id)
                    }

                    send_alert_to_notificationmethod(**kwargs)
                already_queued_nids.add(notification_method.id)

        self.assertEqual(len(mail.outbox), 0)

    def test_subject_group_in_conditions(self):
        for grp in SubjectGroup.objects.all():
            grp.permission_sets.add(self.subjectgroup_test_perm)
            grp.save()
        request = self.factory.get(
            self.api_base + '/activity/alerts/conditions/')
        self.force_authenticate(request, self.subjectgroup_user)
        response = EventAlertConditionsListView.as_view()(request)

        for subject_group in SubjectGroup.objects.all():
            self.assertIn(str(subject_group.id), str(response.data))

    def test_user_without_view_subjectgroup_permissions_does_not_see_subject_groups(self):
        request = self.factory.get(
            self.api_base + '/activity/alerts/conditions/')
        self.force_authenticate(request, self.alerts_perms_user)
        response = EventAlertConditionsListView.as_view()(request)

        for subject_group in SubjectGroup.objects.all():
            self.assertNotIn(str(subject_group.id), str(response.data))

    def test_subject_group_list_updated_for_a_new_eventvariables_type(self):
        request = self.factory.get(
            self.api_base + '/activity/alerts/conditions/')
        self.force_authenticate(request, self.subjectgroup_user)
        response = EventAlertConditionsListView.as_view()(request)

        for subject_group in SubjectGroup.objects.all().filter(
                permission_sets__in=self.subjectgroup_user.get_all_permission_sets()).distinct('id'):
            self.assertIn(str(subject_group.id), str(response.data))

        test_subj = SubjectGroup.objects.create(
            name="new_created"
        )

        test_subj.permission_sets.add(self.subjectgroup_test_perm)
        test_subj.save()

        request = self.factory.get(
            self.api_base + '/activity/alerts/conditions/')
        self.force_authenticate(request, self.subjectgroup_user)
        response = EventAlertConditionsListView.as_view()(request)

        self.assertIn(str(test_subj.id), str(response.data))

    def test_evaluating_alert_rule_for_event_state_change_to_resolved(self):
        category = EventCategory.objects.get(value="security")

        notification_method = NotificationMethod. \
            objects.create(owner=self.power_user,
                           title="Email",
                           method='email',
                           value="test@test.com")

        event_type = EventType.objects.create(
            display="AlertTest",
            value="alert_test",
            schema=json.dumps({
                "schema": {
                    "$schema": "http://json-schema.org/draft-04/schema#",
                    "title": "EventType Test Data",
                    "type": "object",
                    "required": [
                        "details"
                    ],
                    "properties": {
                        "sex": {
                            "type": "string",
                            "title": "Sex of animal",
                            "enum": [
                                "Male",
                                "Female",
                                "Unknown"
                            ]
                        }
                    }
                },
                "definition": [
                    "sex"
                ]
            }),
            category=category
        )
        alert_rule = AlertRule.objects.create(
            owner=self.power_user,
            title="State is one of resolved",
            conditions={
                "all": [
                    {
                        "name": "state",
                        "value": [
                            "resolved"
                        ],
                        "operator": "shares_at_least_one_element_with"
                    }
                ]
            }
        )

        alert_rule.notification_methods.add(notification_method)
        alert_rule.event_types.add(event_type)

        event = Event.objects.create(title="test event",
                                     event_type=event_type,
                                     created_by_user=self.power_user)
        # event updated here
        event.state = 'resolved'
        event.save()

        action_list = evaluate_event(event)
        self.assertEqual(len(action_list), 1)

    @mock.patch("activity.tasks.evaluate_notifications")
    def test_evaluating_alerts_for_empty_conditions(self, mock_evaluate_notifications):
        notification_method = NotificationMethod.objects.create(title="test",
                                                                owner=self.admin_user,
                                                                method="email",
                                                                value="phillip@email.com")
        self.assertEqual(1, NotificationMethod.objects.count())

        subj2 = Subject.objects.create(
            name="test_subject",
            owner=self.admin_user,
        )

        conditions = {
        }

        immobility = EventType.objects.get(display='Immobility')

        alert_rule = AlertRule.objects.create(
            owner=self.power_user, title="test_alert_rule")
        alert_rule.conditions = conditions
        alert_rule.notification_methods.set([notification_method, ])
        alert_rule.event_types.set([immobility, ])
        alert_rule.save()
        # 3. Create event
        TEST_EVENT_TITLE = "Test Subject Group Email"
        event_data = dict(
            state='active',
            title=TEST_EVENT_TITLE,
            event_time=datetime.now(tz=pytz.utc),
            provenance=Event.PC_STAFF,
            event_type=immobility.value,
            priority=Event.PRI_IMPORTANT,
            location=dict(longitude=37.5123, latitude=1.4590),
            event_details={},
            related_subjects=[{'id': subj2.id}, ],
        )

        request = NonHttpRequest()
        request.user = self.power_user
        ser = EventSerializer(data=event_data, context={'request': request})

        if not ser.is_valid():
            self.fail(f'Event is not valid. Errors are: {ser.errors}')
        else:
            event = ser.create(ser.validated_data)
            event = Event.objects.get(id=event.id)

        action_list = evaluate_event(event)
        alert_rule_ids = [action['alert_rule_id'] for action in action_list]

        raised = False
        try:
            evaluate_conditions_for_sending_alerts(
                event, alert_rule, alert_rule_ids, True)
        except KeyError:
            raised = True
        self.assertFalse(raised)
        self.assertEqual(mock_evaluate_notifications.call_count, 1)
