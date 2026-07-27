import django.contrib.auth
from django.contrib.admin.sites import AdminSite
from django.contrib.gis.geos import Polygon
from django.contrib.messages.storage.cookie import CookieStorage
from django.http import QueryDict
from django.test import RequestFactory
from django.urls import reverse

from activity.admin import EventAdmin, EventTypeAdmin
from activity.forms import EventGeometryForm
from activity.models import Event, EventCategory, EventDetails, EventGeometry, EventType
from core.tests import BaseAPITest

User = django.contrib.auth.get_user_model()

EVENT_SCHEMA_MISSING_COMMA = (
    '\n{\n    "schema":\n        {\n            "$schema": '
    '"http://json-schema.org/draft-04/schema#",\n\n            "title": "EventType Test Data",\n\n'
    '            "type": "object",\n\n            "properties":\n'
    '                {\n                    "type_accident": {\n                        "type": "string",\n'
    '                        "title": "Type of accident"\n                    },\n'
    '                    "number_people_involved": {\n                        "type": "number",\n'
    '                        "title": "Number of people involved"\n                        "minimum": 0\n'
    '                    },\n                    "animals_involved": {\n                        "type": "string",\n'
    '                        "title": "Animals involved"\n                    },\n                    "hidden_field": {\n'
    '                        "type": "string",\n                        "title": "Hidden String"\n                    }\n'
    '                }\n        },\n    "definition": [\n        {\n            "key": "type_accident",\n'
    '            "htmlClass": "col-lg-6"\n        },\n        {\n            "key": "number_people_involved",\n'
    '            "htmlClass": "col-lg-6"\n        },\n        {\n            "key": "animals_involved",\n'
    '            "htmlClass": "col-lg-6"\n        }\n    ]\n}\n'
)

EVENT_SCHEMA_UNMATCHED_QUOTES = (
    '\n{\n    "schema":\n        {\n            "$schema": '
    '"http://json-schema.org/draft-04/schema#",\n\n            "title": "EventType Test Data",\n\n'
    '            "type": "object",\n\n            "properties":\n'
    '                {\n                    "type_accident": {\n                        "type": "string",\n'
    '                        "title": "Type of accident"\n                    },\n'
    '                    "number_people_involved": {\n                        "type": "number,\n'
    '                        "title": "Number of people involved",\n                        "minimum": 0\n'
    '                    },\n                    "animals_involved": {\n                        "type": "string",\n'
    '                        "title": "Animals involved"\n                    },\n                    "hidden_field": {\n'
    '                        "type": "string",\n                        "title": "Hidden String"\n                    }\n'
    '                }\n        },\n    "definition": [\n        {\n            "key": "type_accident",\n'
    '            "htmlClass": "col-lg-6"\n        },\n        {\n            "key": "number_people_involved",\n'
    '            "htmlClass": "col-lg-6"\n        },\n        {\n            "key": "animals_involved",\n'
    '            "htmlClass": "col-lg-6"\n        }\n    ]\n}\n'
)

EVENT_SCHEMA_MISSING_COLON = (
    '\n{\n    "schema": \n    {\n        "$schema": '
    '"http://json-schema.org/draft-04/schema#",\n\n        "title": "EventType Test Data",\n      \n'
    '        "type": "object",\n\n        "properties": \n'
    '        {\n        "type_accident": {\n            "type": "string",\n            "title": "Type of accident"\n'
    '        },\n        "number_people_involved": {\n            "type" "number",\n'
    '            "title": "Number of people involved",\n            "minimum":0\n        },\n'
    '        "animals_involved": {\n            "type": "string",\n            "title": "Animals involved"\n'
    '        },\n        "hidden_field": {\n            "type": "string",\n            "title": "Hidden String"\n'
    '        }\n    }\n  },\n  "definition": [\n    {\n        "key":     "type_accident",\n'
    '        "htmlClass": "col-lg-6"\n    }, \n    {\n        "key":     "number_people_involved",\n'
    '        "htmlClass": "col-lg-6"\n    }, \n    {\n        "key":     "animals_involved",\n'
    '        "htmlClass": "col-lg-6"\n    }\n  ]\n}\n'
)


