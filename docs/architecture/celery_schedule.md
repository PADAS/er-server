# Celery Schedule - Daily Task Execution

This document outlines the scheduled tasks in the DAS system organized by hour of the day.

## Hour-by-Hour Schedule

### 12:00 AM (00:00)
- **set_alert_counter_for_all_users** - Resets alert counter for all users
  - Task: `activity.tasks.reset_alert_counter_for_all_users`
  - Schedule: Daily at midnight

### 2:00 AM
- **download-features-from-wfs** - Downloads features from Web Feature Service
  - Task: `mapping.tasks.automate_download_features_from_wfs`
  - Schedule: Daily at 2:00 AM

### 4:00 AM
- **routine-delete-observational-data** - Maintains observation data (cleanup)
  - Task: `observations.tasks.maintain_observation_data`
  - Schedule: Daily at 4:00 AM

### 6:00 AM
- **reports** - Generates subject/source reports
  - Task: `reports.tasks.subjectsource_report`
  - Schedule: Daily at 6:00 AM

### Every Hour
- **check-sources-threshold** - Checks sources threshold
  - Task: `reports.tasks.run_check_sources_threshold`
  - Schedule: Every hour

- **refresh_tenants_cache** - Refreshes tenants cache
  - Task: `das_server.tasks.refresh_tenants_cache`
  - Schedule: Every hour

### Every 15 Minutes
- **firms-plugins** - Schedules FIRMS plugins
  - Task: `tracking.tasks.schedule_firms_plugins`
  - Schedule: Every 15 minutes

- **poll_news_gcs_bucket** - Polls news GCS bucket
  - Task: `observations.tasks.poll_news_gcs_bucket`
  - Schedule: Every 15 minutes

### Every 5 Minutes
- **plugins** - Runs tracking plugins
  - Task: `tracking.tasks.run_plugins`
  - Schedule: Every 5 minutes

- **auto-resolve** - Automatically updates event state
  - Task: `activity.tasks.automatically_update_event_state`
  - Schedule: Every 5 minutes

### Every 30 Minutes
- **observation-lag-report** - Reports on observation lag delays
  - Task: `reports.tasks.alert_lag_delay`
  - Schedule: Every 30 minutes

### Every Minute
- **periodically_maintain_patrol_state** - Maintains patrol state
  - Task: `activity.tasks.periodically_maintain_patrol_state`
  - Schedule: Every minute

### Every 60 Seconds
- **beat-pulse** - Celery beat pulse routine
  - Task: `das_server.tasks.celerybeat_pulse`
  - Schedule: Every 60 seconds

### Every 15 Seconds
- **service-status** - Broadcasts service status
  - Task: `rt_api.tasks.broadcast_service_status`
  - Schedule: Every 15 seconds

### Every 60 Seconds
- **redis-status** - Checks Redis queues
  - Task: `rt_api.tasks.check_redis_queues`
  - Schedule: Every 60 seconds

### Every 12 Hours
- **subject-status-maintenance** - Maintains subject status for all subjects
  - Task: `observations.tasks.maintain_subjectstatus_all`
  - Schedule: Every 12 hours

### Weekly (Monday at 12:00 AM)
- **postgresql_partman_run_partition_table_check_for_observations_observation** - Runs partition table check for observations
  - Task: `observations.tasks.run_partition_table_check`
  - Schedule: Every Monday at midnight

### Weekly (Monday at 1:00 AM)
- **postgresql_partman_run_partition_table_check_for_observations_observationsegment** - Runs partition table check for observation segments
  - Task: `observations.tasks.run_observation_segment_partition_table_check`
  - Schedule: Every Monday at 2:00 AM (aligned with recommended time for `partman.run_maintenance_proc()` for 3-year retention)

The system uses different queues to manage task priorities:

- **realtime_p1**: High-priority real-time tasks
- **realtime_p2**: Medium-priority real-time tasks
- **realtime_p3**: Lower-priority real-time tasks
- **maintenance**: System maintenance tasks
- **analyzers**: Analysis and processing tasks

## Notes

- All times are based on the system's configured timezone (`settings.TIME_ZONE`)
- Tasks with `timedelta` schedules run continuously at the specified intervals
- Tasks with `crontab` schedules run at specific times on specific days
- The `PLUGINS_INTERVAL` is set to 5 minutes (300 seconds) for plugin execution
- High-frequency tasks like service status and Redis checks ensure system health monitoring
- **Partition maintenance:** For `observations_observationsegment`, `partman.run_maintenance_proc()` (e.g. via management command or pg_partman BGW) should run at least weekly (e.g. Monday 02:00 UTC) so that future monthly partitions are created and partitions older than 3 years are dropped per retention config. See `docs/development/observation-segment-partitioning-plan.md`.
