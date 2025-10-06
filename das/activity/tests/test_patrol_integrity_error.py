"""
Test to verify that IntegrityError handling works correctly after our fix.

This test simulates the scenario that was causing TransactionManagementError
in production by forcing IntegrityError conditions.
"""

import logging

import pytest

from django.db import IntegrityError, transaction
from django.db.transaction import TransactionManagementError
from django.test import TransactionTestCase

from activity.models import Patrol
from core.models import DASTenant

logger = logging.getLogger(__name__)


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant")
class TestIntegrityErrorFix(TransactionTestCase):
    """Test case to verify IntegrityError handling works correctly."""

    def setUp(self):
        """Set up test data."""
        # Use the tenant from the fixture
        self.tenant = DASTenant.objects.first()

        # Clear any existing patrols for clean test
        Patrol.objects.filter(das_tenant=self.tenant).delete()

    def test_integrity_error_handling_with_retry(self):
        """
        Test that IntegrityError is handled correctly without causing
        TransactionManagementError.

        This simulates the production scenario where concurrent patrol creation
        could cause IntegrityError due to serial number conflicts.
        """
        logger.info("Testing IntegrityError handling...")

        try:
            with transaction.atomic():
                # Create first patrol
                patrol1 = Patrol.objects.create(das_tenant=self.tenant, title="Test Patrol 1", state="open")
                logger.info(f"Created patrol 1 with serial_number: {patrol1.serial_number}")

                # Now try to create a patrol with the same serial number
                # This should trigger IntegrityError but be handled gracefully
                patrol2 = Patrol(
                    das_tenant=self.tenant,
                    title="Test Patrol 2",
                    state="open",
                    serial_number=patrol1.serial_number,  # Force conflict
                )

                # With our fix, this should work without IntegrityError
                # The SerialNumberModelMixin will generate a new serial number
                patrol2.save()
                logger.info(f"Created patrol 2 with serial_number: {patrol2.serial_number}")

                # Verify that patrol2 got a different serial number
                self.assertNotEqual(patrol1.serial_number, patrol2.serial_number)

                # Try to create another patrol - this should work
                patrol3 = Patrol.objects.create(das_tenant=self.tenant, title="Test Patrol 3", state="open")
                logger.info(f"Created patrol 3 with serial_number: {patrol3.serial_number}")

                # Verify we can still query the database
                patrol_count = Patrol.objects.filter(das_tenant=self.tenant).count()
                self.assertEqual(patrol_count, 3)  # patrol1, patrol2, and patrol3

                # Verify all serial numbers are unique
                serial_numbers = [patrol1.serial_number, patrol2.serial_number, patrol3.serial_number]
                self.assertEqual(len(set(serial_numbers)), len(serial_numbers))

                logger.info("Serial number generation working correctly - no IntegrityError!")

        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            self.fail(f"Unexpected error occurred: {e}")

    def test_concurrent_patrol_creation_simulation(self):
        """
        Test that simulates concurrent patrol creation that could happen
        in production.
        """
        logger.info("Testing concurrent patrol creation simulation...")

        try:
            with transaction.atomic():
                # Create multiple patrols rapidly
                patrols = []
                for i in range(3):
                    try:
                        patrol = Patrol.objects.create(
                            das_tenant=self.tenant, title=f"Concurrent Patrol {i+1}", state="open"
                        )
                        patrols.append(patrol)
                        logger.info(f"Created patrol {i+1} with serial_number: {patrol.serial_number}")
                    except IntegrityError as e:
                        logger.warning(f"IntegrityError during creation {i+1}: {e}")
                        # This should be handled gracefully without breaking the transaction
                        # Continue with the next patrol
                        continue
                    except Exception as e:
                        logger.error(f"Unexpected error during creation {i+1}: {e}")
                        raise

                # Verify we have some patrols created
                self.assertGreater(len(patrols), 0)

                # Verify all created patrols have unique serial numbers
                serial_numbers = [p.serial_number for p in patrols]
                self.assertEqual(len(set(serial_numbers)), len(serial_numbers))

                logger.info(f"Concurrent creation simulation successful - created {len(patrols)} patrols")

        except TransactionManagementError as e:
            logger.error(f"TransactionManagementError caught: {e}")
            self.fail(f"TransactionManagementError occurred: {e}")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            self.fail(f"Unexpected error occurred: {e}")
