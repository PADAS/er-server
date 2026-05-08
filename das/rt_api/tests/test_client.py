import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from dateutil.parser import ParserError
from psycopg2._range import DateTimeTZRange

from django.utils import lorem_ipsum

from observations.models import UserSession
from observations.utils import dateparse
from rt_api.client import (
    CLIENT_REALTIME_SERVICES_TTL,
    EXPIRED_CLIENT_TRACES_LIST,
    REALTIME_SERVICES_KEY,
    SESSION_CURSOR_GRACE_WINDOW,
    SESSION_CURSOR_TTL,
    SID_SESSION_TIMESTAMP_KEY,
    SID_SUBJECTS_TIMESTAMPS_KEY,
    ClientData,
    add_client,
    cleanup_usersessions,
    create_update_user_session_by_sid,
    get_client,
    get_sid_subject_timestamp,
    message_index,
    redis_client,
    remove_all_rt_services,
    remove_invalid_rt_service_key,
    save_session_timestamp,
    trace_expiration_handler,
    update_client,
    update_user_session_by_sid,
)


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestClient:
    sid = "e85ae638fe904b6fa1e018c5c401c11c"
    mock_datetime_now = datetime(2010, 10, 2, 14, 10, tzinfo=timezone.utc)

    def test_save_session_timestamp(self, subject):
        session_key = SID_SESSION_TIMESTAMP_KEY.format(self.sid)
        subjects_key = SID_SUBJECTS_TIMESTAMPS_KEY.format(self.sid)
        redis_client.delete(session_key, subjects_key)

        save_session_timestamp(self.sid, str(subject.id))
        result = redis_client.get(session_key)

        assert result
        assert isinstance(result.decode(), str)
        assert isinstance(dateparse(result), datetime)

        # Both cursor keys must carry a bounded TTL so orphaned sessions
        # can't accumulate forever in Redis — but long enough to survive an
        # idle tracked subject (no new observations for hours to days).
        session_ttl = redis_client.ttl(session_key)
        subjects_ttl = redis_client.ttl(subjects_key)
        assert 0 < session_ttl <= SESSION_CURSOR_TTL
        assert session_ttl > CLIENT_REALTIME_SERVICES_TTL
        assert 0 < subjects_ttl <= SESSION_CURSOR_TTL
        assert subjects_ttl > CLIENT_REALTIME_SERVICES_TTL

    def test_message_index_sets_ttl(self):
        key = f"mid-{self.sid}"
        redis_client.delete(key)

        result = message_index(self.sid, "event")

        assert result == 1
        ttl = redis_client.ttl(key)
        assert 0 < ttl <= CLIENT_REALTIME_SERVICES_TTL

        # TTL is refreshed on each call so a continuously-active session
        # keeps its mid-* key alive.
        message_index(self.sid, "event")
        assert 0 < redis_client.ttl(key) <= CLIENT_REALTIME_SERVICES_TTL
        assert int(redis_client.hget(key, "event")) == 2

    def test_trace_expiration_handler_sets_ttl(self):
        redis_client.delete(EXPIRED_CLIENT_TRACES_LIST)
        msg = {"channel": "__keyspace@2__:trace-abc123-1700000000"}

        trace_expiration_handler(msg)

        assert redis_client.hexists(EXPIRED_CLIENT_TRACES_LIST, "abc123")
        ttl = redis_client.ttl(EXPIRED_CLIENT_TRACES_LIST)
        assert 0 < ttl <= CLIENT_REALTIME_SERVICES_TTL

    def test_get_sid_subject_timestamp_missing_keys_returns_grace_window(self, subject):
        # When both cursor keys are missing the fallback must return a
        # timestamp in the recent past, not now(), so the first observation
        # after a cursor miss is still picked up by FlattenObservationsView's
        # created_at >= created_after filter.
        redis_client.delete(
            SID_SESSION_TIMESTAMP_KEY.format(self.sid),
            SID_SUBJECTS_TIMESTAMPS_KEY.format(self.sid),
        )
        before = datetime.now(tz=timezone.utc)

        result = get_sid_subject_timestamp(self.sid, str(subject.id))

        parsed = dateparse(result)
        after = datetime.now(tz=timezone.utc)
        # result == now - grace_window, so result must fall in
        # [before - grace_window, after - grace_window].
        assert (before - SESSION_CURSOR_GRACE_WINDOW) <= parsed <= (after - SESSION_CURSOR_GRACE_WINDOW)

    def test_get_sid_subject_timestamp_with_date_as_iso_format(self, subject):
        redis_client.set(
            SID_SESSION_TIMESTAMP_KEY.format(self.sid),
            datetime.now(tz=timezone.utc).isoformat(),
        )
        result = get_sid_subject_timestamp(self.sid, str(subject.id))

        assert isinstance(result, str)
        assert dateparse(result)

    def test_get_sid_subject_timestamp_with_date_as_timestamp(self, subject):
        redis_client.set(
            SID_SESSION_TIMESTAMP_KEY.format(self.sid),
            datetime.now(tz=timezone.utc).timestamp(),
        )
        result = get_sid_subject_timestamp(self.sid, str(subject.id))

        assert isinstance(result, str)
        try:
            dateparse(result)
        except Exception as error:
            assert isinstance(error, ParserError)

    def test_create_update_user_session_update_user_session_without_time_range(self, monkeypatch, user_session):
        mock = MagicMock()
        mock.datetime.now.return_value = self.mock_datetime_now
        monkeypatch.setattr("rt_api.client.datetime", mock)

        create_update_user_session_by_sid(user_session.sid)
        user_session.refresh_from_db()

        assert user_session.time_range.lower == self.mock_datetime_now
        assert not user_session.time_range.upper

    def test_create_update_user_session_update_user_session_with_time_range(self, user_session, monkeypatch):
        date = datetime(2015, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        user_session.time_range = DateTimeTZRange(lower=date)
        user_session.save()

        mock = MagicMock()
        mock.datetime.now.return_value = self.mock_datetime_now
        monkeypatch.setattr("rt_api.client.datetime", mock)

        create_update_user_session_by_sid(user_session.sid)
        user_session.refresh_from_db()

        assert user_session.time_range.lower == self.mock_datetime_now
        assert not user_session.time_range.upper

    def test_create_update_user_session_create_user_session(self, monkeypatch):
        mock = MagicMock()
        mock.datetime.now.return_value = self.mock_datetime_now
        monkeypatch.setattr("rt_api.client.datetime", mock)

        sid = hashlib.sha256(lorem_ipsum.words(4).encode()).hexdigest()[:20]
        create_update_user_session_by_sid(sid)
        user_session = UserSession.objects.get(sid=sid)

        assert user_session.time_range.lower == self.mock_datetime_now
        assert not user_session.time_range.upper

    @pytest.mark.parametrize(
        "user_sessions_with_time_range, expected",
        [
            (
                [
                    {
                        "upper": datetime.now(tz=timezone.utc) + timedelta(days=1),
                        "lower": datetime.now(tz=timezone.utc),
                    },
                    {
                        "upper": datetime.now(tz=timezone.utc) + timedelta(days=1),
                        "lower": datetime.now(tz=timezone.utc),
                    },
                    {
                        "upper": datetime.now(tz=timezone.utc) + timedelta(days=1),
                        "lower": datetime.now(tz=timezone.utc),
                    },
                    {
                        "upper": datetime.now(tz=timezone.utc) + timedelta(days=1),
                        "lower": datetime.now(tz=timezone.utc),
                    },
                    {
                        "upper": datetime.now(tz=timezone.utc) + timedelta(days=1),
                        "lower": datetime.now(tz=timezone.utc),
                    },
                ],
                5,
            )
        ],
        indirect=["user_sessions_with_time_range"],
    )
    def test_cleanup_usersessions_no_expired_user_sessions(self, user_sessions_with_time_range, expected):
        cleanup_usersessions()
        assert UserSession.objects.count() == expected

    @pytest.mark.parametrize(
        "user_sessions_with_time_range, expected",
        [
            (
                [
                    {
                        "upper": datetime.now(tz=timezone.utc),
                        "lower": datetime.now(tz=timezone.utc) - timedelta(days=7),
                    },
                    {
                        "upper": datetime.now(tz=timezone.utc),
                        "lower": datetime.now(tz=timezone.utc) - timedelta(days=7),
                    },
                    {
                        "upper": datetime.now(tz=timezone.utc),
                        "lower": datetime.now(tz=timezone.utc) - timedelta(days=4),
                    },
                    {
                        "upper": datetime.now(tz=timezone.utc),
                        "lower": datetime.now(tz=timezone.utc) - timedelta(days=3),
                    },
                    {
                        "upper": datetime.now(tz=timezone.utc),
                        "lower": datetime.now(tz=timezone.utc) - timedelta(days=1),
                    },
                ],
                3,
            ),
            (
                [
                    {
                        "upper": datetime.now(tz=timezone.utc),
                        "lower": datetime.now(tz=timezone.utc) - timedelta(days=7),
                    },
                    {
                        "upper": datetime.now(tz=timezone.utc),
                        "lower": datetime.now(tz=timezone.utc) - timedelta(days=7),
                    },
                    {
                        "upper": datetime.now(tz=timezone.utc),
                        "lower": datetime.now(tz=timezone.utc) - timedelta(days=7),
                    },
                    {
                        "upper": datetime.now(tz=timezone.utc),
                        "lower": datetime.now(tz=timezone.utc) - timedelta(days=7),
                    },
                    {
                        "upper": datetime.now(tz=timezone.utc),
                        "lower": datetime.now(tz=timezone.utc) - timedelta(days=1),
                    },
                ],
                1,
            ),
        ],
        indirect=["user_sessions_with_time_range"],
    )
    def test_cleanup_usersessions_with_expired_user_sessions(self, user_sessions_with_time_range, expected):
        cleanup_usersessions()
        assert UserSession.objects.count() == expected

    def test_update_user_session_user_session_with_no_time_range(self, user_session, monkeypatch):
        mock = MagicMock()
        mock.datetime.now.return_value = self.mock_datetime_now
        monkeypatch.setattr("rt_api.client.datetime", mock)

        update_user_session_by_sid(user_session.sid)
        user_session.refresh_from_db()

        assert user_session.time_range.lower == self.mock_datetime_now
        assert not user_session.time_range.upper

    def test_update_user_session_user_session_with_time_range(self, user_session, monkeypatch):
        mock = MagicMock()
        mock.datetime.now.return_value = self.mock_datetime_now
        monkeypatch.setattr("rt_api.client.datetime", mock)

        date = datetime(2009, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        user_session.time_range = DateTimeTZRange(lower=date)
        user_session.save()

        update_user_session_by_sid(user_session.sid)
        user_session.refresh_from_db()

        assert user_session.time_range.upper == self.mock_datetime_now
        assert user_session.time_range.lower == date

    def test_update_user_session_user_session_with_time_range_upper_as_none(self, user_session, monkeypatch):
        mock = MagicMock()
        mock.datetime.now.return_value = self.mock_datetime_now
        monkeypatch.setattr("rt_api.client.datetime", mock)

        user_session.time_range = DateTimeTZRange()
        user_session.save()

        update_user_session_by_sid(user_session.sid)
        user_session.refresh_from_db()

        assert user_session.time_range.upper == self.mock_datetime_now
        assert not user_session.time_range.lower

    @patch("rt_api.client.get_client_list_key")
    def test_remove_invalid_rt_services(self, mocked_client_list):
        remove_all_rt_services()
        current_service = "rt_api.172.18.0.8"
        redis_client.sadd(REALTIME_SERVICES_KEY, "rt_api.172.18.0.1")
        redis_client.sadd(REALTIME_SERVICES_KEY, "rt_api.172.18.0.2")
        redis_client.sadd(REALTIME_SERVICES_KEY, "rt_api.172.18.0.3")
        redis_client.sadd(REALTIME_SERVICES_KEY, current_service)

        services_list = redis_client.smembers(REALTIME_SERVICES_KEY)
        mocked_client_list.return_value = current_service

        remove_invalid_rt_service_key()

        assert len(services_list) == 4

        new_services_list = redis_client.smembers(REALTIME_SERVICES_KEY)

        assert bytes(current_service, "utf-8") in services_list
        assert len(new_services_list) == 1

    def test_update_client_with_profile_user(self, five_users):
        user = five_users[0]
        profile_user = five_users[1]
        user.act_as_profiles.add(profile_user)

        user_data = ClientData(
            username=user.username,
            sid=self.sid,
            bbox=None,
            tenant_id=self.tenant_settings.id,
            domain=self.tenant_settings.domain,
            user_id=user.id,
            profile_id=None,
        )

        add_client(self.sid, user_data)
        client_data = get_client(self.sid)
        assert client_data.profile_id is None
        assert client_data.username == user.username

        update_client(self.sid, profile_id=profile_user.id)
        client_data = get_client(self.sid)
        assert client_data.profile_id == profile_user.id
        assert client_data.username == profile_user.username
