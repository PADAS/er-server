import os
import logging

from django.core.management.base import BaseCommand
from django.contrib.auth.models import Permission
from django.db import transaction
import yaml
# Use the C (faster) implementation if possible
try:
    from yaml import CSafeLoader as SafeLoader
    from yaml import CSafeDumper as SafeDumper
except ImportError:
    from yaml import SafeLoader, SafeDumper

from accounts.models import PermissionSet
from observations.models import SubjectGroup

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Create the default permission sets'

    def handle(self, *args, **options):
        if options['reset']:
            raise NotImplementedError('reset not supported yet')

        with transaction.atomic():
            self.add_default_permissionsets()


    def add_arguments(self, parser):
        parser.add_argument('--reset',
                            action='store_true',
                            dest='reset',
                            default=False,
                            help='clear out the existing permission sets prior to creation')

    def default_file(self):
        return os.path.join(os.path.dirname(__file__), 'permissions.yaml')

    def add_default_permissionsets(self, file=None):
        if not file:
            file = self.default_file()
        with open(file) as fp:
            perms = yaml.load(fp, Loader=SafeLoader)

        for ps in perms['permission_sets']:
            permission_set, is_new = PermissionSet.objects.get_or_create(name=ps['name'])
            if is_new:
                permission_set.save()

            for p in ps.get('permissions', []):
                app_label, model, codename = p.split('.')
                try:
                    p = Permission.objects.get(codename=codename, content_type__app_label=app_label,
                                           content_type__model=model)
                except Permission.DoesNotExist:
                    logger.error('Permission does not exist: %s', p)
                permission_set.permissions.add(p)

            if 'parent' in ps:
                permission_set.parent = PermissionSet.objects.get(name=ps['parent'])

            permission_set.save()

        for sg in perms['subjectgroups']:
            subjectgroup, is_new = SubjectGroup.objects.get_or_create(name=sg['name'])
            if is_new:
                subjectgroup.save()

            if 'parent' in sg:
                subjectgroup.parent = SubjectGroup.objects.get(name=sg['parent'])
                                
            for ps in sg.get('ps_sets', []):
                subjectgroup.permission_sets.add(PermissionSet.objects.get(name=ps))
            subjectgroup.save()