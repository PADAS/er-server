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


class RTUser(APILocust):
    task_set = RTTasks
    min_wait = 0
    max_wait = 0
