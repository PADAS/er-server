from importlib import import_module

from celery import current_app

from django.test import TestCase

from das_server import celery


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
            "activity.tasks.refresh_event_details_view_task",
            "activity.tasks.send_alert_to_notificationmethod",
            "activity.tasks.update_status_of_event_details_view_refresh",
            "activity.tasks.warm_eventphotos",
            "analyzers.tasks.analyze_subject",
            "analyzers.tasks.annotate_observations_for_subject",
            "analyzers.tasks.download_gfw_alerts",
            "analyzers.tasks.handle_observation",
            "analyzers.tasks.handle_source",
            "analyzers.tasks.handle_subject",
            "das_server.celery.debug_task",
            "das_server.tasks.celerybeat_pulse",
            "das_server.tasks.publish_daily_site_metrics",
            "mapping.tasks.automate_download_features_from_wfs",
            "mapping.tasks.load_features_from_wfs",
            "mapping.tasks.load_spatial_features_from_files",
            "observations.tasks._refresh_patrols_view",
            "observations.tasks.handle_outbox_message",
            "observations.tasks.maintain_observation_data",
            "observations.tasks.maintain_subjectstatus_all",
            "observations.tasks.maintain_subjectstatus_for_subject",
            "observations.tasks.poll_news_gcs_bucket",
            "observations.tasks.process_gpxdata_api",
            "observations.tasks.process_gpxtrack_file",
            "observations.tasks.refresh_patrols_view",
            "observations.tasks.store_and_forward_service_status",
            "reports.observationlagnotification.check_sources_threshold",
            "reports.tasks.alert_lag_delay",
            "reports.tasks.run_check_sources_threshold",
            "reports.tasks.subjectsource_report",
            "rt_api.tasks._broadcast_service_status",
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
            "tracking.tasks.run_awetelementry_plugins",
            "tracking.tasks.run_demo_plugins",
            "tracking.tasks.run_firms_plugin",
            "tracking.tasks.run_inreach_plugins",
            "tracking.tasks.run_inreachkml_plugins",
            "tracking.tasks.run_plugin_class",
            "tracking.tasks.run_plugins",
            "tracking.tasks.run_sirtrack_plugins",
            "tracking.tasks.run_source_plugin",
            "tracking.tasks.run_spidertracks_plugins",
            "tracking.tasks.schedule_firms_plugins",
            "usercontent.tasks.warm_imagefilecontent",
        ]

        current_app.loader.import_default_modules()
        registered_tasks = list(sorted(name for name in current_app.tasks if not name.startswith("celery.")))

        for task_name in task_names:
            assert task_name in registered_tasks
