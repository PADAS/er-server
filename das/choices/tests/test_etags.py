import pytest

from choices.etags import get_event_choices_version
from choices.models import Choice


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestGetEventChoicesVersion:
    def test_stable_when_nothing_changes(self):
        Choice.objects.create(model=Choice.EVENT_MODEL, field="species", value="lion", display="Lion")

        version = get_event_choices_version()

        assert version == get_event_choices_version()

    def test_changes_when_an_event_choice_is_created(self):
        Choice.objects.create(model=Choice.EVENT_MODEL, field="species", value="lion", display="Lion")
        version_before = get_event_choices_version()

        Choice.objects.create(model=Choice.EVENT_MODEL, field="species", value="elephant", display="Elephant")

        assert get_event_choices_version() != version_before

    def test_changes_when_an_event_choice_is_updated(self):
        choice = Choice.objects.create(model=Choice.EVENT_MODEL, field="species", value="lion", display="Lion")
        version_before = get_event_choices_version()

        choice.display = "African Lion"
        choice.save()

        assert get_event_choices_version() != version_before

    def test_changes_when_an_event_choice_is_soft_deleted(self):
        choice = Choice.objects.create(model=Choice.EVENT_MODEL, field="species", value="lion", display="Lion")
        version_before = get_event_choices_version()

        choice.disable()

        assert get_event_choices_version() != version_before

    def test_unaffected_by_choices_for_a_different_model(self):
        Choice.objects.create(model=Choice.EVENT_MODEL, field="species", value="lion", display="Lion")
        version_before = get_event_choices_version()

        Choice.objects.create(model=Choice.EVENT_TYPE_MODEL, field="category", value="security", display="Security")

        assert get_event_choices_version() == version_before

    def test_stable_when_there_are_no_event_choices(self):
        assert get_event_choices_version() == get_event_choices_version()

    def test_changes_when_event_choices_are_bulk_disabled(self):
        Choice.objects.create(model=Choice.EVENT_MODEL, field="species", value="lion", display="Lion")
        version_before = get_event_choices_version()

        Choice.objects.filter(model=Choice.EVENT_MODEL, value="lion").disable_choices()

        assert get_event_choices_version() != version_before

    def test_changes_when_event_choices_are_bulk_soft_deleted(self):
        Choice.objects.create(model=Choice.EVENT_MODEL, field="species", value="lion", display="Lion")
        version_before = get_event_choices_version()

        Choice.objects.filter(model=Choice.EVENT_MODEL, value="lion").soft_delete()

        assert get_event_choices_version() != version_before

    def test_changes_when_is_active_is_toggled_off_via_bulk_update(self):
        Choice.objects.create(model=Choice.EVENT_MODEL, field="species", value="lion", display="Lion")
        version_before = get_event_choices_version()

        Choice.objects.filter(model=Choice.EVENT_MODEL, value="lion").update(is_active=False)

        assert get_event_choices_version() != version_before

    def test_changes_when_is_active_is_toggled_back_on_via_bulk_update(self):
        Choice.objects.create(model=Choice.EVENT_MODEL, field="species", value="lion", display="Lion")
        Choice.objects.filter(model=Choice.EVENT_MODEL, value="lion").update(is_active=False)
        version_before = get_event_choices_version()

        Choice.objects.filter(model=Choice.EVENT_MODEL, value="lion").update(is_active=True)

        assert get_event_choices_version() != version_before

    def test_disable_choices_bulk_soft_delete_advances_updated_at(self):
        """QuerySet.update() bypasses auto_now, so disable_choices() must set
        updated_at explicitly - otherwise anything that incrementally syncs
        Choice by updated_at (mobile deltas, DWH CDC) would miss bulk soft-deletes.
        """
        choice = Choice.objects.create(model=Choice.EVENT_MODEL, field="species", value="lion", display="Lion")
        updated_at_before = choice.updated_at

        Choice.objects.filter(model=Choice.EVENT_MODEL, value="lion").disable_choices()

        choice.refresh_from_db()
        assert choice.updated_at is not None
        assert choice.updated_at > updated_at_before
