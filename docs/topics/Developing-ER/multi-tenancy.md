# Multi-Tenancy

## Django and Multi-tenancy basics

An EarthRanger Site is referred to as a Tenant in the discussion of multi-tenancy. We utilize the third form of tenancy, shared app and shared schema. One database is used to contain all site data. Each table in the database utilizes a column referred to as the tenant column for the purpose of filtering data to a site.

Besides all of the updates in the DAS codebase to support tenancy, the [django-multitenant](https://github.com/citusdata/django-multitenant) library provides the base models and features to support this shared database form of multi-tenancy.

For more details on coding with multi-tenancy see [Multi-Tenancy Coding Guide](https://allenai.atlassian.net/wiki/spaces/ER/pages/29855973859).

## Tenant Management Service

## Models

When migrating or setting up a new model, we are aware that the tenant needs to be specified in most cases. Only for models that are shared across all tenants, do we not add a foreign key field to DASTenant.

### DASTenant

DASTenant is the special model that defines the partitioning point for Tenant, aka EarthRanger Site, data. This simple table contains the site's tenant_id and last known FQDN for that site. For every site hosted by the MT pipeline, this site will have an entry in the DASTenant table.

### Adding or Updating a Model

Most models include tenant data and as such need to include the foreign key to the DASTenant model.

```python
das_tenant = models.ForeignKey(DASTenant, on_delete=models.CASCADE, blank=True, null=True)
tenant_id = "das_tenant_id"
```

Then in the model class Meta section, we update any existing unique constraints to include the tenant. We prefer to use UniqueConstraint over the soon to be deprecated "unique_together=[]" functionality. Here is an example of a table that previously had a constraint on "name":

```python
constraints = [
    UniqueConstraint(fields=["das_tenant", "name"]),
]
```

Optionally, we specify some indexes for the model. Usually as part of a query performance improvement plan, we add an index. Here are examples of doing that with some common fields. Note that here too we include the tenant since the first part of the query will almost always include the Tenant, then this other field:

```python
indexes = [
    models.Index(fields=["das_tenant", "created_at"]),
    models.Index(fields=["das_tenant", "updated_at"]),
    models.Index(fields=["das_tenant", "event_time"]),
]
```

All Django models have an explicit or silent primary key, provided by you or Django. With the tenant added to a table, we need to manually change the primary key to a composite key. We have a function we call during a migration to use raw SQL to remove the primary key and replace with our composite key. Another function is used to backfill the new das_tenant_id column with the proper tenant_id. This can be tricky in the future if there is existing data and more than one tenant exists in the db.

## Issues with Tenants in models

### Composite Primary Key

Ideally Django would support a composite primary key like tenant+id. As of now, Django only supports a single column primary key. Django-multitenant suggests just ignoring that and making our composite primary through a custom migration. This in support of the citus database which needs a way to shard data, tenant being that sharding key. This actually works but breaks when we go to make an aggregate query or any Group By query. Django relies on the feature [recognize functional dependency on primary keys](https://www.postgresql.org/message-id/20100807024409.35E3A7541D7@cvs.postgresql.org) in PostgreSQL to assume when you group by on a table with a single primary key, PostgreSQL understands to include all columns found in the Select clause silently in the group by clause. For a composite primary key to really work, Django would need to insert (tenant+id) as a composite Group by Column. Instead, we see this for example:

```
ERROR: column "event.created_at" must appear in the GROUP BY clause or be used in an aggregate function
```

Here is [StackOverflow](https://stackoverflow.com/questions/75561225/changing-primary-key-index-breaks-group-by-in-postgresql) talking about the issue.

**Workarounds:**

1. When using Group By, manually add any non aggregate columns from the Select clause to the Group By clause, since Django won't do that for us.
2. There is a global database engine override, which when set to False, Django will add the Group By references per (1): `allows_group_by_selected_pks` (see django-multitenant [base.py](https://github.com/citusdata/django-multitenant/blob/fd84aeee9f71f66775a5f4256102f9010418a940/django_multitenant/backends/postgresql/base.py#L126))
3. Manually add the composite primary key to the Group By clause.

## Dependencies

[django-multitenant](https://github.com/citusdata/django-multitenant) - besides basic tests before upgrading this library, we forked their backends/postgresql Django db engine code to support postgis. This requires us to manage any changes in their [implementation](https://github.com/citusdata/django-multitenant/blob/main/django_multitenant/backends/postgresql/base.py) with our forked version.
