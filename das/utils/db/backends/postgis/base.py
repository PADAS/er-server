import logging

from django_multitenant.utils import get_model_by_db_table, get_tenant_column

import django
from django.contrib.gis.db.backends.postgis.base import (
    DatabaseWrapper as PostGISDatabaseWrapper,
)
from django.contrib.gis.db.backends.postgis.features import (
    DatabaseFeatures as PostGISDatabaseFeatures,
)
from django.contrib.gis.db.backends.postgis.schema import PostGISSchemaEditor
from django.db.backends.base.base import NO_DB_ALIAS

from core.fields import CompoundTenantForeignKey

logger = logging.getLogger(__name__)


class DatabaseSchemaEditor(PostGISSchemaEditor):
    """
    the following code has been disabled as it causes problems with our migrations.
    We would need to spend more time to understand why it is needed and how to fix it.
    """

    sql_create_column_inline_fk = None

    # pylint: disable=too-many-arguments
    def _alter_field(
        self,
        model,
        old_field,
        new_field,
        old_type,
        new_type,
        old_db_params,
        new_db_params,
        strict=False,
    ):
        """
        If there is a change in the field, this method assures that if the field is type of CompoundTenantForeignKey
        and db_constraint does not exist, adds the foreign key constraint.
        """

        super()._alter_field(
            model,
            old_field,
            new_field,
            old_type,
            new_type,
            old_db_params,
            new_db_params,
            strict,
        )

        # If the pkey was dropped in the previous distribute migration,
        # foreign key constraints didn't previously exists so django does not
        # recreated them.
        # Here we test if we are in this case
        if isinstance(new_field, CompoundTenantForeignKey) and new_field.db_constraint:
            from_model = get_model_by_db_table(model._meta.db_table)
            fk_names = self._constraint_names(model, [new_field.column], foreign_key=True) + self._constraint_names(
                model,
                [get_tenant_column(from_model), new_field.column],
                foreign_key=True,
            )
            if not fk_names:
                self.execute(self._create_fk_sql(model, new_field, "_fk_%(to_table)s_%(to_column)s"))

    # Override
    def _create_fk_sql(self, model, field, suffix):
        """
        This method overrides the additions foreign key constraint sql and adds the tenant column to the constraint
        """
        if isinstance(field, CompoundTenantForeignKey):
            try:
                # test if both models exists
                # This case happens when we are running from scratch migrations and one model was removed from code
                # In the previous migrations we would still be creating the foreign key
                from_model = get_model_by_db_table(model._meta.db_table)
                to_model = get_model_by_db_table(field.target_field.model._meta.db_table)
            except ValueError:
                return None

            from_columns = get_tenant_column(from_model), field.column
            to_columns = get_tenant_column(to_model), field.target_field.column
            suffix = suffix % {
                "to_table": field.target_field.model._meta.db_table,
                "to_column": "_".join(to_columns),
            }

            return self.sql_create_fk % {
                "table": self.quote_name(model._meta.db_table),
                "name": self.quote_name(self._create_index_name(model._meta.db_table, from_columns, suffix=suffix)),
                "column": ", ".join([self.quote_name(from_col) for from_col in from_columns]),
                "to_table": self.quote_name(field.target_field.model._meta.db_table),
                "to_column": ", ".join([self.quote_name(to_col) for to_col in to_columns]),
                "deferrable": self.connection.ops.deferrable_sql(),
            }
        return super()._create_fk_sql(model, field, suffix)


# noqa
class TenantDatabaseFeatures(PostGISDatabaseFeatures):
    """
    This class is crucial for DAS to work properly with composite primary keys at the db level.
    Without it, django and postgresql make assumptions on default Group By behavour that are not compatible with
    composite primary keys.
    """

    # The default Django behaviour is to collapse the fields to just the 'id'
    # field. This doesn't work because we're using a composite primary key. In
    # Django version 3.0 a function was added that we can override to specify
    # for specific models that this behaviour should be disabled.
    def allows_group_by_selected_pks_on_model(self, model):
        # pylint: disable=import-outside-toplevel
        from django_multitenant.mixins import TenantModelMixin
        from django_multitenant.models import TenantModel

        if issubclass(model, (TenantModel, TenantModelMixin)):
            return False
        return super().allows_group_by_selected_pks_on_model(model)

    # For django versions before version 3.0 we set a flag that disables this
    # behaviour for all models.
    if django.VERSION < (3, 0):
        allows_group_by_selected_pks = False


class DatabaseWrapper(PostGISDatabaseWrapper):
    # Override
    SchemaEditorClass = DatabaseSchemaEditor
    features_class = TenantDatabaseFeatures

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if kwargs.get("alias", "") != NO_DB_ALIAS:
            self.features = TenantDatabaseFeatures(self)
