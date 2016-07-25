-- Run this file on the vectronics database to create the trigger function and notification that DAS will listen for

CREATE OR REPLACE FUNCTION positions_trigger_function() RETURNS TRIGGER AS
$gps_plus_positions$
BEGIN
    PERFORM pg_notify('das_vectronics_position_notification', NEW.id_position::text);
    RETURN NEW;
END;
$gps_plus_positions$
LANGUAGE plpgsql;


CREATE TRIGGER positions_update_trigger AFTER INSERT OR UPDATE on gps_plus_positions FOR EACH ROW EXECUTE PROCEDURE positions_trigger_function();