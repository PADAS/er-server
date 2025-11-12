import json
from unittest.mock import patch

import pytest
from psycopg2.errors import InvalidTextRepresentation

from django.urls import reverse
from rest_framework import status


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings")
class TestEventViewFilters:
    def test_filter_param_is_not_vulnerable_to_sql_injection(
        self, superuser_client, five_events_with_details, tenant_document_cache_client_mock, tenant_response
    ):
        url = reverse("events")
        term = (
            "'||(SELECT (CHR(97)||CHR(102)||CHR(107)||CHR(68)) WHERE 7152=7152 AND 8130=CAST((CHR(113)||CHR(106)||"
            "CHR(118)||CHR(107)||CHR(113))||(SELECT (CASE WHEN (8130=8130) THEN 1 ELSE 0 END))::text||(CHR(113)||"
            "CHR(107)||CHR(112)||CHR(113)||CHR(113)) AS NUMERIC))||'"
        )
        query_params = {
            "include_notes": True,
            "include_related_events": True,
            "state": ["active", "new"],
            "filter": json.dumps({"text": term}),
            "sort_by": "-updated_at",
        }

        response = superuser_client.get(url, query_params)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 0

    def test_filter_raises_invalid_text_representation(
        self, superuser_client, five_events_with_details, tenant_document_cache_client_mock, tenant_response
    ):
        url = reverse("events")
        with patch("activity.views.events.base.EventsView.get_paginated_response") as get_paginated_response_mock:
            get_paginated_response_mock.side_effect = InvalidTextRepresentation(
                "This message should not reach the user"
            )
            response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 0

    def test_filter_with_parentheses_in_text_search(
        self, superuser_client, five_events_with_details, tenant_document_cache_client_mock, tenant_response
    ):
        """Test that text filters with parentheses don't cause parsing errors."""
        url = reverse("events")
        # This is the actual text from the reported issue
        query_params = {
            "state": ["active", "new", "resolved"],
            "include_related_events": True,
            "include_notes": False,
            "include_files": False,
            "include_details": True,
            "include_updates": False,
            "filter": json.dumps({"text": "EWT-Cluster 260792 (318 pts, 1 devices)"}),
            "page_size": 1,
            "page": 1,
        }

        response = superuser_client.get(url, query_params)

        # Should not raise a parsing error
        assert response.status_code == status.HTTP_200_OK
        assert "count" in response.data

    def test_filter_with_special_characters_in_text_search(
        self, superuser_client, five_events_with_details, tenant_document_cache_client_mock, tenant_response
    ):
        """Test that text filters with various special characters don't cause parsing errors."""
        url = reverse("events")

        # Test various special characters that could cause tsquery syntax errors
        test_cases = [
            "test & test",  # ampersand
            "test | test",  # pipe
            "test ! test",  # exclamation
            "test < test",  # less than
            "test > test",  # greater than
            "test (parentheses) test",  # parentheses
            "test <-> test",  # followed by operator
            "complex & | ! < > () test",  # multiple special chars
        ]

        for search_text in test_cases:
            query_params = {
                "filter": json.dumps({"text": search_text}),
            }

            response = superuser_client.get(url, query_params)

            # Should not raise a parsing error for any of these
            assert response.status_code == status.HTTP_200_OK, f"Failed for search text: {search_text}"
            assert "count" in response.data
