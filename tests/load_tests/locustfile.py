"""
Examples:
    set environment variable OAUTH_TOKEN=<>
    locust --host=https://dev.pamdas.org:443

"""

import logging

from locust import TaskSet, task

from clients import APILocust


class RTTasks(TaskSet):
    @task
    def echo_task(self):
        self.client.echo('big echo')

    @task
    def send_event_filter_task(self):
        self.client.send_event_filter(
            {"state": "all", "event_type": "cameratrap_rep", "priority": 300})

    @task
    def status_task(self):
        self.client.status()

    @task
    def get_profiles(self):
        self.client.request('GET', 'user/me/profiles')

    @task
    def get_fitlerschema(self):
        self.client.request('GET', 'activity/eventfilters/schema')

    @task
    def get_schema(self):
        self.client.request('GET', 'activity/events/schema')

    @task
    def get_me(self):
        self.client.request('GET', 'user/me')

    @task
    def get_events(self):
        self.client.request(
            'GET', 'activity/events?exclude_contained=true&include_notes=true&include_related_events=true&state=active&state=new')

    @task
    def get_subjectgroups(self):
        self.client.request('GET', 'subjectgroups')

    @task
    def get_maps(self):
        self.client.request('GET', 'maps')

    @task
    def get_layers(self):
        self.client.request('GET', 'layers')

    @task
    def get_featureset(self):
        self.client.request('GET', 'featureset')

    @task
    def get_index(self):
        self.client.web_request('GET', '/index.html')

    @task
    def get_ranger_image(self):
        self.client.web_request('GET', '/static/ranger-black.svg')

    @task
    def get_scout_image(self):
        self.client.web_request('GET', '/static/scout.svg')


class RTUser(APILocust):
    task_set = RTTasks
    min_wait = 0
    max_wait = 0
