import pytest

"""Tests for SubjectTrackSegmentsV2View request/response and parsing."""
from rest_framework.test import APIRequestFactory, force_authenticate

from das.factories import UserFactory
from observations.models import Subject
from observations.views import SubjectTrackSegmentsV2View


@pytest.fixture
def api_factory():
    return APIRequestFactory()


@pytest.fixture
def subject(db):
    # Prefer factory to ensure tenant and relations
    try:
        from factories import SubjectFactory

        return SubjectFactory()
    except Exception:
        return Subject.objects.create(name="Test Subject")


@pytest.fixture
def auth_client(client, db):
    # Create a tenant-aware user via factory to match app expectations
    user = UserFactory()
    client.force_login(user)
    client.user = user
    return client


def build_view_request(params=None, user=None):
    factory = APIRequestFactory()
    url = "/observations/subjects/%s/segments/v2/" % "00000000-0000-0000-0000-000000000000"
    request = factory.get(url, params or {})
    if user:
        force_authenticate(request, user=user)
    return request


class TestSubjectTrackSegmentsV2View:
    def test_query_param_parsing_edge_cases(self, auth_client, subject, monkeypatch):
        # Bypass permission checks
        monkeypatch.setattr(type(auth_client.user), "has_any_perms", lambda *_args, **_kwargs: True)
        url = f"/api/v2.0/subject/{subject.id}/tracks/"
        resp = auth_client.get(
            url,
            {
                "since": "2025-01-01T00:00:00Z",
                "until": "",
                "max_speed_kmh": "not-a-number",
                "max_gap_ms": "",
                "max_gap_seconds": "3600",
                "group_by_flags": "TrUe",
                "show_excluded": "false",
            },
        )
        assert resp.status_code in (200, 204)

    def test_permission_checks(self, api_factory, subject, monkeypatch, auth_client):
        # Patch has_any_perms to return False to trigger PermissionDenied
        def fake_has_any_perms(self, perms, obj):
            return False

        user = auth_client.user
        monkeypatch.setattr(type(user), "has_any_perms", fake_has_any_perms)
        # Narrow queryset to avoid unrelated annotation expectations
        monkeypatch.setattr(
            SubjectTrackSegmentsV2View,
            "get_queryset",
            lambda self: Subject.objects.filter(id=subject.id),
        )
        # Use as_view() to exercise DRF permission flow
        view = SubjectTrackSegmentsV2View.as_view()
        url = f"/api/v2.0/subject/{subject.id}/tracks/"
        req = api_factory.get(url)
        force_authenticate(req, user=user)
        resp = view(req, subject_id=str(subject.id))
        assert resp.status_code == 403

    def test_invalid_date_formats(self, auth_client, subject, monkeypatch):
        # Bypass permission checks
        monkeypatch.setattr(type(auth_client.user), "has_any_perms", lambda *_args, **_kwargs: True)
        url = f"/api/v2.0/subject/{subject.id}/tracks/"
        resp = auth_client.get(url, {"since": "invalid", "until": "also-invalid"})
        assert resp.status_code in (200, 204)

    def test_request_response_cycle(self, auth_client, subject, monkeypatch):
        # Ensure user has permission
        user = auth_client.user
        monkeypatch.setattr(type(user), "has_any_perms", lambda *_args, **_kwargs: True)

        url = f"/api/v2.0/subject/{subject.id}/tracks/"
        resp = auth_client.get(
            url,
            {
                "since": "2025-01-01T00:00:00Z",
                "until": "2025-12-31T23:59:59Z",
                "max_gap_minutes": "5",
                "max_speed_kmh": "12.5",
                "group_by_flags": "false",
                "show_excluded": "true",
            },
        )
        assert resp.status_code in (200, 204)
        assert resp.data
        assert resp.data.get("type") == "FeatureCollection"
