/* psql -h localhost -U postgres -d dasdb -f .\purge_event.sql -v event_id="'3f05032b-f7d5-4870-87a8-24f9d86126fe'" */
BEGIN;
DELETE FROM activity_eventattachment WHERE event_id = :event_id;
DELETE FROM activity_eventattachmentrevision WHERE object_id = :event_id;

DELETE FROM activity_eventnote WHERE event_id = :event_id;
DELETE FROM activity_eventnoterevision WHERE object_id = :event_id;

DELETE FROM activity_eventphoto WHERE event_id = :event_id;
DELETE FROM activity_eventphotorevision WHERE object_id = :event_id;

DELETE FROM activity_eventrevision WHERE object_id = :event_id;
DELETE FROM activity_event WHERE id = :event_id;

COMMIT;