class TestEventTypeAdmin(BaseAPITest):

    def setUp(self):
        super().setUp()
        user_const = dict(last_name="last", first_name="first")
        self.user = User.objects.create_user(
            "user", "user@test.com", "all_perms_user", is_superuser=True, is_staff=True, **user_const
        )
        self.no_perms_user = User.objects.create_user(
            "no_perms_user", "das_no_perms@vulcan.com", "noperms", **user_const
        )
        self.site = AdminSite()
        self.request = RequestFactory()
        self.admin = EventTypeAdmin(model=EventType, admin_site=self.site)
        EventCategory.objects.create(value="test", display="TEST", ordernum=1)

    def test_eventtype_schema_missing_comma(self):
        url = reverse("admin:activity_eventtype_add")
        event_category_id = EventCategory.objects.get(value="test")

        post_data = {
            "_save": "Save",
            "category": str(event_category_id.id),
            "csrfmiddlewaretoken": "gU5qAhbMAwXNON8HmGmahUKsqhLouY6x5X2bjHYbDV6emzBhDECwlxZlgNgKzUAa",
            "default_priority": "0",
            "default_state": "new",
            "display": "Event",
            "icon": "",
            "ordernum": "",
            "schema": EVENT_SCHEMA_MISSING_COMMA,
            "value": "test_example",
        }

        request = self.factory.post(url)
        self.force_authenticate(request, self.user)
        query_dict = QueryDict("", mutable=True)
        query_dict.update(post_data)

        request.POST = query_dict
        request.META["CSRF_COOKIE"] = "gU5qAhbMAwXNON8HmGmahUKsqhLouY6x5X2bjHYbDV6emzBhDECwlxZlgNgKzUAa"
        messages = CookieStorage(request)
        setattr(request, "_messages", messages)

        response = self.admin.add_view(request)

        self.assertEqual(response.status_code, 200)
        self.assertTrue("Expecting ',' delimiter: line 19 column 25" in messages._queued_messages[0].message)

    def test_eventtype_schema_unmatched_quotes(self):
        url = reverse("admin:activity_eventtype_add")
        event_category_id = EventCategory.objects.get(value="test")

        post_data = {
            "_save": "Save",
            "category": str(event_category_id.id),
            "csrfmiddlewaretoken": "gU5qAhbMAwXNON8HmGmahUKsqhLouY6x5X2bjHYbDV6emzBhDECwlxZlgNgKzUAa",
            "default_priority": "0",
            "default_state": "new",
            "display": "Event",
            "icon": "",
            "ordernum": "",
            "schema": EVENT_SCHEMA_UNMATCHED_QUOTES,
            "value": "test_example",
        }

        request = self.factory.post(url)
        self.force_authenticate(request, self.user)
        query_dict = QueryDict("", mutable=True)
        query_dict.update(post_data)

        request.POST = query_dict
        request.META["CSRF_COOKIE"] = "gU5qAhbMAwXNON8HmGmahUKsqhLouY6x5X2bjHYbDV6emzBhDECwlxZlgNgKzUAa"
        messages = CookieStorage(request)
        setattr(request, "_messages", messages)

        response = self.admin.add_view(request)

        self.assertEqual(response.status_code, 200)
        self.assertTrue("Invalid control character at: line 17 column 41" in messages._queued_messages[0].message)

    def test_eventtype_schema_missing_colon(self):
        url = reverse("admin:activity_eventtype_add")
        event_category_id = EventCategory.objects.get(value="test")

        post_data = {
            "_save": "Save",
            "category": str(event_category_id.id),
            "csrfmiddlewaretoken": "gU5qAhbMAwXNON8HmGmahUKsqhLouY6x5X2bjHYbDV6emzBhDECwlxZlgNgKzUAa",
            "default_priority": "0",
            "default_state": "new",
            "display": "Event",
            "icon": "",
            "ordernum": "",
            "schema": EVENT_SCHEMA_MISSING_COLON,
            "value": "test_example",
        }

        request = self.factory.post(url)
        self.force_authenticate(request, self.user)
        query_dict = QueryDict("", mutable=True)
        query_dict.update(post_data)

        request.POST = query_dict
        request.META["CSRF_COOKIE"] = "gU5qAhbMAwXNON8HmGmahUKsqhLouY6x5X2bjHYbDV6emzBhDECwlxZlgNgKzUAa"
        messages = CookieStorage(request)
        setattr(request, "_messages", messages)

        response = self.admin.add_view(request)

        self.assertEqual(response.status_code, 200)
        self.assertTrue("Expecting ':' delimiter: line 17 column 20" in messages._queued_messages[0].message)


