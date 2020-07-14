#!/usr/bin/env python
import shelve
import sys
from datetime import datetime

import pytz

now = datetime.now(tz=pytz.utc)
file_data = shelve.open('celerybeat-schedule')  # file that store the last run times of periodic tasks.
for task_name, task in file_data['entries'].items():
    try:
        if now > task.last_run_at + task.schedule.run_every:
            sys.exit(1)
    except Exception:
        pass
sys.exit(0)
