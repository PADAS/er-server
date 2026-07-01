from __future__ import annotations

import datetime
import re
import uuid
from urllib.parse import urlencode

import pytest

from django.contrib.admin import site as admin_site
from django.contrib.admin.models import ADDITION, DELETION, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import Client, RequestFactory
from django.urls import reverse
from django.utils import timezone

from das_server.admin import dasadmin_site
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
        # It emits exactly ONE _selected_action sentinel (not one per row): the
        # field must be present so changelist_view dispatches the confirmed POST,
        # but it must not iterate the queryset to emit per-row inputs.
        assert rendered.count('name="_selected_action"') == 1, (
            "select_across path must emit a single _selected_action sentinel "
            "(required by changelist_view's dispatch gate), not one input per row"
        )

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
class TestObservationAdminChangelistDeleteFlow:
    """End-to-end regression coverage for the confirmed select-across delete bug.

    The select-across confirmation template emits no per-row _selected_action
    inputs (by design, to avoid one hidden input per row for huge sets).  But
    Django's changelist_view only dispatches the confirmed POST to
    response_action when helpers.ACTION_CHECKBOX_NAME ("_selected_action") is
    present in request.POST.  Without a sentinel field the confirmation POST is
    silently dropped and nothing is deleted.
    """

    CHANGELIST_URL = "admin:observations_observation_changelist"

    @staticmethod
    def _post_form(client: Client, url: str, fields: list[tuple[str, str]]):
        """POST as application/x-www-form-urlencoded so the data lands in
        request.POST (the admin reads form data, not a JSON body).  Accepts a
        list of pairs so repeated keys like _selected_action are preserved."""
        return client.post(url, data=urlencode(fields), content_type="application/x-www-form-urlencoded")

    @staticmethod
    def _hidden_inputs(html: str) -> list[tuple[str, str]]:
        """Extract (name, value) for every <input type="hidden"> inside the
        confirmation page, so the confirmation POST mirrors exactly what a
        browser would submit when the user clicks 'Yes, I'm sure'."""
        fields: list[tuple[str, str]] = []
        for tag in re.findall(r"<input[^>]*type=\"hidden\"[^>]*>", html):
            name = re.search(r'name="([^"]+)"', tag)
            value = re.search(r'value="([^"]*)"', tag)
            if name:
                fields.append((name.group(1), value.group(1) if value else ""))
        return fields

    def test_select_across_confirmation_post_deletes_all_matching_observations(self, superuser_client: Client) -> None:
        # The bug only bites when the user picks "select all N" (select-across)
        # rather than the visible page rows.
        observations = ObservationFactory.create_batch(5)
        ids = [o.id for o in observations]
        assert Observation.objects.filter(id__in=ids).count() == 5

        url = reverse(self.CHANGELIST_URL)

        # Step 1: the initial action POST from the changelist (has "index" and the
        # select_across marker, no "post=yes") renders the confirmation page.
        step1 = [("action", "delete_selected_observations"), ("select_across", "1"), ("index", "0")]
        step1 += [("_selected_action", str(o.id)) for o in observations]
        confirm = self._post_form(superuser_client, url, step1)
        assert confirm.status_code == 200
        html = confirm.content.decode()
        assert "Are you sure" in html, "expected the delete confirmation page to render"

        # Step 2: submit the confirmation form using ONLY the hidden inputs the
        # override template actually emits (plus post=yes) — i.e. exactly what a
        # browser posts on "Yes, I'm sure".  This is what proves the bug: the
        # current template omits any _selected_action field in the select-across
        # branch, so changelist_view's confirmation gate (ACTION_CHECKBOX_NAME in
        # request.POST) is False and nothing is deleted.
        confirm_fields = self._hidden_inputs(html)
        assert ("select_across", "1") in confirm_fields, "precondition: confirmation form is in select-across mode"

        response = self._post_form(superuser_client, url, confirm_fields)

        assert response.status_code in (200, 302), response.status_code
        assert not Observation.objects.filter(id__in=ids).exists(), (
            "select-across confirmation POST must delete ALL matching observations; "
            "nothing deleted means changelist_view dropped the POST because the "
            "confirmation template emitted no _selected_action sentinel"
        )

    def test_per_row_confirmation_post_deletes_only_selected_rows(self, superuser_client: Client) -> None:
        observations = ObservationFactory.create_batch(3)
        selected = observations[:2]
        unselected = observations[2]
        selected_ids = [o.id for o in selected]

        url = reverse(self.CHANGELIST_URL)
        # The per-row confirmation POST enumerates the selected pks (no "index",
        # select_across=0, post=yes) — exactly what the template's {% else %}
        # branch emits.
        fields = [("action", "delete_selected_observations"), ("select_across", "0"), ("post", "yes")]
        fields += [("_selected_action", str(o.id)) for o in selected]
        response = self._post_form(superuser_client, url, fields)

        assert response.status_code in (200, 302), response.status_code
        assert not Observation.objects.filter(id__in=selected_ids).exists(), "selected rows must be deleted"
        assert Observation.objects.filter(id=unselected.id).exists(), "unselected rows must remain"


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

    def test_das_admin_change_view_returns_200_without_observation_link(self, superuser_client: Client) -> None:
        """Regression test for ERA-13490 follow-up: the dasadmin site must not
        500 on the Source change page because Observation is not registered there.
        The inline observation row must degrade to plain text."""
        now = timezone.now()
        subject_source = SubjectSourceFactory(
            assigned_range=(now - datetime.timedelta(days=10), now + datetime.timedelta(days=10)),
        )
        observation = ObservationFactory(
            source=subject_source.source,
            recorded_at=now - datetime.timedelta(hours=1),
        )
        url = reverse("das_admin:observations_source_change", args=(str(subject_source.source.pk),))
        response = superuser_client.get(url)
        assert (
            response.status_code == 200
        ), "dasadmin Source change page must not 500 even though Observation is not registered there."
        content = response.content.decode()
        observation_change_url = reverse("admin:observations_observation_change", args=(str(observation.pk),))
        assert observation_change_url not in content, (
            "The dasadmin site must not emit a link to the observation change page; "
            "the row must degrade to plain text."
        )


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestSubjectAdminChangeView:
    """Regression test for ERA-13490: editing a Subject in the admin raised
    NoReverseMatch because the inline observations link reversed
    'observations_observation_change' without the 'admin:' namespace."""

    def test_change_view_renders_observation_link(self, superuser_client: Client) -> None:
        now = timezone.now()
        subject_source = SubjectSourceFactory(
            assigned_range=(now - datetime.timedelta(days=10), now + datetime.timedelta(days=10)),
        )
        observation = ObservationFactory(
            source=subject_source.source,
            recorded_at=now - datetime.timedelta(hours=1),
        )
        url = reverse("admin:observations_subject_change", args=(str(subject_source.subject.pk),))
        response = superuser_client.get(url)
        assert response.status_code == 200
        content = response.content.decode()
        assert str(observation.pk) in content, (
            "The rendered inline must contain the real observation pk and the "
            "namespaced admin URL must reverse cleanly."
        )
        expected_link = reverse("admin:observations_observation_change", args=(str(observation.pk),))
        assert expected_link in content, "The default admin site must render a link to the observation change page."

    def test_das_admin_change_view_returns_200_without_observation_link(self, superuser_client: Client) -> None:
        """Regression test for ERA-13490 follow-up: the dasadmin site must not
        500 when rendering the Subject change page, because Observation is not
        registered on that site.  The observation row must degrade to plain text
        instead of attempting to reverse 'das_admin:observations_observation_change'."""
        now = timezone.now()
        subject_source = SubjectSourceFactory(
            assigned_range=(now - datetime.timedelta(days=10), now + datetime.timedelta(days=10)),
        )
        observation = ObservationFactory(
            source=subject_source.source,
            recorded_at=now - datetime.timedelta(hours=1),
        )
        url = reverse("das_admin:observations_subject_change", args=(str(subject_source.subject.pk),))
        response = superuser_client.get(url)
        assert (
            response.status_code == 200
        ), "dasadmin Subject change page must not 500 even though Observation is not registered there."
        content = response.content.decode()
        observation_change_url = reverse("admin:observations_observation_change", args=(str(observation.pk),))
        assert observation_change_url not in content, (
            "The dasadmin site must not emit a link to the observation change page "
            "because Observation is not registered there; the row must degrade to plain text."
        )


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestDasAdminSiteGetAppList:
    """Regression tests for the DasAdminSite.get_app_list signature.

    Django 4.2 changed AdminSite.app_index to call get_app_list(request, app_label),
    passing two positional arguments.  The override previously only accepted one
    (request), causing a TypeError when the app_index view was requested.
    """

    def test_get_app_list_without_app_label_does_not_raise(self, superuser: object) -> None:
        request = RequestFactory().get("/")
        request.user = superuser
        # Must not raise TypeError even when app_label is omitted (index view path).
        result = dasadmin_site.get_app_list(request)
        assert isinstance(result, list)

    def test_get_app_list_with_app_label_does_not_raise(self, superuser: object) -> None:
        request = RequestFactory().get("/")
        request.user = superuser
        # Must not raise "takes 2 positional arguments but 3 were given".
        result = dasadmin_site.get_app_list(request, "observations")
        assert isinstance(result, list)

    def test_app_index_view_returns_200(self, superuser_client: Client) -> None:
        # Exercises the full Django 4.2 app_index path that calls
        # get_app_list(request, app_label) with two arguments.
        url = reverse("das_admin:app_list", kwargs={"app_label": "observations"})
        response = superuser_client.get(url)
        assert (
            response.status_code == 200
        ), "dasadmin app_index must not raise TypeError from get_app_list signature mismatch"
