import inspect
import time
import logging
import json
from urllib.parse import urlparse

import environ
from locust import Locust, TaskSet, task, events, HttpLocust
from locust.clients import HttpSession
from socketio import Client


env = environ.Env(
    # set casting, default value
    DEBUG=(bool, False)
)


def stopwatch(func):
    """
    From the article: https://medium.com/locust-io-lets-get-some-fun/locust-custom-client-23e205f4611f
    :param func:
    :return:
    """
    def wrapper(*args, **kwargs):
        # get task's function name
        previous_frame = inspect.currentframe().f_back
        _, _, task_name, _, _ = inspect.getframeinfo(previous_frame)

        start = time.time()
        result = None
        try:
            result = func(*args, **kwargs)
        except Exception as e:
            total = int((time.time() - start) * 1000)
            events.request_failure.fire(request_type="TYPE",
                                        name=task_name,
                                        response_time=total,
                                        exception=e)
        else:
            total = int((time.time() - start) * 1000)
            events.request_success.fire(request_type="TYPE",
                                        name=task_name,
                                        response_time=total,
                                        response_length=0)
        return result
    return wrapper


class RTSocketIOClient:
    def __init__(self, host, port, scheme, oauth_token):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.host = host
        self.port = port
        self.scheme = scheme
        self.id_counter = 0
        self.client = None
        self.oauth_token = oauth_token

    def get_next_id(self):
        self.id_counter += 1
        return self.id_counter

    def connect(self):
        self.client = Client()
        url = f'{self.scheme}://{self.host}:{self.port}/socket.io'
        self.client.connect(url)
        self.client.sleep(0)
        params = dict(authorization=f'Bearer {self.oauth_token}',
                      type='authorization',
                      id=self.get_next_id())
        self.client.call('authorization', params)
        self.client.sleep(1)

    @stopwatch
    def echo(self, message=None):
        self.client.call('echo', json.dumps(
            {"data": message or 'Hello Server'}))

    @stopwatch
    def send_event_filter(self, filter_=None):
        self.client.call('event_filter', json.dumps(filter_ or {}))

    @stopwatch
    def send_bbox_filter(self, bbox=None):
        self.client.call('bbox', json.dumps({"data": bbox}))

    def disconnect(self):
        self.client.disconnect()
        self.client = None


class OAuthClient(HttpSession):
    def __init__(self, base_url, *args, **kwargs):
        if 'oauth_token' not in kwargs:
            raise KeyError('oauth_token required parameter')
        self.oauth_token = kwargs.pop('oauth_token')

        super().__init__(base_url=base_url, *args, **kwargs)

    def request(self, method, url, name=None, catch_response=False, **kwargs):
        headers = kwargs.get('headers', {})
        headers['Authorization'] = f'Bearer {self.oauth_token}'
        kwargs['headers'] = headers

        super().request(method, url, name=name, catch_response=catch_response, **kwargs)


class APIClient:
    def __init__(self, host, port, scheme, oauth_token):
        url = f"{scheme}://{host}:{port}/api/v1.0/"
        web_url = f"{scheme}://{host}:{port}"
        self.http = OAuthClient(base_url=url, oauth_token=oauth_token)
        self.web = HttpSession(base_url=web_url)
        self.rtsocket = RTSocketIOClient(host, port, scheme, oauth_token)

    def connect(self):
        self.rtsocket.connect()

    def disconnect(self):
        self.rtsocket.disconnect()

    def echo(self, message=None):
        self.rtsocket.echo(message)

    def send_event_filter(self, filter_=None):
        self.rtsocket.send_event_filter(filter_)

    def send_bbox_filter(self, bbox=None):
        self.rtsocket.send_bbox_filter(bbox)

    def web_request(self, method, url, name=None, catch_response=False, **kwargs):
        self.web.request(method, url, name=None,
                         catch_response=False, **kwargs)

    def request(self, method, url, name=None, catch_response=False, **kwargs):
        self.http.request(method, url, name=None,
                          catch_response=False, **kwargs)

    def status(self):
        params = dict(db_connections=True, service_status=True)
        self.http.request('GET', 'status', name='status', params=params)


class APILocust(Locust):
    oauth_token = env.str('OAUTH_TOKEN')

    def __init__(self):
        super().__init__()
        # host is https://dev.pamdas.org:443
        parsed = urlparse(self.host)
        self.host = parsed.hostname
        self.port = parsed.port or 443
        self.scheme = parsed.scheme
        self.client = APIClient(
            host=self.host, port=self.port, scheme=self.scheme, oauth_token=self.oauth_token)
        self.client.connect()

    def teardown(self):
        self.client.disconnect()
