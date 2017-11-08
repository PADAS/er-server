import logging
from das_server import celery

logger = logging.getLogger(__name__)

from django.template.loader import render_to_string

from reports.subjectsourcereport import get_subject_source_report_data


@celery.app.task(bind=True)
def subjectsource_report(self):

    dummycontext = {'groups': [
        {'subjects': [
            {'name': 'chris', 'manufacturer_id': '1234980234'}
        ]
        }
    ]}

    dummycontext = {'groups': get_subject_source_report_data()}
    print(dummycontext)
    email_body = render_to_string('subjectsourcereport.html', dummycontext)
    print(email_body)
