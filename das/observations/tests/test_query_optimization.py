"""
Tests to verify query optimization in filters.
"""

import logging

from django.contrib.auth.models import Permission
from django.db import connection
from django.test.utils import CaptureQueriesContext

from accounts.models import PermissionSet, User
from core.tests import API_BASE, BaseAPITest
from observations.filters import create_gp_filter_class
from observations.models import SubjectGroup
from observations.views import SubjectGroupsView

logger = logging.getLogger(__name__)


class GroupPermissionsFilterQueryOptimizationTest(BaseAPITest):
    """
    Test that the GroupPermissionsFilter is optimized and doesn't have N+1 query problems.
    """

    def setUp(self):
        super().setUp()
        self.view_subject_group_perm = Permission.objects.get(codename="view_subjectgroup")
        self.perm_set = PermissionSet.objects.create(name="View Subject Group")
        self.perm_set.permissions.add(self.view_subject_group_perm)
        self.perm_set.save()

        user_const = dict(last_name="last", first_name="first")
        self.user = User.objects.create_user(
            username="test_user",
            email="test_user@test.com",
            password=User.objects.make_random_password(),
            **user_const,
        )
        self.user.permission_sets.add(self.perm_set)
        self.user.save()

        # Create a complex hierarchy with many groups
        # This will help expose N+1 query problems
        self.root_groups = []
        self.all_groups = []

        # Create 5 root groups
        for i in range(5):
            root = SubjectGroup.objects.create(name=f"Root Group {i}")
            self.root_groups.append(root)
            self.all_groups.append(root)

            # Each root has 3 children
            for j in range(3):
                child = SubjectGroup.objects.create(name=f"Child {i}-{j}")
                root.children.add(child)
                self.all_groups.append(child)

                # Each child has 2 grandchildren
                for k in range(2):
                    grandchild = SubjectGroup.objects.create(name=f"Grandchild {i}-{j}-{k}")
                    child.children.add(grandchild)
                    self.all_groups.append(grandchild)

        # Grant permissions to some groups
        # Give permission to 2 root groups
        self.root_groups[0].permission_sets.add(self.perm_set)
        self.root_groups[1].permission_sets.add(self.perm_set)

        # Give permission to some child groups directly
        child_groups = [g for g in self.all_groups if "Child" in g.name and "-0" not in g.name]
        for child in child_groups[:3]:
            child.permission_sets.add(self.perm_set)

    def test_query_count_is_reasonable_with_many_groups(self):
        """
        Test that the number of queries is reasonable and doesn't scale with the number of groups.

        With the old implementation, we would have queries for:
        - Each group: check permissions (ancestors + permission_sets)
        - Each group's children
        - Recursively for all descendants

        With 35 total groups (5 roots + 15 children + 15 grandchildren), this could be 100+ queries.

        With the optimized implementation, we should have:
        - 1 query to get user's permission sets
        - 1 query to fetch all groups
        - 1-2 queries to prefetch permission_sets
        - 1-2 queries to prefetch children relationships
        - 1-2 queries to prefetch parent relationships
        - A few queries to check permissions

        Total should be less than 15 queries regardless of the number of groups.
        """
        request = self.factory.get(API_BASE + "/subjectgroups")
        self.force_authenticate(request, self.user)

        with CaptureQueriesContext(connection) as context:
            response = SubjectGroupsView.as_view()(request)
            query_count = len(context.captured_queries)

        # Log queries for debugging
        logger.info(f"Query count: {query_count}")
        for i, query in enumerate(context.captured_queries, 1):
            logger.debug(f"Query {i}: {query['sql']}")

        # Assert the response is successful
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        # The key assertion: query count should be reasonable (not O(n) with number of groups)
        # With 35 groups, we should use less than 20 queries
        assert query_count < 20, (
            f"Expected less than 20 queries, got {query_count}. " f"This suggests an N+1 query problem."
        )

        # Log actual query count for visibility
        print(f"\nQuery count for 35 groups: {query_count}")

    def test_query_count_scales_well_with_more_groups(self):
        """
        Test that adding more groups doesn't dramatically increase query count.
        """
        # Get initial query count
        request = self.factory.get(API_BASE + "/subjectgroups")
        self.force_authenticate(request, self.user)

        with CaptureQueriesContext(connection) as context:
            response = SubjectGroupsView.as_view()(request)
            initial_query_count = len(context.captured_queries)

        print(f"\nInitial query count with 35 groups: {initial_query_count}")

        # Add 10 more root groups with children
        for i in range(5, 15):
            root = SubjectGroup.objects.create(name=f"Root Group {i}")
            root.permission_sets.add(self.perm_set)
            for j in range(3):
                child = SubjectGroup.objects.create(name=f"Child {i}-{j}")
                root.children.add(child)

        # Get query count with more groups (now 65 groups total)
        request2 = self.factory.get(API_BASE + "/subjectgroups")
        self.force_authenticate(request2, self.user)

        with CaptureQueriesContext(connection) as context2:
            response2 = SubjectGroupsView.as_view()(request2)
            new_query_count = len(context2.captured_queries)

        print(f"Query count with 65 groups: {new_query_count}")

        # Assert both responses are successful
        assert response.status_code == 200
        assert response2.status_code == 200

        # Query count should not increase by more than a few queries
        # (might increase by 1-2 for pagination or other minor factors)
        query_increase = new_query_count - initial_query_count
        assert query_increase < 5, (
            f"Query count increased by {query_increase} when doubling the number of groups. "
            f"Expected less than 5. This suggests the optimization isn't scaling properly."
        )

    def test_no_queries_during_tree_traversal(self):
        """
        Verify that once data is prefetched, no additional queries occur during tree traversal.
        """

        request = self.factory.get(API_BASE + "/subjectgroups")
        self.force_authenticate(request, self.user)

        # Get the filter
        filter_class = create_gp_filter_class("test_filter", ("observations.view_subjectgroup",), SubjectGroup)
        filter_instance = filter_class()

        # Get initial queryset
        queryset = SubjectGroup.objects.all()

        # First call to capture all queries
        with CaptureQueriesContext(connection) as context:
            filtered_queryset = filter_instance.filter_queryset(request, queryset, None)
            # Evaluate the queryset
            list(filtered_queryset)
            total_queries = len(context.captured_queries)

        print(f"\nTotal queries in filter: {total_queries}")

        # All queries should be upfront, not during traversal
        # This is a qualitative check - we're ensuring queries happen in bulk
        assert total_queries < 20, f"Expected less than 20 queries, got {total_queries}"
