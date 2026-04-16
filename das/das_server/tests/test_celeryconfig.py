from importlib import import_module

from celery import current_app

from django.test import TestCase

from das_server import celery
from das_server.celery import app as celery_app


class CeleryConfigurationTests(TestCase):
    def test_importing_all_scheduled_tasks(self):
        """
        Validate function references in beat_schedule Entries.
        """
        bad_references = []
        for k, v in celery.app.conf.beat_schedule.items():
            try:
                elems = v["task"].split(".")
                module = ".".join(elems[:-1])
                func = elems[-1]
                modl = import_module(module)

                if not hasattr(modl, func):
                    raise ValueError("bad function reference")

            except (ImportError, ValueError):
                bad_references.append((k, v))

        self.assertTrue(len(bad_references) == 0, msg=f"These are bad celerybeat schedule entries: {bad_references}")

    def test_task_name_used_are_registered_task(self):
        task_names = [
            "activity.tasks.automatically_update_event_state",
            "activity.tasks.evaluate_alert_rules",
            "activity.tasks.maintain_patrol_state",
            "activity.tasks.periodically_maintain_patrol_state",
            "activity.tasks.recreate_event_details_view",
            "activity.tasks.refresh_event_details_view",
            "activity.tasks.send_alert_to_notificationmethod",
            "activity.tasks.warm_eventphotos",
            "analyzers.tasks.analyze_subject",
            "analyzers.tasks.download_gfw_alerts",
            "analyzers.tasks.handle_observation",
            "analyzers.tasks.handle_source",
            "analyzers.tasks.handle_subject",
            "das_server.celery.debug_task",
            "das_server.tasks.celerybeat_pulse",
            "mapping.tasks.automate_download_features_from_wfs",
            "mapping.tasks.load_features_from_wfs",
            "mapping.tasks.load_spatial_features_from_files",
            "observations.tasks.handle_outbox_message",
            "observations.tasks.maintain_observation_data",
            "observations.tasks.maintain_subjectstatus_all",
            "observations.tasks.maintain_subjectstatus_for_subject",
            "observations.tasks.poll_news_gcs_bucket",
            "observations.tasks.process_gpxdata_api",
            "observations.tasks.process_gpxtrack_file",
            "observations.tasks.refresh_patrols_view",
            "reports.observationlagnotification.check_sources_threshold",
            "reports.tasks.alert_lag_delay",
            "reports.tasks.run_check_sources_threshold",
            "reports.tasks.subjectsource_report",
            "rt_api.tasks.broadcast_service_status_tenant",
            "rt_api.tasks.broadcast_service_status",
            "rt_api.tasks.check_redis_queues",
            "rt_api.tasks.handle_delete_event",
            "rt_api.tasks.handle_delete_message",
            "rt_api.tasks.handle_delete_patrol",
            "rt_api.tasks.handle_emit_data",
            "rt_api.tasks.handle_new_announcement",
            "rt_api.tasks.handle_new_event",
            "rt_api.tasks.handle_new_message",
            "rt_api.tasks.handle_new_patrol",
            "rt_api.tasks.handle_new_subject_observation",
            "rt_api.tasks.handle_subjectstatus_update",
            "rt_api.tasks.handle_update_event",
            "rt_api.tasks.handle_update_message",
            "rt_api.tasks.handle_update_patrol",
            "tracking.tasks.run_firms_plugin",
            "tracking.tasks.run_plugin_class",
            "tracking.tasks.run_plugins",
            "tracking.tasks.run_source_plugin",
            "tracking.tasks.schedule_firms_plugins",
            "usercontent.tasks.warm_imagefilecontent",
            "utils.auth0.tasks.refresh_cached_auth0_jwks",
        ]

        current_app.loader.import_default_modules()
        registered_tasks = list(sorted(name for name in current_app.tasks if not name.startswith("celery.")))

        for task_name in task_names:
            assert task_name in registered_tasks

    def test_all_scheduled_tasks_are_discoverable_via_autodiscovery(self):
        """
        Test that all tasks referenced in beat_schedule can be discovered through autodiscovery.

        This test ensures that the autodiscovery configuration includes all modules
        that contain scheduled tasks. Without proper autodiscovery, tasks would fail
        with "unregistered task" errors at runtime.
        """
        scheduled_task_names = []
        for schedule_entry in celery_app.conf.beat_schedule.values():
            scheduled_task_names.append(schedule_entry["task"])

        celery_app.loader.import_default_modules()

        unregistered_tasks = []
        for task_name in scheduled_task_names:
            if task_name not in celery_app.tasks:
                unregistered_tasks.append(task_name)

        self.assertEqual(
            [],
            unregistered_tasks,
            f"These scheduled tasks would cause 'Received unregistered task' errors: {unregistered_tasks}. "
            f"Check that their modules are included in autodiscover_tasks() calls in celery.py.",
        )
