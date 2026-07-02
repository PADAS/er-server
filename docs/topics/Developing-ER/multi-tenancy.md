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

## Interacting with models across tenants in code

Outside an HTTP request there is **no tenant in the thread-local context**. Middleware sets it per request (`set_tenant_by_request`), but data migrations, management commands, Celery tasks, and `manage.py shell` sessions all start with no tenant set. django-multitenant only injects the `das_tenant_id` predicate into a query — **including the implicit `WHERE` clause of a write** — when a tenant is set in the current thread. So when you iterate over tenants and touch models in a loop, how you manage that context decides whether your reads *and writes* stay inside a single tenant.

Use the context managers in [`utils/tenant/managers.py`](../../../das/utils/tenant/managers.py). Prefer a `with` block over the bare `set_tenant*` helpers so the previous context is always restored on exit.

### `TenantContextManager(domain=...)` — scope reads AND writes to one tenant

This is the pattern for updating models across multiple tenants. It sets the current tenant (and tenant settings) on enter and restores the previous context on exit. While it is active, the ORM automatically scopes every query and every `save()` / `update()` to that tenant:

```python
from core.models import DASTenant
from utils.tenant.managers import TenantContextManager

for tenant in DASTenant.objects.all():
    with TenantContextManager(domain=tenant.domain):
        for event_type in EventType.objects.filter(version="2"):        # read scoped to this tenant
            event_type.schema = repair(event_type.schema)
            event_type.save(update_fields=["schema", "updated_at"])      # UPDATE ... WHERE id=%s AND das_tenant_id=%s
```

Because the tenant is set, the `save()` above emits `UPDATE ... WHERE id=<uuid> AND das_tenant_id=<tenant>` — it touches only that tenant's row.

### `UnsetDASTenantContextManager()` — remove scoping (reads only)

`UnsetDASTenantContextManager` does the opposite: it clears the current tenant so you can read across all tenants (e.g. to list every `DASTenant`, or to fetch rows regardless of tenant). It is a **read** tool.

> ⚠️ **Never issue a write inside `UnsetDASTenantContextManager` on a tenant-scoped model.** With no tenant set, `instance.save()` / `QuerySet.update()` key the write on the Django primary key (`id`) alone. Seeded/global rows such as `EventType`, `EventCategory`, `EventClass`, and `TileLayer` **reuse the same `id` across every tenant** (see [Composite Primary Key](#composite-primary-key)), so the emitted `UPDATE ... WHERE id=<uuid>` has no tenant predicate and **overwrites every tenant's row that shares that id**. This is a real incident: migrations `0198_fix_v2_link_fields` and `0203_repair_v2_collection_schemas` clobbered V2 `EventType` schemas across every tenant on both production clusters this way (2026-06-29). Scoping the *read* with `.filter(das_tenant_id=...)` does **not** protect the write — the danger is entirely in the write's implicit `WHERE`.

If for some reason you must write while iterating without setting context, name the tenant in the write yourself instead of relying on `save()`:

```python
# Safe even with no tenant set — the tenant is in the WHERE clause:
EventType.objects.filter(id=event_type.id, das_tenant_id=tenant.id).update(schema=new_schema)
# ...or raw SQL: UPDATE activity_eventtype SET schema = %s WHERE id = %s AND das_tenant_id = %s
```

But prefer `TenantContextManager` — it keeps both reads and writes scoped with no manual predicate to forget.

### Setting context without a block

`utils/tenant/managers.py` also exposes `set_tenant(domain)`, `set_tenant_by_request(request)`, and `set_tenant_data(dict)` for setting context imperatively (e.g. at the top of a Celery task, which must accept the tenant identifier as an explicit argument and re-enter context inside the task body). When the scope is a block of code, prefer the context managers so cleanup is automatic.

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
