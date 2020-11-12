import re
import inspect
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

    @staticmethod
    def get_task_names(funcs):
        task_names = []
        for func in funcs:
            rm_indent = re.sub(r'(^[ \t]+|[ \t]+(?=:))', '', inspect.getsource(func), flags=re.M).replace('\n', '')
            code_lines = re.findall(r'\bcelery\.\w+\.\w+\(.*?\)', rm_indent, re.M)

            for i in code_lines:
                split_by_braces = re.findall("\((.*?)\)", i)[0].split(',')[0]
                name = split_by_braces.replace("'", '')
                task_names.append(name)
        return task_names

    def test_task_name_used_are_registered_task(self):
        from rt_api.pubsub_listener import start
        from analyzers.pubsub_registry import new_observations_callback
        from analyzers.gfw_inbound import process_alert_for_subscription
        from observations.servicesutils import store_service_status
        from usercontent.signals import warm_imagefile_content_image
        from activity.signals import event_post_save, warm_EventPhoto_image

        functions = [start, new_observations_callback, process_alert_for_subscription, store_service_status,
                     warm_imagefile_content_image, event_post_save, warm_EventPhoto_image]

        registered_tasks = celery.app.tasks
        task_names = self.get_task_names(functions)

        bad_reference = []
        for i in task_names:
            try:
                registered_tasks[i]
            except KeyError:
                bad_reference.append(i)
        self.assertTrue(len(bad_reference) == 0, msg=f'The following are unregistered task names: {bad_reference}')

