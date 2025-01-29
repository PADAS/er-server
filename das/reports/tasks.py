import logging
import random
from datetime import timedelta
from smtplib import SMTPSenderRefused, SMTPServerDisconnected

from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _

from das_server import celery
from reports.distribution import (
    SOURCE_REPORT_PERMISSION_CODENAME,
    get_users_for_permission,
    send_report,
)
from reports.observationlagnotification import (
    check_sources_threshold,
    get_lagging_providers,
    send_lag_delay_alert,
)
from reports.subjectsourcereport import generate_user_reports
from utils.tenant.celery import OverAllTenantTask, TenantQueueOnceTask

logger = logging.getLogger(__name__)


@celery.app.task(base=OverAllTenantTask, bind=True, once={"graceful": True})
def subjectsource_report(self, usernames=None):
    if usernames:
        raise ValueError("The usernames argument is not supported for this task.")

    delay_in_seconds = random.randint(1, 60)
    subjectsource_report_for_tenant.apply_async(eta=timedelta(seconds=delay_in_seconds))


@celery.app.task(
    base=TenantQueueOnceTask,
    bind=True,
    once={
        "graceful": True,
    },
)
def subjectsource_report_for_tenant(self, usernames=None):
    # Limit recipients to those identified by usernames argument.
    recipients = get_users_for_permission(SOURCE_REPORT_PERMISSION_CODENAME, usernames=usernames)

    recipients = list(recipients)
    if len(recipients) < 1:
        logger.info("No recipients for Subject Source Report, so not generating report data.")
        return

    for user, report_context in generate_user_reports(recipients):
        logger.info("Generating Subject Source Report for username: %s, email: %s", user.username, user.email)

        email_body = render_to_string("subjectsourcereport.html", report_context)

        report_timestamp = report_context.get("report_date").strftime("%b %d, %Y %H:%M (utc)")

        message_subject = _(f"EarthRanger Source Report - {report_timestamp}")

        try:
            send_report(
                subject=message_subject,
                to_email=user.email,
                text_content=_("EarthRanger Source report (attached as HTML)."),
                html_content=email_body,
            )
        except SMTPServerDisconnected:
            logger.exception(f"Failed to send Subject Source Report to {user.username} ({user.email})")
        except SMTPSenderRefused as ex_sr:
            logger.warning(f"Failed to send Subject Source Report to {user.username} ({user.email}), %s", ex_sr)


@celery.app.task(base=OverAllTenantTask, bind=True, once={"graceful": True})
def alert_lag_delay(self):
    lagging_providers = get_lagging_providers()

    for lagging_provider in lagging_providers:
        send_lag_delay_alert(*lagging_provider)


@celery.app.task(base=OverAllTenantTask, once={"graceful": True})
def run_check_sources_threshold():
    check_sources_threshold.apply_async()
