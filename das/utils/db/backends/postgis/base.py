import logging

import django
from django.contrib.gis.db.backends.postgis.base import (
    DatabaseWrapper as PostGISDatabaseWrapper,
)
from django.contrib.gis.db.backends.postgis.features import (
    DatabaseFeatures as PostGISDatabaseFeatures,
)
from django.contrib.gis.db.backends.postgis.schema import PostGISSchemaEditor
from django.db.backends.base.base import NO_DB_ALIAS

logger = logging.getLogger(__name__)


class DatabaseSchemaEditor(PostGISSchemaEditor):
    """
    the following code has been disabled as it causes problems with our migrations.
    We would need to spend more time to understand why it is needed and how to fix it.
    """


# noqa
class TenantDatabaseFeatures(PostGISDatabaseFeatures):
    """
    This class is crucial for DAS to work properly with compoiste primary keys at the db level.
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
    # SchemaEditorClass = DatabaseSchemaEditor
    features_class = TenantDatabaseFeatures

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if kwargs.get("alias", "") != NO_DB_ALIAS:
            self.features = TenantDatabaseFeatures(self)
