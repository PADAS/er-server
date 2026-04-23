import uuid

import pytest

from activity.models import Event, Patrol
from core.mixins import _serial_number_lock_key

TENANT_A = uuid.UUID("11111111-1111-1111-1111-111111111111")
TENANT_B = uuid.UUID("22222222-2222-2222-2222-222222222222")


@pytest.mark.django_db
class TestSerialNumberLockKey:
    def test_deterministic(self):
        assert _serial_number_lock_key(TENANT_A, Event) == _serial_number_lock_key(TENANT_A, Event)

    def test_uuid_and_str_inputs_agree(self):
        """Guards against cross-worker lock divergence when one worker holds a
        ``UUID`` instance and another holds its string form."""
        assert _serial_number_lock_key(TENANT_A, Event) == _serial_number_lock_key(str(TENANT_A), Event)

    def test_distinct_tenants_distinct_keys(self):
        assert _serial_number_lock_key(TENANT_A, Event) != _serial_number_lock_key(TENANT_B, Event)

    def test_distinct_models_distinct_keys(self):
        assert _serial_number_lock_key(TENANT_A, Event) != _serial_number_lock_key(TENANT_A, Patrol)

    def test_fits_signed_int64(self):
        key = _serial_number_lock_key(TENANT_A, Event)
        assert -(2**63) <= key < 2**63

    def test_invalid_tenant_raises(self):
        with pytest.raises(ValueError):
            _serial_number_lock_key("not-a-uuid", Event)