class TestEventAdmin(BaseAPITest):

    def setUp(self):
        super().setUp()
        user_const = dict(last_name="last", first_name="first")
        self.user = User.objects.create_user(
            "user", "user@test.com", "all_perms_user", is_superuser=True, is_staff=True, **user_const
        )
        self.site = AdminSite()
        self.admin = EventAdmin(model=Event, admin_site=self.site)
        self.category = EventCategory.objects.create(value="test", display="TEST", ordernum=1)

        # Create event types with different geometry types
        self.point_event_type = EventType.objects.create(
            value="point_event",
            display="Point Event",
            category=self.category,
            geometry_type=EventType.GeometryTypesChoices.POINT,
        )
        self.polygon_event_type = EventType.objects.create(
            value="polygon_event",
            display="Polygon Event",
            category=self.category,
            geometry_type=EventType.GeometryTypesChoices.POLYGON,
        )

    def test_get_inlines_for_new_event(self):
        """Test that EventGeometryInline is included when creating a new event."""
        inlines = self.admin.get_inlines(request=None, obj=None)
        inline_classes = [inline.__name__ for inline in inlines]

        # Should include EventGeometryInline for new events
        self.assertIn("EventGeometryInline", inline_classes)
        self.assertIn("EventDetailsInline", inline_classes)

    def test_get_inlines_for_point_event(self):
        """Test that EventGeometryInline is NOT included for Point geometry events."""
        event = Event.objects.create(
            title="Test Point Event", event_type=self.point_event_type, created_by_user=self.user
        )

        inlines = self.admin.get_inlines(request=None, obj=event)
        inline_classes = [inline.__name__ for inline in inlines]

        # Should NOT include EventGeometryInline for Point events
        self.assertNotIn("EventGeometryInline", inline_classes)
        self.assertIn("EventDetailsInline", inline_classes)

    def test_get_inlines_for_polygon_event(self):
        """Test that EventGeometryInline IS included for Polygon geometry events."""
        event = Event.objects.create(
            title="Test Polygon Event", event_type=self.polygon_event_type, created_by_user=self.user
        )

        inlines = self.admin.get_inlines(request=None, obj=event)
        inline_classes = [inline.__name__ for inline in inlines]

        # Should include EventGeometryInline for Polygon events
        self.assertIn("EventGeometryInline", inline_classes)
        self.assertIn("EventDetailsInline", inline_classes)

    def test_get_inlines_for_event_without_event_type(self):
        """Test that EventGeometryInline is included when event has no event_type."""
        event = Event.objects.create(title="Test Event Without Type", created_by_user=self.user)

        inlines = self.admin.get_inlines(request=None, obj=event)
        inline_classes = [inline.__name__ for inline in inlines]

        # Should include EventGeometryInline when event_type is None
        self.assertIn("EventGeometryInline", inline_classes)
        self.assertIn("EventDetailsInline", inline_classes)


class TestEventDetailsVerboseNames:
    """The admin inline heading is derived from EventDetails' Meta verbose names."""

    def test_verbose_name_is_title_cased_event_details(self):
        assert str(EventDetails._meta.verbose_name) == "Event Details"

    def test_verbose_name_plural_matches_singular_to_avoid_pluralized_heading(self):
        assert str(EventDetails._meta.verbose_name_plural) == "Event Details"


