from django.db import migrations

sql_create_fks = """
DO
$$
    BEGIN
            -- RE-CREATE FK
            alter table auth_permission
                add constraint auth_permission_content_type_id_2f476e4b_fk_django_co
                    foreign key (content_type_id) references django_content_type
                        deferrable initially deferred;
            alter table django_admin_log
                add constraint django_admin_log_content_type_id_c4bce8eb_fk_django_co
                    foreign key (content_type_id) references django_content_type
                        deferrable initially deferred;
            alter table activity_event
                add constraint activity_event_reported_by_content__81040fb0_fk_django_co
                    foreign key (reported_by_content_type_id) references django_content_type
                        deferrable initially deferred;
            alter table activity_eventattachment
                add constraint activity_eventattach_content_type_id_b6440fce_fk_django_co
                    foreign key (content_type_id) references django_content_type
                        deferrable initially deferred;
            alter table activity_eventfile
                add constraint activity_eventfile_usercontent_type_id_b3a3b1ed_fk_django_co
                    foreign key (usercontent_type_id) references django_content_type
                        deferrable initially deferred;
            alter table activity_patrolfile
                add constraint activity_patrolfile_usercontent_type_id_031d6880_fk_django_co
                    foreign key (usercontent_type_id) references django_content_type
                        deferrable initially deferred;
            alter table activity_patrolsegment
                add constraint activity_patrolsegme_leader_content_type__165f10e0_fk_django_co
                    foreign key (leader_content_type_id) references django_content_type
                        deferrable initially deferred;
            alter table analyzers_subjectanalyzerresult
                add constraint analyzers_subjectana_subject_analyzer_con_864bc490_fk_django_co
                    foreign key (subject_analyzer_content_type_id) references django_content_type
                        deferrable initially deferred;
            alter table observations_message
                add constraint observations_message_receiver_content_typ_56719c81_fk_django_co
                    foreign key (receiver_content_type_id) references django_content_type
                        deferrable initially deferred;
            alter table observations_message
                add constraint observations_message_sender_content_type__ec59feb7_fk_django_co
                    foreign key (sender_content_type_id) references django_content_type
                        deferrable initially deferred;
            alter table tracking_sourceplugin
                add constraint tracking_sourceplugi_plugin_type_id_0e392da4_fk_django_co
                    foreign key (plugin_type_id) references django_content_type
                        deferrable initially deferred;
    END
$$
"""


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0017_set_base_content_types"),
    ]

    operations = [
        migrations.RunSQL(
            sql=sql_create_fks,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
