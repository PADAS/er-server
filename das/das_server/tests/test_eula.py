from django.db import IntegrityError
from django.test import TestCase

from das_server.models import EULA


class EulaModelTestCase(TestCase):
    def test_only_unique_eula_version_numbers_accepted(self):
        EULA.objects.create(content="Do do this", version_number=1.0)

        with self.assertRaises(IntegrityError):
            EULA.objects.create(content="Do do this", version_number=1.0)

    def test_only_one_active_eula_can_exist_at_any_time(self):
        EULA.objects.create(content="Do do this", version_number=1.0,
                                    active=True)
        EULA.objects.create(content="Do do this v2", version_number=1.1,
                            active=True)
        latest_eula = EULA.objects.create(content="Do do this v3", version_number=1.2,
                                    active=True)

        self.assertEqual(len(EULA.objects.filter(active=True)), 1)
        active_eula = EULA.objects.get(active=True)
        self.assertEqual(active_eula, latest_eula)

    def test_get_current_eula_version(self):
        EULA.objects.create(content="Do do this", version_number=1.0,
                            active=True)
        eula = EULA.objects.create(content="Do do this", version_number=1.4)
        active_eula = EULA.objects.get_active_eula()
        self.assertEqual(active_eula, eula)

    def test_get_users_that_agreed_to_current_eula_version(self):
        self.fail("Not implemented")

    def test_get_users_that_have_acknowledged_eula(self):
        self.fail("not implemented")

    def test_accepted_eula_flag_changed_to_false_for_all_new_users_when_new_eula_version_added(self):
        self.fail("not implemented")
