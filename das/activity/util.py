from django.contrib.auth import get_user_model


def get_er_user():
    user_model = get_user_model()
    user, _ = user_model.objects.get_or_create(username='er_system',
                                               defaults={'first_name': 'EarthRanger',
                                                         'last_name': 'System',
                                                         'password': user_model.objects.make_random_password()
                                                         })
    return user
