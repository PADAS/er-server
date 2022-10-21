import logging
from datetime import datetime, timedelta

import pytz

from django.utils.translation import gettext_lazy as _

from analyzers.models import SubjectAnalyzerResult
from observations.models import Observation, Subject, SubjectSource

logger = logging.getLogger(__name__)


def generate_subject_records(report_hours=24):
    '''
    For each subject-source generate a single report line for the most recent 24-hour period
    :param report_hours: How many hours of data should be interpreted for each subject.
    :return: generator of subject-source-performance records.
    '''
    now = datetime.now(tz=pytz.utc)
    for ss in SubjectSource.objects.filter(subject__subject_subtype__subject_type='wildlife', subject__is_active=True,
                                           assigned_range__contains=datetime.now(tz=pytz.utc)):

        result = {'subject_id': str(ss.subject.id),
                  'model_name': ss.source.model_name,
                  'manufacturer_id': ss.source.manufacturer_id,
                  'name': ss.subject.name,
                  'frequency': ss.source.additional.get('frequency', ''),
                  'data_starts': ss.safe_assigned_range.lower,
                  'species': ss.subject.subject_subtype.display,
                  'region': ss.subject.additional.get('region', 'Unassigned'),
                  }

        try:
            latest_observation = Observation.objects.filter(
                source=ss.source).latest('recorded_at')
        except Observation.DoesNotExist:
            latest_observation = None

        # If a subject gets here but has no Observations then we'll exclude it from the report.
        # TODO: Consider a 'blank' report record for this case.

        if latest_observation:

            result['latest_observation_at'] = latest_observation.recorded_at

            latest_observations = Observation.objects.filter(source=ss.source,
                                                             recorded_at__gt=(
                                                                 latest_observation.recorded_at -
                                                                 timedelta(hours=report_hours)))

            alert_accumulator = {}
            for ar in SubjectAnalyzerResult.objects.filter(subject=ss.subject,
                                                           estimated_time__range=(latest_observation.recorded_at -
                                                                                  timedelta(
                                                                                      hours=report_hours),
                                                                                  latest_observation.recorded_at),
                                                           level__gt=SubjectAnalyzerResult.LEVEL_OK
                                                           ):
                k = ar.subject_analyzer.analyzer_category
                alert_accumulator.setdefault(k, 0)
                alert_accumulator[k] += 1

            try:
                trajectory = ss.subject.create_trajectory(obs=latest_observations,
                                                          trajectory_filter_params=ss.subject.default_trajectory_filter())
                trajectory_length = trajectory.relocs.fix_count
            except Exception:
                trajectory_length = 'n/a'

            result['performance'] = (
                len(latest_observations), trajectory_length)

            result['voltage'] = latest_observation.additional.get(
                'voltage', '') if latest_observation.additional else ''

            result['analyzers'] = alert_accumulator
            result['analyzers_summary'] = ', '.join(
                '{}({})'.format(k, v) for k, v in alert_accumulator.items())

            result['time_since_last'] = calculate_age_description(
                latest_observation.recorded_at)

            result['styles'] = {}
            los_styles = calculate_styles(
                'latest_observation_at', latest_observation.recorded_at)
            result['styles']['time_since_last'] = ';'.join(los_styles)
            yield result


def calculate_age_description(val):
    '''
    Describe age of latest observation in terms of fractional hours or days.
    :param val: datetime
    :return: Friendly description of age.
    '''
    age_s = (datetime.now(tz=pytz.utc) - val).total_seconds()
    if age_s > 86400:
        return _('{0:0.1f} days').format(float(age_s / 86400.0))
    else:
        return _('{0:0.1f} hours').format(float(age_s / 3600.0))


TD_12_HOURS = timedelta(hours=12)
TD_48_HOURS = timedelta(hours=48)


def build_legend():
    return [
        {
            'text': 'Data is Current',
            'styles': 'color:#0a0;',
        },
        {
            'text': 'Data older than 12 hours',
            'styles': 'color:#f60;',
        },
        {
            'text': 'Data older than 48 hours',
            'styles': 'color:#c00;font-weight:bold',
        }
    ]


def calculate_latest_observation_style(val):
    '''
    Determine which styles should be applied to the value.
    :param val:
    :return: tuple of styles
    '''
    if val is None:
        return None
    age = datetime.now(tz=pytz.utc) - val
    if age > TD_48_HOURS:
        return ('color:#c00', 'font-weight:bold')
    if age > TD_12_HOURS:
        return ('color:#f60',)
    return ('color:#0a0',)


# Map a context data key to a function that'll calculate styles for the
# template to apply.
style_calculator_map = {
    'latest_observation_at': calculate_latest_observation_style
}


def calculate_styles(keyword, value):

    fn = style_calculator_map.get(keyword, None)
    if fn:
        return fn(value)


def filter_by_user(values, user, key='subject_id'):
    '''
    Filter list of values to those the User has permission to see.
    :param values: a list of dict objects having subject_id in 'key'.
    :param user: User to filter by.
    :param key:
    :return: filtered list
    '''
    user_subject_ids = [
        sub.id for sub in Subject.objects.all().by_user_subjects(user)]
    user_subject_ids = [str(x) for x in user_subject_ids]
    return [sub for sub in values if sub[key] in user_subject_ids]


def groupify_report_data(subject_records):

    # group by region and species to conform to STE bulletin format.
    groups = {}

    try:
        for record in subject_records:
            species, region = record.get('species'), record.get('region')
            group = groups.setdefault(
                (species, region), {'species': species, 'region': region})
            # Used in template.
            group['sort_key'] = '{}:{}'.format(region, species)
            subjects = group.setdefault('subjects', [])
            subjects.append(record)

    except StopIteration as si:
        print(si)

    # Create a sorted list of groups
    group_list = sorted(groups.values(), key=lambda x: '%s %s' %
                        (species, region), reverse=False)

    return group_list


def generate_user_reports(userlist):
    '''
    A few steps.
    1. Generate a comprehensive list if records for all collars.
    2. For each recipient, reduce the list to Subjects the user is allowed to see.
    3. Organize the data in groups (by [species/region]) for the report context.
    :param userlist:
    :return:
    '''
    report_records = list(generate_subject_records())
    report_timestamp = datetime.now(tz=pytz.utc)

    for user in userlist:
        user_filtered_records = filter_by_user(report_records, user)

        group_list = groupify_report_data(user_filtered_records)

        message_context = {
            'groups': group_list,
            'report_date': report_timestamp,
            'report_legend': build_legend(),
        }

        yield user, message_context
