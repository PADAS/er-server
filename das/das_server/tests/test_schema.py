import pytest
from django.urls import reverse
pytestmark = pytest.mark.django_db


def test_schema_builder(client, django_user_model):
    password = django_user_model.objects.make_random_password()
    user_const = dict(last_name='last', first_name='first')
    user = django_user_model.objects.create_superuser(
        'super_user', 'das_super_user@vulcan.com', password,
        **user_const)
    client.force_login(user)
    response = client.get(reverse("openapi-schema"))
    assert response.status_code == 200
