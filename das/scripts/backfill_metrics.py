# backfill-metrics
import datetime
import logging

import dateutil.parser

from django.core.management import call_command

logger = logging.getLogger(__name__)

def run(start, end=None):
    logger.info("backfill_metrics")

    start_date = dateutil.parser.parse(start)
    if not start_date.tzinfo:
        start_date = start_date.replace(tzinfo=datetime.timezone.utc)
    end_date = datetime.datetime.now(datetime.timezone.utc)
    if end:
        end_date = dateutil.parser.parse(end)
        if not end_date.tzinfo:
            end_date = end_date.replace(tzinfo=datetime.timezone.utc)

    incr = datetime.timedelta(days=1)
    day = start_date
    while day < end_date:
        call_command("site_metrics", start=day.isoformat())
        day = day + incr


