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

from observations.models import Subject, Source, SubjectSource, SourceProvider, SOURCE_TYPES


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
    start_date = start_date or assignment.safe_assigned_range.lower
    end_date = end_date or assignment.safe_assigned_range.upper
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


def get_subject(subject_name, subject_subtype):

    try:
        subject, created = Subject.objects.get_or_create(name=subject_name, subject_subtype_id=subject_subtype)
        if created:
            print(f'Subject named {subject_name} was not found, so I created it for you.')
        return subject
    except Subject.MultipleObjectsReturned:
        print(f'I found multiple subjects named {subject_name} of subject_subtype {subject_subtype}')
        raise


def ensure_assignment(subject, manufacturer_id, model_name, source_type, source_provider_key,
                      start_date):

    source_provider, created = SourceProvider.objects.get_or_create(provider_key=source_provider_key)
    if created:
        print(f'SourceProvider with key {source_provider_key} was not found, so I created it.')

    print(f'Ensuring assignment for name {subject.name} with source {manufacturer_id}')

    assignments = find_assignments(subject=subject, start_date=start_date)
    print(f'Subject found assignments {assignments}') if assignments else print('No assignments yet.')

    for assignment in assignments:
        if assignment.source.manufacturer_id != manufacturer_id:
            print(f'Ending assignment for subject {subject.name} to source {assignment.source.manufacturer_id}')
            update_assignment(assignment, end_date=start_date)


    # Get sources by manufacturer_id
    srcs = Source.objects.filter(manufacturer_id=manufacturer_id)
    if len(srcs) > 1:
        raise Exception(f'source {manufacturer_id} is not unique.')
    if srcs:
        source = srcs[0]
        assignments = find_assignments(source=source, start_date=start_date)
        print(f'Source found assignements {assignments}') if assignments else print('No assignments yet.')

        for assignment in assignments:
            if assignment.subject.name != subject.name:
                print(f'Ending assignment for source {manufacturer_id} to subject {assignment.subject.name}')
                update_assignment(assignment, end_date=start_date)
    else:
        print(f'mid {manufacturer_id} does not exist.')
        source = Source.objects.create(manufacturer_id=manufacturer_id, model_name=model_name,
                                       provider=source_provider, source_type=source_type)

    if subject and source:
        existing_assignment = find_assignments(
            subject=subject, source=source, start_date=start_date)
        if not existing_assignment:
            print(f'Adding assignment for {subject.name} to {manufacturer_id}')
            add_assignment(subject, source, start_date=start_date)
        else:
            print(f'Found existing assignment for {subject.name} to {manufacturer_id}')


# source_type_list = (k for k,v in SOURCE_TYPES)
class Command(BaseCommand):

    help = 'Administer Subject-Source assigments.'

    def add_arguments(self, parser):
        parser.add_argument(
            '-n', '--subject_name',
            action='store',
            dest='subject_name',
            required=True,
            help='Subject Name',
        )

        parser.add_argument(
            '-m', '--manufacturer_id',
            action='store',
            dest='manufacturer_id',
            required=True,
            help='Device Manufacturer Id',
        )

        parser.add_argument(
            '-d', '--start_date',
            action='store',
            dest='start_date',
            required=True,
            help='Start date for new assignment.',
        )

        parser.add_argument(
            '-t', '--source_type',
            action='store',
            dest='source_type',
            required=True,
            # ['gps-radio', 'tracking-device'],
            choices=list((k for k, v in SOURCE_TYPES)),
            help='Source Type.'
        )

        parser.add_argument(
            '-p', '--provider_key',
            action='store',
            dest='provider_key',
            required=True,
            help='Source Provider Key.',

        )

        parser.add_argument(
            '--model_name',
            action='store',
            dest='model_name',
            required=False,
            default='unspecified',
            help='Model name.',

        )

        parser.add_argument(
            '--subject_subtype',
            action='store',
            dest='subject_subtype',
            required=False,
            default='unassigned',
            help='Subject Subtype to use if a subject is to be created.',
        )

    def handle(self, *args, **options):

        try:
            start_date = date_parser.parse(options['start_date']) if options.get('start_date') \
                else datetime.now(tz=pytz.utc)
        except ValueError:
            print(f"-start_date={options['start_date']} is not valid. Please provide a valid date string.")
            return
        else:

            print(f'Subject Name = {options["subject_name"]}')
            print(f'Manufacturer ID = {options["manufacturer_id"]}')
            print(f'Model Name = {options["model_name"]}')
            print(f'Source Type = {options["source_type"]}')
            print(f'Provider Key = {options["provider_key"]}')
            print(f'Subject Subtype = {options["subject_subtype"]}')

            try:
                subject = get_subject(subject_name=options['subject_name'], subject_subtype=options['subject_subtype'])
            except Exception as e:
                print(f'Subject name, type is unresolvable. ex={e}')
            else:
                ensure_assignment(subject=subject,
                                  manufacturer_id=options['manufacturer_id'],
                                  model_name=options['model_name'],
                                  source_type=options['source_type'],
                                  source_provider_key=options['provider_key'],
                                  start_date=start_date)
