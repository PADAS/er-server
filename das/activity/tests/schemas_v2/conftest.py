import json
from pathlib import Path

import pytest


@pytest.fixture
def json_schema_fixture(request):
    """Load a JSON schema fixture file by name."""
    fixture_name = request.param
    fixture_path = Path(__file__).parent.parent / "fixtures" / f"{fixture_name}.json"
    with open(fixture_path) as f:
        return json.load(f)