class TestEventGeometryForm(BaseAPITest):

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.event_category = EventCategory.objects.create(value="test", display="Test Category")
        self.point_event_type = EventType.objects.create(
            value="point_test",
            display="Point Test",
            category=self.event_category,
            geometry_type=EventType.GeometryTypesChoices.POINT,
        )
        self.polygon_event_type = EventType.objects.create(
            value="polygon_test",
            display="Polygon Test",
            category=self.event_category,
            geometry_type=EventType.GeometryTypesChoices.POLYGON,
        )
        self.event = Event.objects.create(
            title="Test Event",
            event_type=self.polygon_event_type,
        )
        self.event_geometry = EventGeometry.objects.create(
            event=self.event,
            geometry=Polygon(((0, 0), (0, 1), (1, 1), (1, 0), (0, 0))),
        )

    def test_point_event_type_accepts_point_geometry(self):
        form = EventGeometryForm(data={"geometry": "POINT(0 0)"}, instance=EventGeometry(event=self.event))
        form.set_event_type(self.point_event_type)
        self.assertTrue(form.is_valid())

    def test_point_event_type_rejects_polygon_geometry(self):
        form = EventGeometryForm(
            data={"geometry": "POLYGON((0 0, 0 1, 1 1, 1 0, 0 0))"}, instance=EventGeometry(event=self.event)
        )
        form.set_event_type(self.point_event_type)
        self.assertFalse(form.is_valid())
        if form.errors and "geometry" in form.errors:
            self.assertIn("point geometry", str(form.errors["geometry"]))

    def test_polygon_event_type_accepts_polygon_geometry(self):
        form = EventGeometryForm(
            data={"geometry": "POLYGON((0 0, 0 1, 1 1, 1 0, 0 0))"}, instance=EventGeometry(event=self.event)
        )
        form.set_event_type(self.polygon_event_type)
        self.assertTrue(form.is_valid())

    def test_polygon_event_type_rejects_point_geometry(self):
        form = EventGeometryForm(data={"geometry": "POINT(0 0)"}, instance=EventGeometry(event=self.event))
        form.set_event_type(self.polygon_event_type)
        self.assertFalse(form.is_valid())
        if form.errors and "geometry" in form.errors:
            self.assertIn("polygon geometry", str(form.errors["geometry"]))

    def test_delete_event_geometry_works(self):
        """Test that the delete checkbox in EventGeometryInline works correctly."""
        from django.contrib.admin.sites import AdminSite

        from activity.admin import EventGeometryInline

        # Get the inline
        inline = EventGeometryInline(Event, AdminSite())

        # Create formset data for deletion
        formset_data = {
            "geometries-TOTAL_FORMS": "1",
            "geometries-INITIAL_FORMS": "1",
            "geometries-MIN_NUM_FORMS": "0",
            "geometries-MAX_NUM_FORMS": "1",
            "geometries-0-id": str(self.event_geometry.id),
            "geometries-0-DELETE": "on",  # This marks it for deletion
            "geometries-0-geometry": "POLYGON((0 0, 0 1, 1 1, 1 0, 0 0))",
            "geometries-0-event": str(self.event.id),
            "geometries-0-das_tenant": str(self.event_geometry.das_tenant.id),
        }

        request = RequestFactory()
        self.force_authenticate(request, self.user)
        # Get the formset
        formset = inline.get_formset(request=request, obj=self.event, can_delete=True)

        # Create the formset with data
        formset_instance = formset(data=formset_data, instance=self.event, files={})

        # Check that the formset is valid
        self.assertTrue(formset_instance.is_valid())

        # Check that the form is marked for deletion by checking the formset's behavior
        # When a form is marked for deletion in an inline formset, it should be excluded from save
        instances = formset_instance.save(commit=False)

        # If the form is marked for deletion, no instances should be returned
        self.assertEqual(len(instances), 0, "Form should be marked for deletion")

        # Check that the original instance still exists
        self.assertTrue(EventGeometry.objects.filter(id=self.event_geometry.id).exists())

        # Now actually delete it
        formset_instance.save()

        # Check that the instance was deleted
        self.assertFalse(EventGeometry.objects.filter(id=self.event_geometry.id).exists())
