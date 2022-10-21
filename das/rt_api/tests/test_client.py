import datetime
import uuid
from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from dateutil.parser import ParserError
from django_fakeredis import FakeRedis
from psycopg2._range import DateTimeTZRange

from django.utils import timezone

from observations.models import UserSession
from observations.utils import dateparse
from rt_api.client import (SID_SESSION_TIMESTAMP_KEY, cleanup_usersessions,
                           create_update_user_session,
                           get_sid_subject_timestamp, redis_client,
                           save_session_timestamp, update_user_session)


@pytest.mark.django_db
class TestClient:
    sid = "e85ae638fe904b6fa1e018c5c401c11c"
    mock_datetime_now = datetime.datetime(
        2010, 10, 2, 14, 10, tzinfo=timezone.utc)

    @FakeRedis("rt_api.client.redis_client")
    def test_save_session_timestamp(self, subject):
        save_session_timestamp(self.sid, str(subject.id))
        result = redis_client.get(SID_SESSION_TIMESTAMP_KEY.format(self.sid))

        assert result
        assert isinstance(result.decode(), str)
        assert isinstance(dateparse(result), datetime.datetime)

    @FakeRedis("rt_api.client.redis_client")
    def test_get_sid_subject_timestamp_with_date_as_iso_format(self, subject):
        redis_client.set(
            SID_SESSION_TIMESTAMP_KEY.format(self.sid),
            datetime.datetime.now().isoformat(),
        )
        result = get_sid_subject_timestamp(self.sid, str(subject.id))

        assert isinstance(result, str)
        assert dateparse(result)

    @FakeRedis("rt_api.client.redis_client")
    def test_get_sid_subject_timestamp_with_date_as_timestamp(self, subject):
        redis_client.set(
            SID_SESSION_TIMESTAMP_KEY.format(self.sid),
            datetime.datetime.now().timestamp(),
        )
        result = get_sid_subject_timestamp(self.sid, str(subject.id))

        assert isinstance(result, str)
        try:
            dateparse(result)
        except Exception as error:
            assert isinstance(error, ParserError)

    def test_create_update_user_session_update_user_session_without_time_range(
        self, monkeypatch, user_session
    ):
        mock = MagicMock()
        mock.datetime.now.return_value = self.mock_datetime_now
        monkeypatch.setattr("rt_api.client.datetime", mock)

        create_update_user_session(user_session.id)
        user_session.refresh_from_db()

        assert user_session.time_range.lower == self.mock_datetime_now
        assert not user_session.time_range.upper

    def test_create_update_user_session_update_user_session_with_time_range(
        self, user_session, monkeypatch
    ):
        date = datetime.datetime(2015, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        user_session.time_range = DateTimeTZRange(lower=date)
        user_session.save()

        mock = MagicMock()
        mock.datetime.now.return_value = self.mock_datetime_now
        monkeypatch.setattr("rt_api.client.datetime", mock)

        create_update_user_session(user_session.id)
        user_session.refresh_from_db()

        assert user_session.time_range.lower == self.mock_datetime_now
        assert not user_session.time_range.upper

    def test_create_update_user_session_create_user_session(self, monkeypatch):
        mock = MagicMock()
        mock.datetime.now.return_value = self.mock_datetime_now
        monkeypatch.setattr("rt_api.client.datetime", mock)

        user_id = uuid.uuid4()
        create_update_user_session(user_id)
        user_session = UserSession.objects.get(pk=user_id)

        assert user_session.time_range.lower == self.mock_datetime_now
        assert not user_session.time_range.upper

    @pytest.mark.parametrize(
        "user_sessions_with_time_range, expected",
        [
            (
                [
                    {
                        "upper": datetime.datetime.now() + timedelta(days=1),
                        "lower": datetime.datetime.now(),
                    },
                    {
                        "upper": datetime.datetime.now() + timedelta(days=1),
                        "lower": datetime.datetime.now(),
                    },
                    {
                        "upper": datetime.datetime.now() + timedelta(days=1),
                        "lower": datetime.datetime.now(),
                    },
                    {
                        "upper": datetime.datetime.now() + timedelta(days=1),
                        "lower": datetime.datetime.now(),
                    },
                    {
                        "upper": datetime.datetime.now() + timedelta(days=1),
                        "lower": datetime.datetime.now(),
                    },
                ],
                5,
            )
        ],
        indirect=["user_sessions_with_time_range"],
    )
    def test_cleanup_usersessions_no_expired_user_sessions(
        self, user_sessions_with_time_range, expected
    ):
        cleanup_usersessions()
        assert UserSession.objects.count() == expected

    @pytest.mark.parametrize(
        "user_sessions_with_time_range, expected",
        [
            (
                [
                    {
                        "upper": datetime.datetime.now(),
                        "lower": datetime.datetime.now() - timedelta(days=7),
                    },
                    {
                        "upper": datetime.datetime.now(),
                        "lower": datetime.datetime.now() - timedelta(days=7),
                    },
                    {
                        "upper": datetime.datetime.now(),
                        "lower": datetime.datetime.now() - timedelta(days=4),
                    },
                    {
                        "upper": datetime.datetime.now(),
                        "lower": datetime.datetime.now() - timedelta(days=3),
                    },
                    {
                        "upper": datetime.datetime.now(),
                        "lower": datetime.datetime.now() - timedelta(days=1),
                    },
                ],
                3,
            ),
            (
                [
                    {
                        "upper": datetime.datetime.now(),
                        "lower": datetime.datetime.now() - timedelta(days=7),
                    },
                    {
                        "upper": datetime.datetime.now(),
                        "lower": datetime.datetime.now() - timedelta(days=7),
                    },
                    {
                        "upper": datetime.datetime.now(),
                        "lower": datetime.datetime.now() - timedelta(days=7),
                    },
                    {
                        "upper": datetime.datetime.now(),
                        "lower": datetime.datetime.now() - timedelta(days=7),
                    },
                    {
                        "upper": datetime.datetime.now(),
                        "lower": datetime.datetime.now() - timedelta(days=1),
                    },
                ],
                1,
            ),
        ],
        indirect=["user_sessions_with_time_range"],
    )
    def test_cleanup_usersessions_with_expired_user_sessions(
        self, user_sessions_with_time_range, expected
    ):
        cleanup_usersessions()
        assert UserSession.objects.count() == expected

    def test_update_user_session_user_session_with_no_time_range(
        self, user_session, monkeypatch
    ):
        mock = MagicMock()
        mock.datetime.now.return_value = self.mock_datetime_now
        monkeypatch.setattr("rt_api.client.datetime", mock)

        update_user_session(user_session.id)
        user_session.refresh_from_db()

        assert user_session.time_range.lower == self.mock_datetime_now
        assert not user_session.time_range.upper

    def test_update_user_session_user_session_with_time_range(
        self, user_session, monkeypatch
    ):
        mock = MagicMock()
        mock.datetime.now.return_value = self.mock_datetime_now
        monkeypatch.setattr("rt_api.client.datetime", mock)

        date = datetime.datetime(2009, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        user_session.time_range = DateTimeTZRange(lower=date)
        user_session.save()

        update_user_session(user_session.id)
        user_session.refresh_from_db()

        assert user_session.time_range.upper == self.mock_datetime_now
        assert user_session.time_range.lower == date

    def test_update_user_session_user_session_with_time_range_upper_as_none(
        self, user_session, monkeypatch
    ):
        mock = MagicMock()
        mock.datetime.now.return_value = self.mock_datetime_now
        monkeypatch.setattr("rt_api.client.datetime", mock)

        user_session.time_range = DateTimeTZRange()
        user_session.save()

        update_user_session(user_session.id)
        user_session.refresh_from_db()

        assert user_session.time_range.upper == self.mock_datetime_now
        assert not user_session.time_range.lower
