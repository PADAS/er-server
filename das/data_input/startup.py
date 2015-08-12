from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

import pytz
from data_input.jobs import run_savanna
from django.conf import settings

def add_scheduled_jobs(scheduler):
    '''
    Add jobs to schedule.
    '''
    job = scheduler.add_job(run_savanna, 'interval', minutes=15, id='savanna_import', replace_existing=True)
    print('Added savanna_import job %s' % job)


def start_scheduler():
    '''
    Start scheduler for executing background tasks (ex. importing collar data.)
    :return:
    '''
    jobstores = {
        'default': SQLAlchemyJobStore(url=settings.SCHEDULER['db_url']),
    }
    executors = settings.SCHEDULER['executors']
    job_defaults = settings.SCHEDULER['job_defaults']

    scheduler = BackgroundScheduler(jobstores=jobstores, executors=executors, job_defaults=job_defaults,
                                    timezone=pytz.utc)


    print("Starting scheduler...")
    scheduler.start()
    print("Scheduler started.")

    def __shutdown_scheduler(scheduler):
        print("Shutting down job scheduler...")
        scheduler.shutdown()

    import atexit

    atexit.register(__shutdown_scheduler, scheduler)

    add_scheduled_jobs(scheduler)

start_scheduler()
