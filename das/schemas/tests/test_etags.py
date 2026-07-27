import pytest

from django.contrib.gis.geos import Point

from choices.models import Choice
from factories import (
    EventTypeFactory,
    SourceFactory,
    SpatialFeatureFactory,
    SubjectFactory,
    UserFactory,
)
from schemas.etags import get_dynamic_schema_sources_version


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestGetDynamicSchemaSourcesVersion:
    def test_stable_when_nothing_changes(self):
        SubjectFactory.create()

        version = get_dynamic_schema_sources_version()

        assert version == get_dynamic_schema_sources_version()

    def test_changes_when_an_event_choice_is_created(self):
        version_before = get_dynamic_schema_sources_version()

        Choice.objects.create(model=Choice.EVENT_MODEL, field="species", value="lion", display="Lion")

        assert get_dynamic_schema_sources_version() != version_before

    def test_changes_when_a_subject_is_created(self):
        version_before = get_dynamic_schema_sources_version()

        SubjectFactory.create()

        assert get_dynamic_schema_sources_version() != version_before

    def test_changes_when_a_subject_is_updated(self):
        subject = SubjectFactory.create()
        version_before = get_dynamic_schema_sources_version()

        subject.name = "Renamed Subject"
        subject.save()

        assert get_dynamic_schema_sources_version() != version_before

    def test_changes_when_a_subject_is_bulk_deactivated(self):
        """A bulk `.update(is_active=...)` bypasses auto_now, so the active-count
        component - not `updated_at` - must be what changes here."""
        subject = SubjectFactory.create()
        version_before = get_dynamic_schema_sources_version()

        type(subject).objects.filter(id=subject.id).update(is_active=False)

        assert get_dynamic_schema_sources_version() != version_before

    def test_changes_when_a_source_is_created(self):
        version_before = get_dynamic_schema_sources_version()

        SourceFactory.create()

        assert get_dynamic_schema_sources_version() != version_before

    def test_changes_when_a_source_is_updated(self):
        source = SourceFactory.create()
        version_before = get_dynamic_schema_sources_version()

        source.manufacturer_id = "renamed-manufacturer"
        source.save()

        assert get_dynamic_schema_sources_version() != version_before

    def test_changes_when_a_spatial_feature_is_created(self):
        version_before = get_dynamic_schema_sources_version()

        SpatialFeatureFactory.create(feature_geometry=Point(-122.1, 47.5))

        assert get_dynamic_schema_sources_version() != version_before

    def test_changes_when_a_spatial_feature_is_updated(self):
        spatial_feature = SpatialFeatureFactory.create(feature_geometry=Point(-122.1, 47.5))
        version_before = get_dynamic_schema_sources_version()

        spatial_feature.name = "Renamed Feature"
        spatial_feature.save()

        assert get_dynamic_schema_sources_version() != version_before

    def test_changes_when_an_event_type_is_created(self):
        version_before = get_dynamic_schema_sources_version()

        EventTypeFactory.create()

        assert get_dynamic_schema_sources_version() != version_before

    def test_changes_when_an_event_type_is_bulk_deactivated(self):
        event_type = EventTypeFactory.create()
        version_before = get_dynamic_schema_sources_version()

        type(event_type).objects.filter(id=event_type.id).update(is_active=False)

        assert get_dynamic_schema_sources_version() != version_before

    def test_changes_when_a_user_is_created(self):
        version_before = get_dynamic_schema_sources_version()

        UserFactory.create()

        assert get_dynamic_schema_sources_version() != version_before

    def test_changes_when_a_user_is_deactivated(self):
        user = UserFactory.create()
        version_before = get_dynamic_schema_sources_version()

        user.is_active = False
        user.save()

        assert get_dynamic_schema_sources_version() != version_before

    def test_unaffected_by_renaming_an_existing_active_user(self):
        """Documented gap: User has no `updated_at`, so an edit that doesn't touch
        `is_active` (e.g. a display-name change) isn't reflected in the token."""
        user = UserFactory.create()
        version_before = get_dynamic_schema_sources_version()

        user.first_name = "Renamed"
        user.save()

        assert get_dynamic_schema_sources_version() == version_before
