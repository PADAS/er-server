from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor, ProcessPoolExecutor
from pytz import utc

jobstores = {
    # 'redis': RedisJobStore(host='soa.here', db=12),
    'default': SQLAlchemyJobStore(url='postgres://postgres:postgres@soa.here:5432/dasdb'),
}



executors = {
    'default': ThreadPoolExecutor(20),
    'processpool': ProcessPoolExecutor(5)
}

job_defaults = {
    'coalesce': False,
    'max_instances': 3
}

scheduler = BackgroundScheduler(jobstores=jobstores, executors=executors, job_defaults=job_defaults, timezone=utc)

scheduler.start()

from data_input import jobs

job_details = scheduler.get_job('savanna_import')

if not job_details:
    job_details = scheduler.add_job(jobs.run_savanna, 'interval', minutes=30, id='savanna_import')

print(job_details)

def __shutdown_scheduler(scheduler):
    print("Shutting down job scheduler...")
    scheduler.shutdown()

import atexit

atexit.register(__shutdown_scheduler, scheduler)
