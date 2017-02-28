from __future__ import unicode_literals

from django.db import models

class GpsPlusPositions(models.Model):

    def __iter__(self):
        for attr, value in self.__dict__.items():
            yield attr, value

    id_position = models.AutoField(primary_key=True)
    id_collar = models.IntegerField()
    acquisition_time = models.DateTimeField()
    scts = models.DateTimeField(blank=True, null=True)
    origin_code = models.CharField(max_length=1, blank=True, null=True)
    ecef_x = models.IntegerField(blank=True, null=True)
    ecef_y = models.IntegerField(blank=True, null=True)
    ecef_z = models.IntegerField(blank=True, null=True)
    latitude = models.FloatField(blank=True, null=True)
    longitude = models.FloatField(blank=True, null=True)
    height = models.IntegerField(blank=True, null=True)
    dop = models.FloatField(blank=True, null=True)
    id_fix_type = models.SmallIntegerField(blank=True, null=True)
    position_error = models.FloatField(blank=True, null=True)
    sat_count = models.SmallIntegerField(blank=True, null=True)
    ch01_sat_id = models.SmallIntegerField(blank=True, null=True)
    ch01_sat_cnr = models.SmallIntegerField(blank=True, null=True)
    ch02_sat_id = models.SmallIntegerField(blank=True, null=True)
    ch02_sat_cnr = models.SmallIntegerField(blank=True, null=True)
    ch03_sat_id = models.SmallIntegerField(blank=True, null=True)
    ch03_sat_cnr = models.SmallIntegerField(blank=True, null=True)
    ch04_sat_id = models.SmallIntegerField(blank=True, null=True)
    ch04_sat_cnr = models.SmallIntegerField(blank=True, null=True)
    ch05_sat_id = models.SmallIntegerField(blank=True, null=True)
    ch05_sat_cnr = models.SmallIntegerField(blank=True, null=True)
    ch06_sat_id = models.SmallIntegerField(blank=True, null=True)
    ch06_sat_cnr = models.SmallIntegerField(blank=True, null=True)
    ch07_sat_id = models.SmallIntegerField(blank=True, null=True)
    ch07_sat_cnr = models.SmallIntegerField(blank=True, null=True)
    ch08_sat_id = models.SmallIntegerField(blank=True, null=True)
    ch08_sat_cnr = models.SmallIntegerField(blank=True, null=True)
    ch09_sat_id = models.SmallIntegerField(blank=True, null=True)
    ch09_sat_cnr = models.SmallIntegerField(blank=True, null=True)
    ch10_sat_id = models.SmallIntegerField(blank=True, null=True)
    ch10_sat_cnr = models.SmallIntegerField(blank=True, null=True)
    ch11_sat_id = models.SmallIntegerField(blank=True, null=True)
    ch11_sat_cnr = models.SmallIntegerField(blank=True, null=True)
    ch12_sat_id = models.SmallIntegerField(blank=True, null=True)
    ch12_sat_cnr = models.SmallIntegerField(blank=True, null=True)
    id_mortality_status = models.SmallIntegerField(blank=True, null=True)
    activity = models.SmallIntegerField(blank=True, null=True)
    main_voltage = models.FloatField(blank=True, null=True)
    backup_voltage = models.FloatField(blank=True, null=True)
    temperature = models.FloatField(blank=True, null=True)
    transformed_x = models.FloatField(blank=True, null=True)
    transformed_y = models.FloatField(blank=True, null=True)

    class Meta:

        managed = False
        db_table = 'gps_plus_positions'
        unique_together = (('id_collar', 'acquisition_time', 'origin_code'),)
