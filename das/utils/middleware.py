import logging
import time

from django.conf import settings


class RequestLoggingMiddleware(object):
    logger = logging.getLogger('django.request')
    def process_request(self, request):
        self.start_time = time.time()

    def process_response(self, request, response):
        try:
            result = {}

            logname = '-'
            remote_addr = request.META.get('REMOTE_ADDR')
            if remote_addr in getattr(settings, 'INTERNAL_IPS', []):
                remote_addr = request.META.get(
                    'HTTP_X_FORWARDED_FOR') or remote_addr
            user_email = '-'
            if hasattr(request, 'user'):
                user_email = getattr(request.user, 'email', '-')
            req_time = time.time() - self.start_time
            content_len = len(response.content)
            referer = request.META.get('HTTP_REFERER', '')
            agent = request.META.get('HTTP_USER_AGENT', '')
            status = response.status_code
            path = request.get_full_path()
            method = request.method
            protocol = request.META.get('SERVER_PROTOCOL', '')

            request_info = '{0} {1} {2}'.format(method, path, protocol)

            self.logger.info('%s %s %s [] "%s" %s %s "%s" "%s" (%.02f seconds)' % (
            remote_addr, logname, user_email, request_info,
            status, content_len, referer, agent, req_time))

        except Exception as e:
            logging.exception('RequestLoggingMiddleware Error')

        return response