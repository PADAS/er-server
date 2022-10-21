from django.contrib.auth import get_user_model
from activity.models import EventCategory
from activity.permissions import EventCategoryPermissions
from rest_framework.response import Response
from rest_framework import status


def get_er_user():
    user_model = get_user_model()
    user, _ = user_model.objects.get_or_create(username='er_system',
                                               defaults={'first_name': 'EarthRanger',
                                                         'last_name': 'System',
                                                         'password': user_model.objects.make_random_password()
                                                         })
    return user


def get_permitted_event_categories(request):
    permitted_categories = []

    for category in EventCategory.objects.filter(is_active=True):
        permission_name = 'activity.{0}_{1}'.format(
            category.value,
            EventCategoryPermissions.http_method_map['GET']
        )
        if request.user.has_perm(permission_name):
            permitted_categories.append(category)
    return permitted_categories


def return_409_response():
    status_msg = {'error_message': 'The request could not be completed due to conflict with existing data.'}
    return Response(status_msg, status=status.HTTP_409_CONFLICT)
