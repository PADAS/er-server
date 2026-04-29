import pytest

from django.contrib.auth import get_user_model
from django.urls import reverse

from choices.models import Choice
from factories import (
    EventCategoryFactory,
    EventTypeFactory,
    SourceFactory,
    SubjectFactory,
)
from observations.models import SubjectGroup


@pytest.mark.django_db
@pytest.mark.parametrize("view", ["users", "sources", "subjects", "choices", "spatial_features", "event_types"])
def test_get_dynamic_schemas(superuser_client, view):
    url = reverse(f"schemas:{view}")
    response = superuser_client.get(url)

    data = response.json()

    assert response.status_code == 200
    assert data["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    for item in data["oneOf"]:
        assert item["const"]
        assert item["title"]


@pytest.mark.django_db
def test_get_choices_dynamic_schemas(superuser_client):
    url = reverse("schemas:choices")
    response = superuser_client.get(url)

    choices = list(Choice.objects.all())
    choice_triples = {(str(c.value), c.display, c.field) for c in choices}

    data = response.json()

    assert response.status_code == 200
    assert data["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    for item in data["oneOf"]:
        triple = (str(item["const"]), item["title"], item["description"])
        assert triple in choice_triples, f"schema item {triple!r} does not match any Choice row"


@pytest.mark.django_db
def test_users_schema_includes_username_as_description(superuser_client):
    url = reverse("schemas:users")
    response = superuser_client.get(url)
    assert response.status_code == 200
    data = response.json()
    User = get_user_model()
    ids = [item["const"] for item in data["oneOf"]]
    id_to_username = {
        str(pk): username for pk, username in User.objects.filter(pk__in=ids).values_list("pk", "username")
    }
    for item in data["oneOf"]:
        assert item["description"] == id_to_username[str(item["const"])]


@pytest.mark.django_db
def test_choices_dynamic_schema_accessible_without_choice_permissions(user_client, five_choices):
    """Test that ChoicesDynamicSchemaView is accessible to users without choice permissions."""

    # Attempt to access the choices dynamic schema
    url = reverse("schemas:choices")
    response = user_client.get(url)

    # Should succeed even without choice-specific permissions
    assert response.status_code == 200

    data = response.json()
    assert data["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert "oneOf" in data
    assert len(data["oneOf"]) >= len(five_choices)

    for item in data["oneOf"]:
        assert "const" in item
        assert "title" in item
        assert "description" in item

    # Every fixture choice must appear in the schema; match on (value, display, field) so values are not ambiguous.
    items_by_triple = {(str(i["const"]), i["title"], i["description"]) for i in data["oneOf"]}
    for choice in five_choices:
        triple = (str(choice.value), choice.display, choice.field)
        assert triple in items_by_triple, f"expected schema item for fixture choice {triple!r}"


@pytest.mark.django_db
def test_get_dynamic_schema_choices_filtered(superuser_client):
    Choice.objects.filter(id=Choice.objects.first().id).update(field="firerep_status")
    Choice.objects.filter(id=Choice.objects.last().id).update(field="carcassrep_ageofcarcass")

    url = reverse("schemas:choices")
    response = superuser_client.get(f"{url}?field=firerep_status,carcassrep_ageofcarcass")

    not_in_filter_choices = [
        str(choice.value)
        for choice in Choice.objects.exclude(field__in=["firerep_status", "carcassrep_ageofcarcass"]).all()
    ]
    filtered_choices = [
        str(choice.value)
        for choice in Choice.objects.filter(field__in=["firerep_status", "carcassrep_ageofcarcass"]).all()
    ]

    assert response.status_code == 200
    for item in response.json()["oneOf"]:
        assert item["const"] in filtered_choices
        assert item["const"] not in not_in_filter_choices
        _ = Choice.objects.get(value=item["const"], field=item["description"])


@pytest.mark.django_db
def test_choices_display_as_title(superuser_client):
    url = reverse("schemas:choices")
    response = superuser_client.get(f"{url}?s_description=display")

    data = response.json()

    assert response.status_code == 200
    for item in data["oneOf"]:
        assert item["description"] == item["title"]


@pytest.mark.django_db
def test_dynamic_subjects_filtered_by_subtypes(superuser_client):
    two_subjects = SubjectFactory.create_batch(2)
    last_subject = SubjectFactory.create()

    sgrp1 = SubjectGroup.objects.create(name="Subject Group 1")
    sgrp2 = SubjectGroup.objects.create(name="Subject Group 2")
    sgrp1.subjects.add(two_subjects[0])
    sgrp2.subjects.add(last_subject)

    sgrp1.save()
    sgrp2.save()

    url = reverse("schemas:subjects")
    response = superuser_client.get(f"{url}?subject_subtypes={last_subject.subject_subtype.value}")

    assert response.status_code == 200
    response_json = response.json()
    assert len(response_json["oneOf"])
    for item in response_json["oneOf"]:
        # assert attached first subject filtered by first group
        assert item["const"] == str(last_subject.id)
        assert item["title"] == str(last_subject.name)
        # assert other created subjects aren't present
        assert item["const"] not in [str(two_subjects[0].id), str(two_subjects[1].id)]
        assert item["title"] not in [str(two_subjects[0].name), str(two_subjects[1].name)]


@pytest.mark.django_db
def test_dynamic_subjects_filtered_by_group_id(superuser_client):
    two_subjects = SubjectFactory.create_batch(2)
    last_subject = SubjectFactory.create()

    sgrp1 = SubjectGroup.objects.create(name="Subject Group 1")
    sgrp2 = SubjectGroup.objects.create(name="Subject Group 2")
    sgrp1.subjects.add(two_subjects[0])
    sgrp2.subjects.add(last_subject)

    sgrp1.save()
    sgrp2.save()

    url = reverse("schemas:subjects")
    response = superuser_client.get(f"{url}?subject_group={sgrp1.id}")
    assert response.status_code == 200

    response_json = response.json()
    assert len(response_json["oneOf"]) == 1
    for item in response_json["oneOf"]:
        # assert attached first subject filtered by first group
        assert item["const"] == str(two_subjects[0].id)
        assert item["title"] == two_subjects[0].name
        # assert other created subjects aren't present
        assert item["const"] not in [str(two_subjects[1].id), str(last_subject.id)]
        assert item["title"] not in [str(two_subjects[1].name), str(last_subject.name)]


@pytest.mark.django_db
def test_get_sources_dynamic_schemas(superuser_client, source):
    """Test sources dynamic schema returns correct structure."""
    url = reverse("schemas:sources")
    response = superuser_client.get(url)

    data = response.json()

    assert response.status_code == 200
    assert data["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert "oneOf" in data
    assert len(data["oneOf"]) >= 1

    # Find our test source in the response
    source_items = [item for item in data["oneOf"] if item["const"] == str(source.id)]
    assert len(source_items) == 1

    source_item = source_items[0]
    assert source_item["const"] == str(source.id)
    assert source_item["title"]  # Should have a title (display name)
    source.refresh_from_db()
    if source.manufacturer_id and source.model_name:
        assert source_item["title"] == (source.model_name or "").strip()
        assert source_item["description"] == (source.manufacturer_id or "").strip()
    elif source.manufacturer_id:
        assert source_item["title"] == (source.manufacturer_id or "").strip()
        assert "description" not in source_item
    elif source.model_name:
        assert source_item["title"] == (source.model_name or "").strip()
        assert "description" not in source_item
    else:
        assert source_item["title"] == (source.source_type or f"Source {source.id}")
        assert "description" not in source_item


@pytest.mark.django_db
def test_sources_display_name_logic(superuser_client):
    """Test that sources display name logic works correctly with different field combinations."""

    # Test source with manufacturer_id and model_name
    source1 = SourceFactory.create(manufacturer_id="GPS-COLLAR-123", model_name="Vectronic Aerospace")

    # Test source with only manufacturer_id
    source2 = SourceFactory.create(manufacturer_id="SENSOR-456", model_name="")

    # Test source with only model_name
    source3 = SourceFactory.create(manufacturer_id="", model_name="Custom Device")

    # Test source with only source_type
    source4 = SourceFactory.create(manufacturer_id="", model_name="", source_type="tracking-device")

    url = reverse("schemas:sources")
    response = superuser_client.get(url)

    assert response.status_code == 200
    data = response.json()

    # Find each source and verify title / description rules
    items_by_id = {item["const"]: item for item in data["oneOf"]}

    # Source 1: model_name as title, manufacturer_id as description
    source1_item = items_by_id[str(source1.id)]
    assert source1_item["title"] == "Vectronic Aerospace"
    assert source1_item["description"] == "GPS-COLLAR-123"

    # Source 2: manufacturer_id only — title only, no description
    source2_item = items_by_id[str(source2.id)]
    assert source2_item["title"] == "SENSOR-456"
    assert "description" not in source2_item

    # Source 3: model_name only — title only, no description
    source3_item = items_by_id[str(source3.id)]
    assert source3_item["title"] == "Custom Device"
    assert "description" not in source3_item

    # Source 4: fallback to source_type, no description
    source4_item = items_by_id[str(source4.id)]
    assert source4_item["title"] == "tracking-device"
    assert "description" not in source4_item


@pytest.mark.django_db
def test_sources_schema_accessible_to_authenticated_users(user_client):
    """Test that sources dynamic schema is accessible to authenticated users."""

    # Create a source that should be visible to authenticated users
    source = SourceFactory.create(manufacturer_id="TEST-SOURCE")

    url = reverse("schemas:sources")
    response = user_client.get(url)

    # Should return 200 for authenticated users (permission relaxed like choices)
    assert response.status_code == 200
    data = response.json()
    assert data["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert "oneOf" in data

    # Verify structure is correct
    for item in data["oneOf"]:
        assert "const" in item
        assert "title" in item


@pytest.mark.django_db
def test_get_event_types_dynamic_schemas(superuser_client, event_type):
    """Test event types dynamic schema returns correct structure."""
    url = reverse("schemas:event_types")
    response = superuser_client.get(url)

    data = response.json()

    assert response.status_code == 200
    assert data["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert "oneOf" in data
    assert len(data["oneOf"]) >= 1

    # Find our test event type in the response
    event_type_items = [item for item in data["oneOf"] if item["const"] == str(event_type.id)]
    assert len(event_type_items) == 1

    event_type_item = event_type_items[0]
    assert event_type_item["const"] == str(event_type.id)
    assert event_type_item["title"] == event_type.display
    assert event_type_item["description"] == event_type.value


@pytest.mark.django_db
def test_event_types_schema_structure(superuser_client):
    """Test that event types schema uses correct field mappings."""

    # Create event types with specific values to test field mappings
    event_type1 = EventTypeFactory.create(value="test_event_type_1", display="Test Event Type 1")

    event_type2 = EventTypeFactory.create(value="test_event_type_2", display="Test Event Type 2")

    url = reverse("schemas:event_types")
    response = superuser_client.get(url)

    assert response.status_code == 200
    data = response.json()

    # Find each event type and verify field mappings
    items_by_id = {item["const"]: item for item in data["oneOf"]}

    # Event type 1: const=id, title=display, description=value
    event_type1_item = items_by_id[str(event_type1.id)]
    assert event_type1_item["const"] == str(event_type1.id)
    assert event_type1_item["title"] == "Test Event Type 1"
    assert event_type1_item["description"] == "test_event_type_1"

    # Event type 2: const=id, title=display, description=value
    event_type2_item = items_by_id[str(event_type2.id)]
    assert event_type2_item["const"] == str(event_type2.id)
    assert event_type2_item["title"] == "Test Event Type 2"
    assert event_type2_item["description"] == "test_event_type_2"


@pytest.mark.django_db
def test_event_types_permissions_and_categories(superuser_client):
    """Test that event types respect category permissions."""

    # Create event categories and types
    category1 = EventCategoryFactory.create(value="category1", is_active=True)
    category2 = EventCategoryFactory.create(value="category2", is_active=True)
    inactive_category = EventCategoryFactory.create(value="inactive", is_active=False)

    event_type1 = EventTypeFactory.create(value="event_in_category1", display="Event in Category 1", category=category1)

    event_type2 = EventTypeFactory.create(value="event_in_category2", display="Event in Category 2", category=category2)

    # Event type in inactive category (should be filtered out)
    event_type_inactive = EventTypeFactory.create(
        value="event_in_inactive_category", display="Event in Inactive Category", category=inactive_category
    )

    url = reverse("schemas:event_types")
    response = superuser_client.get(url)

    assert response.status_code == 200
    data = response.json()

    # Get all const values (event type IDs) from response
    response_ids = [item["const"] for item in data["oneOf"]]

    # Active category event types should be present (for superuser)
    assert str(event_type1.id) in response_ids
    assert str(event_type2.id) in response_ids

    # Inactive category event type should NOT be present
    assert str(event_type_inactive.id) not in response_ids


@pytest.mark.django_db
def test_event_types_schema_accessible_to_authenticated_users(user_client):
    """Test that event types dynamic schema is accessible to authenticated users."""

    # Create an event type
    event_type = EventTypeFactory.create(value="test_event_type", display="Test Event Type")

    url = reverse("schemas:event_types")
    response = user_client.get(url)

    # Should return 200 for authenticated users
    assert response.status_code == 200
    data = response.json()
    assert data["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert "oneOf" in data

    # Verify structure is correct
    for item in data["oneOf"]:
        assert "const" in item
        assert "title" in item

    created_item = next(item for item in data["oneOf"] if item["const"] == str(event_type.id))
    assert created_item["title"] == event_type.display
    assert created_item["description"] == event_type.value
