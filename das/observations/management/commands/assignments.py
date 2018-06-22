from datetime import datetime, timedelta
import pytz
import psycopg2.extras
import dateutil.parser as date_parser

import glob
import json
import os

import yaml
try:
    from yaml import CSafeLoader as SafeLoader
except ImportError:
    from yaml import SafeLoader
from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import Permission
from django.db.models import F, Q

from observations.models import Subject, Source, SubjectSource, SourceProvider


def find_assignments(subject=None, source=None, start_date=None, end_date=None):
    '''
    Return all assignments that include the subject and/or source and overlap with range [start_date, end_date].
    start_date and end_date default to datetime.min and datetime.max respectively.
    '''
    if all((x is None for x in (subject, source))):
        raise ValueError(
            'You must provide at least one of subject and source.')

    # Construct a datetimetzrange from the given dates.
    start_date = start_date or datetime.now(tz=pytz.utc)
    end_date = end_date or datetime.max.replace(tzinfo=pytz.utc)
    assignment_range = psycopg2.extras.DateTimeTZRange(
        lower=start_date, upper=end_date)

    qs = SubjectSource.objects.all()

    if subject is not None:
        qs = qs.filter(subject=subject)

    if source is not None:
        qs = qs.filter(source=source)

    qs = qs.filter(assigned_range__overlap=assignment_range)

    qs.order_by('assigned_range')

    return qs


def update_assignment(assignment, start_date=None, end_date=None, force=False):
    '''
    End the assignment
    force = True will set the end_date for assignment regardless of what it is current set to.
    '''
    # Construct a datetimetzrange from the given dates.
    start_date = start_date or assignment.assigned_range.lower
    end_date = end_date or assignment.assigned_range.upper
    new_assignment_range = psycopg2.extras.DateTimeTZRange(
        lower=start_date, upper=end_date)

    SubjectSource.objects.filter(id=assignment.id).update(
        assigned_range=new_assignment_range)


def add_assignment(subject, source, start_date=None, end_date=None):
    '''
    Create an assignment for given subject and source.
    Raise exception if a conflicting assignment exists.
    '''
    # Construct a datetimetzrange from the given dates.
    start_date = start_date or datetime.now(tz=pytz.utc)
    end_date = end_date or datetime.max.replace(tzinfo=pytz.utc)
    assignment_range = psycopg2.extras.DateTimeTZRange(
        lower=start_date, upper=end_date)

    conflicting_assignments = SubjectSource.objects.filter(
        Q(subject=subject) | Q(source=source),
        assigned_range__overlap=assignment_range)

    if conflicting_assignments:
        for x in conflicting_assignments:
            print(x)
        raise Exception('Conflicting assignments already exist.')
    else:
        SubjectSource.objects.create(
            subject=subject, source=source, assigned_range=assignment_range)


def ensure_assignment(subject_name, manufacturer_id, model_name, source_type, source_provider_key):

    source_provider = SourceProvider.objects.get(
        provider_key=source_provider_key)

    print(f'Ensuring assignment for name {subject_name} with source {manufacturer_id}')

    # Get subjects by name
    subs = Subject.objects.filter(name=subject_name)
    if len(subs) > 1:
        raise Exception(f'name {subject_name} is assigned to multiple subjects')
    if subs:
        subject = subs[0]
        assignments = find_assignments(subject=subject, start_date=START_DATE)
        print(f'Subject found assignments {assignments}') if assignments else print('No assignments yet.')

        for assignment in assignments:
            if assignment.source.manufacturer_id != manufacturer_id:
                print(f'Ending assignment for subject {subject_name} to source {assignment.source.manufacturer_id}')
                update_assignment(assignment, end_date=START_DATE)

    else:
        print(f'name {subject_name} does not exist.')

    # Get sources by manufacturer_id
    srcs = Source.objects.filter(manufacturer_id=manufacturer_id)
    if len(srcs) > 1:
        raise Exception(f'source {manufacturer_id} is not unique.')
    if srcs:
        source = srcs[0]
        assignments = find_assignments(source=source, start_date=START_DATE)
        print(f'Source found assignements {assignments}') if assignments else print('No assignments yet.')

        for assignment in assignments:
            if assignment.subject.name != subject_name:
                print(f'Ending assignment for source {manufacturer_id} to subject {assignment.subject.name}')
                update_assignment(assignment, end_date=START_DATE)
    else:
        print(f'mid {manufacturer_id} does not exist.')
        source = Source.objects.create(manufacturer_id=manufacturer_id, model_name=model_name,
                                       provider=source_provider, source_type=source_type)

    if subject and source:
        existing_assignment = find_assignments(
            subject=subject, source=source, start_date=START_DATE)
        if not existing_assignment:
            print(f'Adding assignment for {subject_name} to {manufacturer_id}')
            add_assignment(subject, source, start_date=START_DATE)
        else:
            print(f'Found existing assignment for {subject_name} to {manufacturer_id}')


subject_radio_pairs = (
    ('G10A', 'trbonet-50712'),
    ('G10B', 'trbonet-50713'),
    ('G10C', 'trbonet-50714'),
    ('G15A', 'trbonet-50715'),
    ('G15B', 'trbonet-50716'),
    ('G16A', 'trbonet-50717'),
    ('G16B', 'trbonet-50718'),
    ('G17A', 'trbonet-50719'),
    ('G17B', 'trbonet-50720'),
    ('G18A', 'trbonet-50721'),
    ('G18B', 'trbonet-50722'),
    ('G1KA', 'trbonet-50723'),
    ('G1KB', 'trbonet-50724'),
    ('G1KC', 'trbonet-50725'),
    ('G1KD', 'trbonet-50726'),
    ('G1KE', 'trbonet-50727')
)


model_name = 'dasradioagent:grumeti-trbonet'
source_type = 'gps-radio'
source_provider_key = 'grumeti-trbonet'

START_DATE = datetime(2018, 6, 14, tzinfo=pytz.utc)


class Command(BaseCommand):

    help = 'Administer Subject-Source assigments.'

    def add_arguments(self, parser):
        parser.add_argument(
            '-n', '--subject_name',
            action='store',
            dest='subject_name',
            default='',
            help='Subject Name',
        )

        parser.add_argument(
            '-m', '--manufacturer_id',
            action='store',
            dest='manufacturer_id',
            default='',
            help='Device Manufacturer Id',
        )

        parser.add_argument(
            '-d', '--start_date',
            action='store',
            dest='start_date',
            default=None,
            help='Start date for new assignment.',
        )

        parser.add_argument(
            '-t', '--source_type',
            action='store',
            dest='source_type',
            default='gps-radio',
            help='Source Type.',
        )

        parser.add_argument(
            '-p', '--provider_key',
            action='store',
            dest='provider_key',
            default='default',
            help='Source Provider Key.',
        )

    def handle(self, *args, **options):

        try:
            start_date = date_parser.parse(options['start_date']) if options.get('start_date') \
                else datetime.now(tz=pytz.utc)
        except ValueError:
            print(f"-start_date={options['start_date']} is not valid. Please provide a valid date string.")
            return

        print(f'Start date = {start_date.isoformat()}')
        print(f'Options = {options}')

        ensure_assignment(subject_name=options['subject_name'], manufacturer_id=options['manufacturer_id'],
                          model_name=options['model_name'],
                          source_type=options['source_type'], source_provider_key=options['provider_key'])
