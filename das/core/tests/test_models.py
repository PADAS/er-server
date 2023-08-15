import pytest
from django_multitenant.utils import set_current_tenant

from activity.models import Community
from observations.models import Source, SourceProvider


@pytest.mark.django_db
class TestDASTenant:
    @pytest.mark.skip(reason="The TenantModelMixin needs to be inherit into Community model")
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
