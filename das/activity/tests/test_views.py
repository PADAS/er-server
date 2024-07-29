from functools import reduce
from itertools import chain

import pytest

from django.contrib.gis.geos import MultiPoint, Point, Polygon
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from accounts.models.permissionset import PermissionSet
from activity.models import Event, EventGeometry, EventType
from analyzers.models import FeatureProximityAnalyzerConfig
from analyzers.proximity import FeatureProximityAnalyzer
from mapping.models import SpatialFeature
from observations.models import Subject, SubjectSubType
from utils.gis import get_polygon_info


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestEventsView:
    feature = {
        "type": "Feature",
        "properties": {},
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [-121.77246093750001, 47.96050238891509],
                    [-118.037109375, 32.879587173066305],
                    [-83.75976562499999, 30.826780904779774],
                    [-84.5947265625, 45.1510532655634],
                    [-95.5810546875, 48.719961222646276],
                    [-121.77246093750001, 47.96050238891509],
                ]
            ],
        },
    }
    feature_collection = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [-103.64158630371094, 20.67037186452816],
                            [-103.64398956298828, 20.652382371230658],
                            [-103.63197326660155, 20.653667405666592],
                            [-103.64158630371094, 20.67037186452816],
                        ]
                    ],
                },
            }
        ],
    }

    # Area = 18876, Perimeter = 551
    feature_with_known_dimensions = {
        "type": "Feature",
        "properties": {},
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [-103.3813151344657, 20.67669767171168],
                    [-103.38131647557019, 20.67563084151954],
                    [-103.3799860998988, 20.675623940505954],
                    [-103.37997503578663, 20.676691711787292],
                    [-103.3813151344657, 20.67669767171168],
                ]
            ],
        },
    }

    def test_create_an_event_with_a_feature_collection_as_geometry(
        self, event_type, superuser_client, memory_store_client_mock, tenant_response
    ):
        event_type.geometry_type = EventType.GeometryTypesChoices.POLYGON
        event_type.save()
        url = reverse("events")

        response = superuser_client.post(
            url,
            {
                "title": "Event number five",
                "event_type": event_type.value,
                "geometry": self.feature_collection,
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert Event.objects.all().count()
        assert EventGeometry.objects.all().count() == 1

    def test_create_an_event_with_a_feature_as_geometry(
        self, event_type, superuser_client, memory_store_client_mock, tenant_response
    ):
        event_type.geometry_type = EventType.GeometryTypesChoices.POLYGON
        event_type.save()
        url = reverse("events")

        response = superuser_client.post(
            url,
            {
                "title": "Event number five",
                "event_type": event_type.value,
                "geometry": self.feature,
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert Event.objects.all().count()
        assert EventGeometry.objects.all().count()
        assert "area" in response.data["geometry"]["features"][0]["properties"]

    def test_calculate_geometry_area_and_perimeter(
        self, event_type, superuser_client, memory_store_client_mock, tenant_response
    ):
        event_type.geometry_type = EventType.GeometryTypesChoices.POLYGON
        event_type.save()
        url = reverse("events")

        response = superuser_client.post(
            url,
            {
                "title": "Event number five",
                "event_type": event_type.value,
                "geometry": self.feature_with_known_dimensions,
            },
        )
        area = response.data["geometry"][0]["properties"]["area"]
        perimeter = response.data["geometry"][0]["properties"]["perimeter"]

        assert response.status_code == status.HTTP_201_CREATED
        assert int(area) == 16438
        assert int(perimeter) == 514


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestEventView:
    feature = {
        "type": "Feature",
        "properties": {"title": "This is a new title", "size": 10, "large": 20},
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [-130.166015625, 66.93006025862448],
                    [-125.771484375, 51.34433866059924],
                    [-85.869140625, 49.83798245308484],
                    [-92.10937499999999, 66.5482634621744],
                    [-130.166015625, 66.93006025862448],
                ]
            ],
        },
    }
    feature_collection = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"color": "green"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [-103.64158630371094, 20.67037186452816],
                            [-103.64398956298828, 20.652382371230658],
                            [-103.63197326660155, 20.653667405666592],
                            [-103.64158630371094, 20.67037186452816],
                        ]
                    ],
                },
            }
        ],
    }

    @pytest.mark.parametrize(
        "geometry, expected",
        (
            (feature, {"area": 3846072269393, "perimeter": 8185448}),
            (feature_collection, {"area": 1228789, "perimeter": 5370}),
        ),
    )
    def test_updated_geometry_of_event_that_contains_a_previous_geometry(
        self, geometry, expected, event_with_detail, superuser_client, memory_store_client_mock, tenant_response
    ):
        EventGeometry.objects.create(
            event=event_with_detail.event,
            geometry=Polygon(
                (
                    (-103.41898441314697, 20.638567565077864),
                    (-103.41387748718262, 20.63499318125139),
                    (-103.40585231781006, 20.646840535793658),
                    (-103.41898441314697, 20.638567565077864),
                )
            ),
            properties={"title": "This is a little title"},
        )

        url = reverse("event-view", args=[event_with_detail.event.pk])
        response = superuser_client.patch(url, {"geometry": geometry})

        area = response.data["geometry"][0]["properties"]["area"]
        perimeter = response.data["geometry"][0]["properties"]["perimeter"]

        assert response.status_code == status.HTTP_200_OK
        assert int(area) == expected["area"]
        assert int(perimeter) == expected["perimeter"]

    @pytest.mark.parametrize(
        "geometry, expected",
        (
            (feature, {"area": 3846072269393, "perimeter": 8185448}),
            (feature_collection, {"area": 1228789, "perimeter": 5370}),
        ),
    )
    def test_update_geometry_of_event_that_does_not_contains_a_geometry(
        self, geometry, expected, event_with_detail, superuser_client, memory_store_client_mock, tenant_response
    ):
        url = reverse("event-view", args=[event_with_detail.event.pk])
        response = superuser_client.patch(url, {"geometry": geometry})

        area = response.data["geometry"][0]["properties"]["area"]
        perimeter = response.data["geometry"][0]["properties"]["perimeter"]

        assert response.status_code == status.HTTP_200_OK
        assert int(area) == expected["area"]
        assert int(perimeter) == expected["perimeter"]
        assert EventGeometry.objects.all().count()

    def test_delete_event_geometry_of_event(
        self, event_geometry_with_polygon, superuser_client, memory_store_client_mock, tenant_response
    ):
        url = reverse("event-view", args=[event_geometry_with_polygon.event.pk])

        response = superuser_client.patch(url, {"geometry": None})

        assert response.status_code == status.HTTP_200_OK
        assert event_geometry_with_polygon.event.geometries.count() == 0

    def test_delete_event_geometry_of_event_without_geometry(
        self, event_with_detail, superuser_client, memory_store_client_mock, tenant_response
    ):
        url = reverse("event-view", args=[event_with_detail.event.pk])

        response = superuser_client.patch(url, {"geometry": None})

        assert response.status_code == status.HTTP_200_OK
        assert event_with_detail.event.geometries.count() == 0


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestEventGeometryView:
    def test_get_event_geometry_updates(
        self, event_geometry_with_polygon, superuser_client, memory_store_client_mock, tenant_response
    ):
        event = event_geometry_with_polygon.event

        url = reverse("event-geometries", args=[event.id])
        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1

    def test_get_event_geometry_updates_properties(
        self, event_geometry_with_polygon, superuser_client, memory_store_client_mock, tenant_response
    ):
        event_geometry_with_polygon.properties = {"key": "value"}
        event_geometry_with_polygon.save()
        event = event_geometry_with_polygon.event

        url = reverse("event-geometries", args=[event.id])
        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 2

    def test_get_event_geometry_update_without_revisions(
        self, event_with_detail, superuser_client, memory_store_client_mock, tenant_response
    ):
        url = reverse("event-geometries", args=[event_with_detail.event.id])
        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert not response.data

    def test_export_events_csv(
        self, event_geometry_with_polygon, superuser_client, memory_store_client_mock, tenant_response
    ):
        url = reverse("events-export")
        event_geometry_with_polygon.properties["area"] = get_polygon_info(event_geometry_with_polygon.geometry, "area")
        event_geometry_with_polygon.properties["perimeter"] = get_polygon_info(
            event_geometry_with_polygon.geometry, "length"
        )
        event_geometry_with_polygon.save()
        response = superuser_client.get(url)
        content = response.content.decode("utf-8")

        assert response.status_code == status.HTTP_200_OK
        assert "Area" in content
        assert "3215419796603.78" in content
        assert "Perimeter" in content
        assert "8791536.63" in content


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestEventsExportView:
    @pytest.fixture
    def subject_source_with_proximity_analyzer_configured(
        self,
        subject_source,
        spatial_feature_type,
        subject_group_without_permissions,
        spatial_feature_group_static,
    ):
        subject = subject_source.subject
        subject_source.source
        subject_group_without_permissions.subjects.add(subject)

        spatial_feature = SpatialFeature.objects.create(
            feature_type=spatial_feature_type,
            feature_geometry=MultiPoint(Point(-103, 20)),
        )
        spatial_feature_group_static.features.add(spatial_feature)
        FeatureProximityAnalyzerConfig.objects.create(
            name="Test Feature Proximity Analyzer",
            subject_group=subject.groups.first(),
            threshold_dist_meters=150.0,
            is_active=True,
            proximal_features=spatial_feature_group_static,
        )

        return subject_source

    def test_event_export_view_filters_by_user_permission(
        self,
        superuser_client,
        ops_user,
        client,
        subject_source_with_proximity_analyzer_configured,
        five_observations,
        memory_store_client_mock,
    ):
        url = reverse("events-export")
        subject = subject_source_with_proximity_analyzer_configured.subject
        source = subject_source_with_proximity_analyzer_configured.source
        can_export_data_permission_set = PermissionSet.objects.get(name="Can Export Data")
        ops_user.permission_sets.add(can_export_data_permission_set)
        client.force_login(ops_user)
        self._setup_observations(source, five_observations)
        self._analyze_subject(subject)

        superuser_response = superuser_client.get(url)
        superuser_report = self._get_response_content(superuser_response)
        user_response = client.get(url)
        user_report = self._get_response_content(user_response)

        assert superuser_response.status_code == status.HTTP_200_OK
        assert user_response.status_code == status.HTTP_200_OK
        assert len(superuser_report) == 2
        assert len(user_report) == 1

    def _setup_observations(self, source, observations):
        locations = Point(-103, 20.001155774646055), Point(-103, 20.001798483879462)
        now = timezone.now()
        for count, location, observation in zip((1, 2), locations, observations):
            recorded_at = now - timezone.timedelta(minutes=count * 5)
            observation.location = location
            observation.source = source
            observation.recorded_at = recorded_at
            observation.save()

    def _analyze_subject(self, subject):
        for analyzer in FeatureProximityAnalyzer.get_subject_analyzers(subject):
            analyzer.analyze()

    def _get_response_content(self, response):
        return [line.decode() for line in response.content.split(b"\r\n") if line]


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestTrackedBySchemaView:
    def test_get_patrols_tracked_by_without_permission_should_be_empty(self, user_client, patrol_configuration):
        url = reverse("patrol-segments-schema")

        response = user_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["properties"]["leader"]["enum"] == []

    def test_get_patrols_tracked_by_with_permission(self, user_client, patrol_configuration):
        subject_group = patrol_configuration.subject_groups.first()
        expected_subject_ids = set(self._get_subject_ids_by_subject_group(subject_group))
        permission_set = subject_group.permission_sets.first()
        user = user_client.user
        user_id = str(user.id)
        user.permission_sets.add(permission_set)
        subject = subject_group.subjects.first()
        subject_id = str(subject.id)
        subject.linked_user = user
        subject.save()
        url = reverse("patrol-segments-schema")

        response = user_client.get(url)
        leaders = response.data["properties"]["leader"]["enum"]
        leader_ids = {leader["id"] for leader in leaders}
        subject_data = [leader for leader in leaders if leader["id"] == subject_id][-1]

        assert response.status_code == status.HTTP_200_OK
        assert expected_subject_ids == leader_ids
        assert user_id == subject_data["user"]["id"]

    def test_get_patrols_tracked_by_without_permission_and_linked_subject(self, user_client, patrol_configuration):
        subject_group = patrol_configuration.subject_groups.first()
        user = user_client.user
        user_id = str(user.id)
        subject = subject_group.subjects.first()
        subject_id = str(subject.id)
        subject.linked_user = user
        subject.save()
        url = reverse("patrol-segments-schema")

        response = user_client.get(url)
        leader = response.data["properties"]["leader"]["enum"][0]

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["properties"]["leader"]["enum"]) == 1
        assert leader["id"] == subject_id
        assert leader["user"]["id"] == user_id

    def test_get_patrols_tracked_by_without_permission_and_linked_subject_not_in_patrol_configuration(
        self, user_client, patrol_configuration, subject
    ):
        user = user_client.user
        subject.linked_user = user
        subject.save()
        url = reverse("patrol-segments-schema")

        response = user_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["properties"]["leader"]["enum"] == []

    def test_get_patrols_tracked_by_as_superuser(self, superuser_client, patrol_configuration):
        expected_subject_ids = self._get_subject_ids_in_patrol_configuration(patrol_configuration)
        url = reverse("patrol-segments-schema")

        response = superuser_client.get(url)
        leaders = response.data["properties"]["leader"]["enum"]
        leader_ids = set((leader["id"] for leader in leaders))

        assert response.status_code == status.HTTP_200_OK
        assert len(expected_subject_ids) == len(leaders)
        assert expected_subject_ids == leader_ids

    def _get_subject_ids_in_patrol_configuration(self, patrol_config):
        ids_by_subject_group = map(self._get_subject_ids_by_subject_group, patrol_config.subject_groups.all())
        return set(reduce(chain, ids_by_subject_group, []))

    def _get_subject_ids_by_subject_group(self, subject_group):
        return map(str, subject_group.subjects.values_list("id", flat=True))

    def test_etag_is_same_multiple_request(self, superuser_client):
        url = reverse("patrol-segments-schema")

        first_response = superuser_client.get(url)
        second_response = superuser_client.get(url)

        assert first_response.status_code == status.HTTP_200_OK
        assert first_response.headers["ETag"]
        assert second_response.status_code == status.HTTP_200_OK
        assert second_response.headers["ETag"]

        first_etag = first_response.headers["ETag"]
        second_etag = second_response.headers["ETag"]

        assert first_etag == second_etag

    def test_etag_is_different_after_update(self, superuser_client, patrol_configuration):

        url = reverse("patrol-segments-schema")

        first_response = superuser_client.get(url)
        first_etag = first_response.headers["ETag"]

        subject = Subject.objects.first()

        subject.subject_subtype = SubjectSubType.objects.exclude(id=subject.subject_subtype.id).first()
        subject.save(update_fields=["subject_subtype"])

        second_response = superuser_client.get(url)
        second_etag = second_response.headers["ETag"]

        assert second_response.status_code == status.HTTP_200_OK
        assert second_etag != first_etag

    def test_etags_should_be_different_for_two_users(self, superuser_client, user_client, patrol_configuration):
        url = reverse("patrol-segments-schema")

        superuser_response = superuser_client.get(url)
        superuser_etag = superuser_response.headers["ETag"]

        user_response = user_client.get(url)
        user_etag = user_response.headers["ETag"]

        assert superuser_etag != user_etag

    def test_etag_should_change_for_one_user_keep_same_for_other(
        self, superuser_client, user_client, patrol_configuration
    ):
        url = reverse("patrol-segments-schema")

        superuser_response = superuser_client.get(url)
        superuser_etag = superuser_response.headers["ETag"]

        user_response = user_client.get(url)
        user_etag = user_response.headers["ETag"]

        # Update subject
        subject = Subject.objects.first()
        subject.subject_subtype = SubjectSubType.objects.exclude(id=subject.subject_subtype.id).first()
        subject.save(update_fields=["subject_subtype"])

        superuser_response_2 = superuser_client.get(url)
        superuser_etag_2 = superuser_response_2.headers["ETag"]

        user_response_2 = user_client.get(url)
        user_etag_2 = user_response_2.headers["ETag"]

        assert superuser_etag != user_etag
        assert superuser_etag_2 != user_etag_2
        assert superuser_etag != superuser_etag_2
        assert user_etag == user_etag_2
