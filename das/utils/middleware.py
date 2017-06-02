import logging
import time

from django.conf import settings


class RequestLoggingMiddleware(object):
    logger = logging.getLogger('django.request')

    def process_request(self, request):
        self.start_time = time.time()

    def process_exception(self, request, exception):
        self.logger.exception('Exception handling %s', request.get_full_path)

    def process_response(self, request, response):
        try:
            result = {}

            logname = '-'
            remote_addr = request.META.get('REMOTE_ADDR')
            remote_addr = request.META.get(
                'HTTP_X_FORWARDED_FOR') or remote_addr
            user_id = '-'
            if hasattr(request, 'user'):
                user_id = getattr(request.user, 'id', '-')
            try:
                req_time = time.time() - self.start_time
            except AttributeError:
                req_time = 0
            content_length = len(getattr(response, 'content', []))
            referer = request.META.get('HTTP_REFERER', '')
            user_agent = request.META.get('HTTP_USER_AGENT', '')
            status = response.status_code
            path = request.get_full_path()
            method = request.method
            protocol = request.META.get('SERVER_PROTOCOL', '')

            extra = dict(
                remote_addr=remote_addr,
                user_id=user_id,
                req_time=req_time,
                content_length=content_length,
                referer=referer,
                user_agent=user_agent,
                status=status,
                path=path,
                method=method,
                protocol=protocol,
            )

            request_info = '{0} {1} {2}'.format(method, path, protocol)
            method = '%s %s %s [] "%s" %s %s "%s" "%s" (%.02f seconds)' % (
                remote_addr, logname, user_id, request_info,
                status, content_length, referer, user_agent, req_time)

            self.logger.info('request', extra=extra)

        except Exception as e:
            logging.exception('RequestLoggingMiddleware Error')

        return response
