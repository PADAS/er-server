from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

import pytz
from data_input.jobs import *
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

def heartbeat():
    logger.info('beat')

def add_scheduled_jobs(scheduler):
    '''
    Add jobs to schedule.
    '''
    scheduler.add_job(run_savanna, id='savanna_import', trigger='cron', minute='*/17', replace_existing=True)
    scheduler.add_job(run_firms, id='firms_import', trigger='cron', minute='*/99', replace_existing=True)
    scheduler.add_job(run_inreach, id='inreach_import', trigger='cron', minute='*/13', replace_existing=True)
    scheduler.add_job(heartbeat, id='heartbeat', trigger='cron', minute='*/10', replace_existing=True)

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
    logger.info('Starting scheduler...')
    scheduler.start()
    logger.info('Scheduler started.')

    def __shutdown_scheduler(scheduler):
        logger.info('Shutting down job scheduler...')
        scheduler.shutdown()

    import atexit

    atexit.register(__shutdown_scheduler, scheduler)

    add_scheduled_jobs(scheduler)

# start_scheduler()
