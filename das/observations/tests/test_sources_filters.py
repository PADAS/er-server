"""
DB-backed integration tests for SourcesView filtering via ``SourceFilterSet``.

Covers:
- Comma-list IN filters: ``manufacturer_id``, ``provider_key``, ``provider``
  (alias), ``id``, ``source_type``.
- JSON exact filters: ``additional.species``, ``additional.gender`` (declared keys).
- Arbitrary (undeclared) ``additional.<key>`` filtering now that ``open=True``.
- Combined JSON bridge + plain column filter in the same request.
- Last-wins behaviour on a repeated ``additional.species`` param.
- Nonexistent/typo'd key in open mode yields zero matches (NULL-miss), not
  a silent ignore — a typo'd key just doesn't exist in any row's JSON.
"""

from __future__ import annotations

import pytest

from django.urls import reverse
from rest_framework.test import APIClient

from factories import ProviderFactory, SourceFactory, UserFactory

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_ids(response) -> set[str]:
    return {str(item["id"]) for item in response.data["results"]}


# ---------------------------------------------------------------------------
# JSON filters (additional.species, additional.gender, and open-mode arbitrary keys)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestSourcesViewJsonFieldFilter:
    """Integration tests for ``additional.<key>`` exact filtering on SourcesView."""

    @pytest.fixture(autouse=True)
    def setup(self, das_tenant):
        self.url = reverse("sources-view")
        superuser = UserFactory(is_superuser=True, das_tenant=das_tenant)
        self.client = APIClient()
        self.client.force_authenticate(user=superuser)

        provider = ProviderFactory(das_tenant=das_tenant)

        self.lion_male = SourceFactory(
            das_tenant=das_tenant,
            provider=provider,
            additional={"species": "lion", "gender": "male"},
        )
        self.lion_female = SourceFactory(
            das_tenant=das_tenant,
            provider=provider,
            additional={"species": "lion", "gender": "female"},
        )
        self.cheetah = SourceFactory(
            das_tenant=das_tenant,
            provider=provider,
            additional={"species": "cheetah", "gender": "female"},
        )
        self.no_additional = SourceFactory(
            das_tenant=das_tenant,
            provider=provider,
            additional={},
        )

    def test_filter_by_species_returns_matching_sources(self):
        response = self.client.get(self.url, {"additional.species": "lion"})
        assert response.status_code == 200
        ids = _get_ids(response)
        assert str(self.lion_male.id) in ids
        assert str(self.lion_female.id) in ids
        assert str(self.cheetah.id) not in ids
        assert str(self.no_additional.id) not in ids

    def test_filter_by_species_and_gender_narrows_results(self):
        response = self.client.get(self.url, {"additional.species": "lion", "additional.gender": "female"})
        assert response.status_code == 200
        ids = _get_ids(response)
        assert str(self.lion_female.id) in ids
        assert str(self.lion_male.id) not in ids
        assert str(self.cheetah.id) not in ids

    def test_filter_by_gender_returns_all_matching_sources(self):
        response = self.client.get(self.url, {"additional.gender": "female"})
        assert response.status_code == 200
        ids = _get_ids(response)
        assert str(self.lion_female.id) in ids
        assert str(self.cheetah.id) in ids
        assert str(self.lion_male.id) not in ids

    def test_no_data_params_returns_all_sources(self):
        response = self.client.get(self.url)
        assert response.status_code == 200
        ids = _get_ids(response)
        assert str(self.lion_male.id) in ids
        assert str(self.lion_female.id) in ids
        assert str(self.cheetah.id) in ids
        assert str(self.no_additional.id) in ids

    def test_arbitrary_undeclared_key_filters_open_mode(self):
        """SourceFilterSet is open=True, so any additional.<key> is applied end-to-end."""
        from factories import SourceFactory as SF

        provider = self.lion_male.provider
        das_tenant = self.lion_male.das_tenant

        tagged = SF(das_tenant=das_tenant, provider=provider, additional={"habitat": "savanna"})
        untagged = SF(das_tenant=das_tenant, provider=provider, additional={"habitat": "forest"})

        response = self.client.get(self.url, {"additional.habitat": "savanna"})
        assert response.status_code == 200
        ids = _get_ids(response)
        assert str(tagged.id) in ids
        assert str(untagged.id) not in ids
        # Existing fixtures have no 'habitat' key → NULL-miss → excluded.
        assert str(self.lion_male.id) not in ids
        assert str(self.no_additional.id) not in ids

    def test_nonexistent_key_in_open_mode_yields_zero_matches(self):
        """A typo'd / nonexistent additional key produces zero matches (NULL-miss)."""
        response = self.client.get(self.url, {"additional.definitely_not_a_real_key_xyz": "value"})
        assert response.status_code == 200
        ids = _get_ids(response)
        # Every fixture row lacks this key → text extraction is NULL → no match.
        assert str(self.lion_male.id) not in ids
        assert str(self.cheetah.id) not in ids
        assert str(self.no_additional.id) not in ids

    def test_last_wins_on_repeated_data_species(self):
        """When additional.species is repeated, the last value wins (QueryDict.get behaviour).

        The URL ``?additional.species=lion&additional.species=cheetah`` uses GET with a
        multi-value param.  DRF's QueryDict returns ``"cheetah"`` for ``.get()``,
        so only cheetah sources are returned.
        """
        url = self.url + "?additional.species=lion&additional.species=cheetah"
        response = self.client.get(url)
        assert response.status_code == 200
        ids = _get_ids(response)
        assert str(self.cheetah.id) in ids
        assert str(self.lion_male.id) not in ids
        assert str(self.lion_female.id) not in ids

    def test_injection_attempt_nested_path_yields_zero_matches(self):
        """?additional.species.icontains=lion is treated as nested key 'species'->'icontains'.

        In open mode this is applied as a real (but nested) path query.  Since no row
        has a JSON object at 'species' with an 'icontains' sub-key, text extraction
        returns NULL and zero rows match.  It is not a silent ignore — it is a NULL-miss.
        """
        response = self.client.get(self.url, {"additional.species.icontains": "lion"})
        assert response.status_code == 200
        ids = _get_ids(response)
        # No row has additional -> species -> icontains -> 'lion', so all are excluded.
        assert str(self.lion_male.id) not in ids
        assert str(self.cheetah.id) not in ids


