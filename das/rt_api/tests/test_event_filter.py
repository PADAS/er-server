import json

from activity.models import Event, EventType, EventCategory
from core.tests import BaseAPITest
from rt_api.tasks import get_filtered_events


class EventsFilterTestCase(BaseAPITest):
    def setUp(self):
        super().setUp()
        category = EventCategory.objects.create(value='test_category', display="test Category")
        self.event_type = EventType.objects.create(
            id="c9feb7e4-db81-4548-b8e3-29d4f14a3026",
            display="Test Type 1",
            value="typetest1",
            category=category
        )
        self.second_event_type = EventType.objects.create(
            display="Test Type 2",
            value="typetest2",
            category=category
        )
        self.event = Event.objects.create(
            title="test event",
            event_type=self.event_type,
            created_by_user=self.app_user)

        # sample angular filter payload
        self.test_filter = """{"event_type":["c9feb7e4-db81-4548-b8e3-29d4f14a3026"]}"""

    def test_event_filter_with_full_filter_params(self):

        # sample react filter payload
        filter = """
        {
            "include_notes":true,
            "include_related_events":true,
            "state":["active","new"],
            "filter":{
                "date_range":
                    {
                        "lower":"2020-04-06T21:00:00.000Z","upper":null
                    },
                "event_type":[null,"c9feb7e4-db81-4548-b8e3-29d4f14a3026"],
                "event_category":[],
                "text":"",
                "duration":null,
                "priority":[],
                "reported_by":[]
            }
        }
        """
        queryset = Event.objects.filter(id=self.event.id)
        events = get_filtered_events(json.loads(filter), queryset)
        self.assertTrue(self.event in events)

        # Create report then resolve event
        self.event.state = "resolved"
        self.event.save()

        # state is added and applied to filter
        events = get_filtered_events(json.loads(filter), queryset)
        self.assertFalse(self.event in events)

    def test_event_filter_with_selective_filter_params(self):

        # using sample angular filter payload
        queryset = Event.objects.filter(id=self.event.id)
        events = get_filtered_events(json.loads(self.test_filter), queryset)
        self.assertTrue(self.event in events)

    def test_event_filter_on_a_non_matching_event(self):

        # New event not a member of the saved filter
        new_event = Event.objects.create(
            title="new test event",
            event_type=self.second_event_type,
            created_by_user=self.app_user)
        queryset = Event.objects.filter(id=new_event.id)
        events = get_filtered_events(json.loads(self.test_filter), queryset)
        self.assertFalse(self.event in events)
