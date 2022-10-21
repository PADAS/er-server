# Generated by hand on 2018-07-11

from django.db import migrations, models

# Prior to adding default-priority to EventType, we relied on web-code to map event-type to default-priority.
# This update query includes a table expression that is constructed from the existing web-code (as of July 2018).
# Essentially this expression maps all of our known event-type values to what we want to default priority to be.
# A particular site will only include a small subset of these event-types.
SET_DEFAULT_PRIORITIES = '''

with t0 as (select * from (values ('default', 0),
    ('trespass', 300),
    ('mist', 300),
    ('mist_rep', 300),
    ('_mist_rep', 300),
    ('fire', 300),
    ('fire_rep', 300),
    ('_fire_rep', 300),
    ('firms_rep', 100),
    ('arrest', 100),
    ('arrest_rep', 0),
    ('_arrest_rep', 100),
    ('more', 0),
    ('sit_rep', 0),
    ('_sit_rep', 0),
    ('illegal_activity', 300),
    ('activity_rep', 300),
    ('hostile', 300),
    ('contact', 200),
    ('contact_rep', 300),
    ('_contact_rep', 200),
    ('gunshot', 300),
    ('shot_rep', 300),
    ('_shot_rep', 300),
    ('other', 0),
    ('incident_collection', 0),
    ('event-icon', 0),
    ('tribal_conflict', 200),
    ('conflict', 300),
    ('poaching', 300),
    ('snare', 200),
    ('snare_rep', 200),
    ('_snare_rep', 200),
    ('poacher_camp', 300),
    ('poacher_camp_rep', 300),
    ('_poacher_camp_rep', 300),
    ('wildlife_sighting', 0),
    ('wildlife_sighting_rep', 0),
    ('_wildlife_sighting_rep', 0),
    ('vehicle_accident', 200),
    ('all_posts', 0),
    ('post_rep', 0),
    ('all_posts_rep', 0),
    ('civil_unrest', 200),
    ('threat', 200),
    ('complaint', 200),
    ('animal_accident', 200),
    ('drowning', 200),
    ('medevac_request', 300),
    ('_medevac_rep', 300),
    ('medevac_rep', 300),
    ('traf_rep', 200),
    ('traffic_rep', 200),
    ('_traf_rep', 200),
    ('spoor', 0),
    ('spoor_rep', 300),
    ('_spoor_rep', 0),
    ('shot_rep_ranger', 100),
    ('ranger_shot_rep', 100),
    ('_ranger_shot_rep', 100),
    ('loss_of_human_life', 300),
    ('loss_of_animal_life', 200),
    ('recovered_firearms', 100),
    ('human_wildlife_conflict', 300),
    ('hwc_rep', 0),
    ('tourist_attack', 300),
    ('missing_person', 300),
    ('recovered_trophies', 100),
    ('_recovered_trophies_rep', 100),
    ('road_banditry', 300),
    ('stock_theft', 200),
    ('accident', 200),
    ('accident_rep', 200),
    ('_accident_rep', 200),
    ('robbery_theft', 300),
    ('rhino_sighting_rep', 0),
    ('black_rhino_sighting', 0),
    ('white_rhino_sighting', 0),
    ('rhino_birth', 100),
    ('rhino_territorial_movement', 0),
    ('other_wildlife_sightings_old', 0),
    ('wildlife_gap_movement', 0),
    ('rainfall_report', 0),
    ('rainfall_rep', 0),
    ('rainfall_report_rep', 0),
    ('radio_room_report', 0),
    ('radio_report_rep', 0),
    ('radio_rep', 0),
    ('fence_report', 0),
    ('fence_breakage', 200),
    ('fence_rep', 0),
    ('fence_report_rep', 0),
    ('injured_animal', 300),
    ('injured_animal_rep', 300),
    ('_injured_animal_rep', 300),
    ('elephant_sighting', 0),
    ('elephant_sighting_rep', 0),
    ('lion_sighting', 0),
    ('other_wildlife_sightings', 0),
    ('leopard_sighting', 0),
    ('dog_immobilisation', 300),
    ('confiscations', 100),
    ('confiscation_rep', 100),
    ('confiscations_rep', 100),
    ('confiscations_repc', 100),
    ('animal_control', 100),
    ('critical_sightings', 100),
    ('detection', 200),
    ('detection_rep', 200),
    ('animal_control_rep', 300),
    ('arrivee_camp_nuit', 300),
    ('carcass', 200),
    ('carcass_rep', 200),
    ('wildlife_mortality_rep', 100),
    ('_carcass_rep', 200),
    ('elephant_mortality_rep', 300),
    ('invasive_species_rep', 200),
    ('water_level_rep', 0),
    ('suspicious_person_rep', 200),
    ('road_status_rep', 0),
    ('critical_sightings_rep', 100),
    ('light_rep', 200),
    ('burn_rep', 0),
    ('plant_control_rep', 0),
    ('scholarship', 0),
    ('HWC_follow_up', 0),
    ('tse_tse_status', 0),
    ('migration_rep', 0),
    ('rhino_boma_rep', 0),
    ('hwc_alert_rep', 300),
    ('cameratrap_rep', 300),
    ('geofence', 300),
    ('proximity_ele', 200),
    ('proximity_ele_all_clear', 100),
    ('proximity', 0),
    ('proximity_all_clear', 100),
    ('high_speed', 200),
    ('high_speed_all_clear', 100),
    ('low_speed', 200),
    ('low_speed_all_clear', 100),
    ('immobility', 200),
    ('immobility_all_clear', 100),
    ('geofence_break', 300),
    ('low_speed_percentile', 200),
    ('low_speed_percentile_all_clear', 100),
    ('low_speed_wilcoxon', 200),
    ('low_speed_wilcoxon_all_clear', 100)
    ) as t0 (event_type, priority))
update activity_eventtype et
    set default_priority = t0.priority
  from t0 
    where et.value = t0.event_type;
'''


class Migration(migrations.Migration):

    dependencies = [
        ('activity', '0071_eventsource'),
    ]

    operations = [
        migrations.RunSQL(sql=SET_DEFAULT_PRIORITIES,
                          reverse_sql=migrations.RunSQL.noop)
    ]
