import pytest
from django_multitenant.utils import set_current_tenant

from activity.models import Community, EventCategory
from observations.models import Source, SourceProvider
from utils.tenant import set_tenant_settings


@pytest.mark.django_db
class TestDASTenant:
    def test_filter_objects_by_tenant(self, five_tenants, five_communities):
        tenant_a = five_tenants[0]
        tenant_b = five_tenants[1]
        two_communities = five_communities[:2]
        three_communities = five_communities[2:]
        for community in two_communities:
            community.das_tenant = tenant_a
            community.save()
        for community in three_communities:
            community.das_tenant = tenant_b
            community.save()

        set_current_tenant(tenant_a)

        communities = Community.objects.all()
        assert communities.count() == 2
        assert set(community.id for community in two_communities) == set(communities.values_list("id", flat=True))

    def test_filter_event_categories_by_tenant(self, tenant, das_tenant, one_tenant):
        tenant_a = tenant
        tenant_a_das_tenant = das_tenant
        tenant_b_das_tenant, tenant_b = one_tenant

        set_current_tenant(tenant_a_das_tenant)
        set_tenant_settings(tenant_a)
        for count in enumerate(range(2)):
            EventCategory.objects.create(
                value=f"value_{count}", display=f"value_{count}", das_tenant=tenant_a_das_tenant, ordernum=15
            )

        set_current_tenant(tenant_b_das_tenant)
        set_tenant_settings(tenant_b)
        for count in enumerate(range(2, 4)):
            EventCategory.objects.create(
                value=f"value_{count}", display=f"value_{count}", das_tenant=tenant_b_das_tenant, ordernum=14
            )

        set_current_tenant(tenant_a_das_tenant)
        set_tenant_settings(tenant_a)

        event_categories = EventCategory.objects.all()
        assert event_categories.count() == 3
        assert set(community.id for community in event_categories) == set(event_categories.values_list("id", flat=True))

    @pytest.mark.skip(reason="The TenantModelMixin needs to be inherit into Source and SourceProvider models")
    def test_filter_source_objects_by_tenant(self, five_tenants):
        tenant_a = five_tenants[0]
        tenant_b = five_tenants[1]
        provider1 = SourceProvider.objects.create(das_tenant=tenant_a)
        Source.objects.create(provider=provider1, das_tenant=tenant_a)
        provider2 = SourceProvider.objects.create(das_tenant=tenant_b)
        Source.objects.create(provider=provider2, das_tenant=tenant_b)

        set_current_tenant(tenant_a)

        sources = Source.objects.all()
        assert sources.count() == 1
