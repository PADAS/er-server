from importlib import import_module

from django.test import TestCase

from das_server import celery


class CeleryConfigurationTests(TestCase):

    def test_importing_all_scheduled_tasks(self):
        '''
        Validate function references in beat_schedule Entries.
        '''
        bad_references = []
        for k, v in celery.app.conf.beat_schedule.items():
            try:
                elems = v['task'].split('.')
                module = '.'.join(elems[:-1])
                func = elems[-1]
                modl = import_module(module)

                if not hasattr(modl, func):
                    raise ValueError('bad function reference')

            except (ImportError, ValueError):
                bad_references.append((k, v))

        self.assertTrue(len(bad_references) == 0,
                        msg=f'These are bad celerybeat schedule entries: {bad_references}')
