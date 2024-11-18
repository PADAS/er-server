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
