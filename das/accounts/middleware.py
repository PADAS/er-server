import logging
import time
import uuid

from django.http import HttpResponseForbidden

from accounts.models import User


class UserProfileMiddleware(object):
    '''
    Allow a user to impersonate another user profile during an http request
    '''

    logger = logging.getLogger('django.request')

    def process_request(self, request):
        logged_in_user = request.user
        profile_header = request.META.get('HTTP_USER_PROFILE', None)
        if profile_header:
            profile_pk = uuid.UUID(profile_header)
            if 1 != logged_in_user.act_as_profiles.all().filter(pk=profile_pk).count():
                raise HttpResponseForbidden

            profile_user = User.objects.get(pk=profile_pk)

            if profile_user.is_staff or profile_user.is_superuser:
                raise HttpResponseForbidden

            request.user = profile_user