# ---------------------------------------------------------------------------
# source_type IN filter
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestSourcesViewSourceTypeFilter:
    """Integration tests for ``source_type`` comma-list IN filter on SourcesView."""

    @pytest.fixture(autouse=True)
    def setup(self, das_tenant):
        self.url = reverse("sources-view")
        superuser = UserFactory(is_superuser=True, das_tenant=das_tenant)
        self.client = APIClient()
        self.client.force_authenticate(user=superuser)

        provider = ProviderFactory(das_tenant=das_tenant)

        self.tracking_device = SourceFactory(
            das_tenant=das_tenant,
            provider=provider,
            source_type="tracking-device",
        )
        self.trap = SourceFactory(
            das_tenant=das_tenant,
            provider=provider,
            source_type="trap",
        )
        self.no_type = SourceFactory(
            das_tenant=das_tenant,
            provider=provider,
            source_type=None,
        )

    def test_filter_by_source_type_tracking_device(self):
        response = self.client.get(self.url, {"source_type": "tracking-device"})
        assert response.status_code == 200
        ids = _get_ids(response)
        assert str(self.tracking_device.id) in ids
        assert str(self.trap.id) not in ids

    def test_filter_by_source_type_trap(self):
        response = self.client.get(self.url, {"source_type": "trap"})
        assert response.status_code == 200
        ids = _get_ids(response)
        assert str(self.trap.id) in ids
        assert str(self.tracking_device.id) not in ids

    def test_source_type_comma_list_returns_multiple_types(self):
        response = self.client.get(self.url, {"source_type": "tracking-device,trap"})
        assert response.status_code == 200
        ids = _get_ids(response)
        assert str(self.tracking_device.id) in ids
        assert str(self.trap.id) in ids
        assert str(self.no_type.id) not in ids

    def test_source_type_combined_with_json_field_filter(self):
        """``source_type`` and ``additional.species`` both apply simultaneously."""
        provider = self.tracking_device.provider
        source_with_both = SourceFactory(
            das_tenant=self.tracking_device.das_tenant,
            provider=provider,
            source_type="tracking-device",
            additional={"species": "lion"},
        )
        response = self.client.get(
            self.url,
            {"source_type": "tracking-device", "additional.species": "lion"},
        )
        assert response.status_code == 200
        ids = _get_ids(response)
        assert str(source_with_both.id) in ids
        # tracking_device has no species in additional → excluded by the JSON-field filter.
        assert str(self.tracking_device.id) not in ids


