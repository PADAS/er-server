import uuid

import pytest

from django.contrib.admin import site as admin_site
from django.contrib.admin.models import ADDITION, DELETION, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory

from factories import (
    ObservationFactory,
    ProviderFactory,
    SubjectFactory,
    SubjectSourceFactory,
    TenantFactory,
    UserFactory,
)
from observations.admin import (
    ObservationAdmin,
    SourceAdmin,
    SourceProviderAdmin,
    SubjectAdmin,
)
from observations.models import Observation, Source, SourceProvider, Subject


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
def test_subject_admin_delete_queryset_with_distinct(superuser):
    """
    SubjectAdmin.get_queryset returns a .distinct() queryset (needed to avoid
    duplicate rows when M2M/join filters are active).  Django forbids calling
    .delete() on a distinct queryset, so delete_queryset must work around that.
    """
    subject1 = SubjectFactory()
    subject2 = SubjectFactory()

    admin_instance = SubjectAdmin(model=Subject, admin_site=admin_site)
    request = RequestFactory().get("/")
    request.user = superuser

    # Simulate exactly what Django's admin delete action does:
    # get_queryset() returns a .distinct() queryset, which is passed to delete_queryset()
    selected = admin_instance.get_queryset(request).filter(pk__in=[subject1.pk, subject2.pk])
    assert selected.query.distinct, "precondition: selected queryset must have distinct to reproduce the bug"

    # Should not raise "Cannot call delete() after .distinct()"
    admin_instance.delete_queryset(request, selected)

    assert not Subject.objects.filter(pk__in=[subject1.pk, subject2.pk]).exists()


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestObservationAdminBulkDelete:
    """Covers the custom delete_selected_observations action that replaces Django's
    default to avoid per-row LogEntry inserts and per-row hidden inputs in the
    confirmation form."""

    def _make_request(self, method, superuser, post_data=None):
        factory = RequestFactory()
        request = factory.post("/", post_data or {}) if method == "POST" else factory.get("/")
        request.user = superuser
        # delete_selected_observations writes flash messages — RequestFactory doesn't
        # attach a messages backend, so add a no-op storage.
        from django.contrib.messages.storage.fallback import FallbackStorage

        setattr(request, "session", {})
        setattr(request, "_messages", FallbackStorage(request))
        return request

    def test_bulk_delete_post_removes_rows_and_writes_single_summary_log_entry(self, superuser):
        observations = ObservationFactory.create_batch(3)
        ids = [o.id for o in observations]
        ct = ContentType.objects.get_for_model(Observation)
        log_count_before = LogEntry.objects.filter(content_type=ct, action_flag=DELETION).count()

        admin = ObservationAdmin(model=Observation, admin_site=admin_site)
        request = self._make_request("POST", superuser, post_data={"post": "yes"})
        queryset = Observation.objects.filter(id__in=ids)

        admin.delete_selected_observations(request, queryset)

        assert not Observation.objects.filter(id__in=ids).exists(), "rows must be deleted"

        new_entries = LogEntry.objects.filter(content_type=ct, action_flag=DELETION).order_by("-id")
        assert (
            new_entries.count() - log_count_before == 1
        ), "exactly one summary LogEntry per bulk action — not one per row"
        entry = new_entries.first()
        assert "3" in entry.object_repr, "summary entry must include the count"
        assert "bulk" in entry.object_repr.lower()
        assert entry.user_id == superuser.pk

    def test_bulk_delete_select_across_emits_single_hidden_field(self, superuser):
        # When the user picks "select all 100k" on the changelist, the action receives
        # select_across=1 and must emit ONE hidden field, not one per row — otherwise
        # the confirmation page is hundreds of MBs of HTML.
        ObservationFactory.create_batch(3)

        admin = ObservationAdmin(model=Observation, admin_site=admin_site)
        request = self._make_request("POST", superuser, post_data={"select_across": "1"})
        queryset = Observation.objects.all()

        response = admin.delete_selected_observations(request, queryset)
        assert response is not None
        rendered = response.render().content.decode()

        # With select_across, the template renders <input name="select_across" value="1">
        # exactly once and skips the per-row {% for %} loop.
        assert rendered.count('name="select_across"') == 1
        assert (
            rendered.count('name="_selected_action"') == 0
        ), "select_across path must not iterate the queryset to emit per-row inputs"

    def test_bulk_delete_get_renders_confirmation_with_summary_count(self, superuser):
        # GET path (initial confirmation) should render the model-count summary so
        # the user sees "Observations: N" without paying the cost of the default
        # collector or rendering an unordered_list per row.
        ObservationFactory.create_batch(4)

        admin = ObservationAdmin(model=Observation, admin_site=admin_site)
        request = self._make_request("GET", superuser)
        queryset = Observation.objects.all()

        response = admin.delete_selected_observations(request, queryset)
        assert response is not None
        rendered = response.render().content.decode()
        # The custom template includes admin/includes/object_delete_summary.html
        # which renders the model_count dict as "<verbose_name>: <count>" lines.
        assert "4" in rendered, "summary count must appear on the confirmation page"

    def test_default_delete_selected_action_is_removed(self, superuser):
        admin = ObservationAdmin(model=Observation, admin_site=admin_site)
        request = self._make_request("GET", superuser)
        actions = admin.get_actions(request)
        assert "delete_selected" not in actions, "default action would re-introduce per-row LogEntry inserts"
        assert "delete_selected_observations" in actions


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestHistoryViewPaginatesActionList:
    """
    Regression test for the bug where history_view passed a raw QuerySet as
    action_list in extra_context instead of a paginated Page object.

    Django's parent history_view merges extra_context last, so the raw
    queryset overwrote the page object that Django had already built.  The
    template then called action_list.paginator.count on a QuerySet — which has
    no .paginator attribute — producing None, which caused:

        TemplateSyntaxError: 'counter' argument to 'blocktranslate' tag must be
        a number
    """

    def _make_history_request(self, superuser):
        request = RequestFactory().get("/")
        request.user = superuser
        # history_view renders a TemplateResponse which does not require a
        # full middleware stack, but admin.each_context checks has_permission,
        # and some template tags require these attributes.
        setattr(request, "session", {})
        setattr(request, "_messages", FallbackStorage(request))
        return request

    def test_history_view_returns_200(self, superuser):
        provider = ProviderFactory()
        # Create a LogEntry so that action_list is non-empty and the template
        # enters the {% if action_list %} branch that contains the blocktranslate
        # tag with counter=action_list.paginator.count.  Without at least one
        # entry the branch is skipped and the TemplateSyntaxError caused by a
        # non-integer counter (i.e. a raw QuerySet with no .paginator attribute)
        # would never be triggered.
        LogEntry.objects.log_action(
            user_id=superuser.pk,
            content_type_id=ContentType.objects.get_for_model(SourceProvider).pk,
            object_id=provider.pk,
            object_repr=str(provider),
            action_flag=ADDITION,
        )
        admin_instance = SourceProviderAdmin(model=SourceProvider, admin_site=admin_site)
        request = self._make_history_request(superuser)

        response = admin_instance.history_view(request, str(provider.pk))

        assert response.status_code == 200
        # Force template rendering so that any TemplateSyntaxError raised during
        # blocktranslate (e.g. from a non-integer counter argument) surfaces here
        # rather than being silently swallowed by the lazy TemplateResponse.
        response.rendered_content

    def test_history_view_excludes_log_entries_from_other_tenant_users(self, superuser):
        provider = ProviderFactory()
        other_tenant = TenantFactory(id=uuid.uuid4(), domain="other.com")
        other_user = UserFactory(das_tenant=other_tenant)
        LogEntry.objects.log_action(
            user_id=other_user.pk,
            content_type_id=ContentType.objects.get_for_model(SourceProvider).pk,
            object_id=provider.pk,
            object_repr=str(provider),
            action_flag=ADDITION,
        )
        admin_instance = SourceProviderAdmin(model=SourceProvider, admin_site=admin_site)
        request = self._make_history_request(superuser)

        response = admin_instance.history_view(request, str(provider.pk))

        action_list = response.context_data["action_list"]
        assert (
            action_list.paginator.count == 0
        ), "log entries authored by users from another tenant must not appear in history_view"


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestSourceAdminChangeView:
    """
    Regression test for the bug where the Source admin change_view raised
    NoReverseMatch because the inline observations queryset omitted the 'id'
    field from .values(), causing the template to render an empty-string pk in
    the admin:observations_observation_change URL.
    """

    def _make_change_request(self, superuser: object) -> object:
        request = RequestFactory().get("/")
        request.user = superuser
        setattr(request, "session", {})
        setattr(request, "_messages", FallbackStorage(request))
        return request

    def test_change_view_returns_200_when_source_has_observation_in_assigned_range(self, superuser: object) -> None:
        subject_source = SubjectSourceFactory()
        observation = ObservationFactory(source=subject_source.source)

        admin_instance = SourceAdmin(model=Source, admin_site=admin_site)
        request = self._make_change_request(superuser)

        response = admin_instance.change_view(request, str(subject_source.source.pk))

        assert response.status_code == 200
        # Force template rendering so that NoReverseMatch (caused by an empty-string
        # observation id in the inline URL) surfaces here rather than being swallowed
        # by the lazy TemplateResponse.
        rendered = response.rendered_content
        assert str(observation.pk) in rendered, (
            "The rendered inline must contain the real observation pk; "
            "an empty string means 'id' was missing from .values()"
        )
