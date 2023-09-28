import os
import warnings

from django_multitenant.utils import get_current_tenant

from django.conf import settings
from django.core import serializers
from django.core.management.base import CommandError
from django.core.management.commands.loaddata import Command as LoadDataCommand
from django.db import DatabaseError, IntegrityError, router

from core.utils import DASTenantManagement
from utils.tenant.commands import TenantCommandMixin


class Command(TenantCommandMixin, LoadDataCommand):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.das_tenant = get_current_tenant()
        if self.das_tenant is None:
            self.das_tenant = DASTenantManagement(domain=settings.SERVER_FQDN).get_or_create_tenant()

    def load_label(self, fixture_label):
        """Load fixtures files for a given label."""
        show_progress = self.verbosity >= 3
        for fixture_file, fixture_dir, fixture_name in self.find_fixtures(fixture_label):
            _, ser_fmt, cmp_fmt = self.parse_name(os.path.basename(fixture_file))
            open_method, mode = self.compression_formats[cmp_fmt]
            fixture = open_method(fixture_file, mode)
            try:
                self.fixture_count += 1
                objects_in_fixture = 0
                loaded_objects_in_fixture = 0
                if self.verbosity >= 2:
                    self.stdout.write(
                        "Installing %s fixture '%s' from %s." % (ser_fmt, fixture_name, humanize(fixture_dir))
                    )

                objects = serializers.deserialize(
                    ser_fmt,
                    fixture,
                    using=self.using,
                    ignorenonexistent=self.ignore,
                    handle_forward_references=True,
                )

                for obj in objects:
                    objects_in_fixture += 1
                    if obj.object._meta.app_config in self.excluded_apps or type(obj.object) in self.excluded_models:
                        continue
                    if router.allow_migrate_model(self.using, obj.object.__class__):
                        loaded_objects_in_fixture += 1
                        self.models.add(obj.object.__class__)
                        try:
                            if hasattr(obj.object, "das_tenant"):
                                obj.object.das_tenant = self.das_tenant
                            obj.save(using=self.using)
                            if show_progress:
                                self.stdout.write("\rProcessed %i object(s)." % loaded_objects_in_fixture, ending="")
                        # psycopg2 raises ValueError if data contains NUL chars.
                        except (DatabaseError, IntegrityError, ValueError) as e:
                            e.args = (
                                "Could not load %(object_label)s(pk=%(pk)s): %(error_msg)s"
                                % {
                                    "object_label": obj.object._meta.label,
                                    "pk": obj.object.pk,
                                    "error_msg": e,
                                },
                            )
                            raise
                    if obj.deferred_fields:
                        self.objs_with_deferred_fields.append(obj)
                if objects and show_progress:
                    self.stdout.write()  # Add a newline after progress indicator.
                self.loaded_object_count += loaded_objects_in_fixture
                self.fixture_object_count += objects_in_fixture
            except Exception as e:
                if not isinstance(e, CommandError):
                    e.args = ("Problem installing fixture '%s': %s" % (fixture_file, e),)
                raise
            finally:
                fixture.close()

            # Warn if the fixture we loaded contains 0 objects.
            if objects_in_fixture == 0:
                warnings.warn(
                    "No fixture data found for '%s'. (File format may be " "invalid.)" % fixture_name, RuntimeWarning
                )


def humanize(dirname):
    return "'%s'" % dirname if dirname else "absolute path"
