import pytest
from psycopg2._range import DateTimeTZRange

from rt_api.factories import UserSessionFactory


@pytest.fixture
def user_session():
    return UserSessionFactory.create()


@pytest.fixture
def user_sessions_with_time_range(request):
    results = []
    for param in request.param:
        date_rage = DateTimeTZRange(**param)
        results.append(UserSessionFactory.create(time_range=date_rage))
    return results
