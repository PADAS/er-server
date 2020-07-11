from datetime import datetime
import pytz
import shelve

now = datetime.now(tz=pytz.utc)
file_data = shelve.open('celerybeat-schedule')  # file that store the last run times of periodic tasks. 

for task_name, task in file_data['entries'].items():
    if now > task.last_run_at + task.schedule.run_every:
        exit(1)
exit(0)