# ---------------------------------------------------------------------------
# Existing plain-column filters (regression)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestSourcesViewExistingFiltersUnchanged:
    """Regression: ``manufacturer_id``, ``provider_key``, ``provider``, ``id``
    continue to work after the FilterSet refactor."""

    @pytest.fixture(autouse=True)
    def setup(self, das_tenant):
        self.url = reverse("sources-view")
        superuser = UserFactory(is_superuser=True, das_tenant=das_tenant)
        self.client = APIClient()
        self.client.force_authenticate(user=superuser)

        self.provider_a = ProviderFactory(das_tenant=das_tenant)
        self.provider_b = ProviderFactory(das_tenant=das_tenant)

        self.source_a = SourceFactory(
            das_tenant=das_tenant,
            provider=self.provider_a,
            manufacturer_id="MFR-001",
        )
        self.source_b = SourceFactory(
            das_tenant=das_tenant,
            provider=self.provider_a,
            manufacturer_id="MFR-002",
        )
        self.source_c = SourceFactory(
            das_tenant=das_tenant,
            provider=self.provider_b,
            manufacturer_id="MFR-003",
        )

    def test_manufacturer_id_single_value(self):
        response = self.client.get(self.url, {"manufacturer_id": "MFR-001"})
        assert response.status_code == 200
        ids = _get_ids(response)
        assert str(self.source_a.id) in ids
        assert str(self.source_b.id) not in ids

    def test_manufacturer_id_comma_list(self):
        response = self.client.get(self.url, {"manufacturer_id": "MFR-001,MFR-002"})
        assert response.status_code == 200
        ids = _get_ids(response)
        assert str(self.source_a.id) in ids
        assert str(self.source_b.id) in ids
        assert str(self.source_c.id) not in ids

    def test_id_filter_single_uuid(self):
        response = self.client.get(self.url, {"id": str(self.source_a.id)})
        assert response.status_code == 200
        ids = _get_ids(response)
        assert str(self.source_a.id) in ids
        assert str(self.source_b.id) not in ids

    def test_id_filter_comma_list(self):
        response = self.client.get(self.url, {"id": f"{self.source_a.id},{self.source_c.id}"})
        assert response.status_code == 200
        ids = _get_ids(response)
        assert str(self.source_a.id) in ids
        assert str(self.source_c.id) in ids
        assert str(self.source_b.id) not in ids

    def test_provider_key_filter(self):
        response = self.client.get(self.url, {"provider_key": self.provider_a.provider_key})
        assert response.status_code == 200
        ids = _get_ids(response)
        assert str(self.source_a.id) in ids
        assert str(self.source_b.id) in ids
        assert str(self.source_c.id) not in ids

    def test_provider_alias_filter(self):
        """``provider`` is an alias for ``provider_key`` and must behave identically."""
        response = self.client.get(self.url, {"provider": self.provider_b.provider_key})
        assert response.status_code == 200
        ids = _get_ids(response)
        assert str(self.source_c.id) in ids
        assert str(self.source_a.id) not in ids

    def test_provider_key_comma_list(self):
        response = self.client.get(
            self.url,
            {"provider_key": f"{self.provider_a.provider_key},{self.provider_b.provider_key}"},
        )
        assert response.status_code == 200
        ids = _get_ids(response)
        assert str(self.source_a.id) in ids
        assert str(self.source_b.id) in ids
        assert str(self.source_c.id) in ids
