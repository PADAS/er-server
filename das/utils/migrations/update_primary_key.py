import logging

from django.apps import apps
from django.db import connection
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)

EDGE_CASE_TABLES = ["observations_usersession", "observations_socketclient"]
SOURCE_CASE_TABLES = ["observations_latestobservationsource"]
VALUE_CASE_TABLES = ["observations_subjecttype", "observations_subjectsubtype", "observations_commonname"]


def add_tenant_to_primary_key(app: str, models: []):
    query_manager = QueryManager()
    apps_handler = DjangoAppsHandler(query_manager=query_manager)
    apps_handler.handle(app=app, models=models)


def drop_constraint(app: str, model: str, constraint: str, cascade: bool = False):
    query_manager = QueryManager()
    apps_handler = AppsHandler(query_manager=query_manager)
    apps_handler.handle_constraints(app=app, model=model, constraint=constraint, cascade=cascade)


class QueryManager:
    def regenerate_primary_key(self, table):
        primary_key = self._get_primary_key(table)
        new_primary_key = f"{table}_pkey"
        self._drop_primary_key(table, primary_key)
        self._create_primary_key(table, new_primary_key)

    def drop_constraint(self, table: str, constraint: str, cascade: bool = False):
        self._drop_constraint(table=table, constraint=constraint, cascade=cascade)

    def _get_primary_key(self, table: str) -> str:
        with connection.cursor() as cursor:
            pk_table_query = (
                f"SELECT conname FROM pg_constraint WHERE conrelid = '{table}'::regclass AND contype = 'p';"
            )
            cursor.execute(pk_table_query)
            primary_key_result = cursor.fetchone()
            return primary_key_result[0]

    def _drop_primary_key(self, table: str, primary_key: str):
        drop_pk_query = f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {primary_key} CASCADE;"
        with connection.cursor() as cursor:
            cursor.execute(drop_pk_query)

    def _create_primary_key(self, table: str, primary_key: str):
        create_pk_query = f"ALTER TABLE {table} ADD CONSTRAINT {primary_key} PRIMARY KEY (das_tenant_id, id);"
        if table in EDGE_CASE_TABLES:
            create_pk_query = f"ALTER TABLE {table} ADD CONSTRAINT {primary_key} PRIMARY KEY (das_tenant_id, sid);"
        elif table in VALUE_CASE_TABLES:
            create_pk_query = f"ALTER TABLE {table} ADD CONSTRAINT {primary_key} PRIMARY KEY (das_tenant_id, value);"
        elif table in SOURCE_CASE_TABLES:
            create_pk_query = (
                f"ALTER TABLE {table} ADD CONSTRAINT {primary_key} PRIMARY KEY (das_tenant_id, source_id);"
            )
        with connection.cursor() as cursor:
            cursor.execute(create_pk_query)

    def _drop_constraint(self, table: str, constraint: str, cascade: bool = False):
        drop_constraint_query = (
            f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {constraint} {'CASCADE' if cascade else ''};"
        )
        with connection.cursor() as cursor:
            cursor.execute(drop_constraint_query)


class AppsHandler:
    def __init__(self, query_manager):
        self.query_manager = query_manager

    def handle(self, app: str, models=None):
        if not models:
            models = []
        for table in self._get_table_names(app=app, models=models):
            logger.info("Regenerating primary key of table %s" % table)
            self.query_manager.regenerate_primary_key(table)

    def handle_constraints(self, app: str, model: str, constraint: str, cascade: bool = False):
        model = self._get_model(app=app, model=model)
        table = self._get_model_table_name(model=model)
        logger.info("Dropping constraint %s of table %s" % (constraint, table))
        self.query_manager.drop_constraint(table=table, constraint=constraint, cascade=cascade)

    def _get_table_names(self, app: str, models):
        models_path = [f"{app}.models.{model}" for model in models]
        tables = set()
        for model in self._get_apps_model(models_path=models_path):
            tables.add(self._get_model_table_name(model=model))
        return tables

    def _get_apps_model(self, models_path=None):
        if not models_path:
            models_path = []
        return [import_string(model_path) for model_path in models_path]

    def _get_model(self, app: str, model: str):
        model_path = f"{app}.models.{model}"
        return import_string(model_path)

    def _get_model_table_name(self, model) -> str:
        return model.objects.model._meta.db_table


class DjangoAppsHandler(AppsHandler):
    def _get_table_names(self, app: str, models):
        for model in models:
            yield apps.get_model(app, model)._meta.db_table
