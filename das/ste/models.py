# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey has `on_delete` set to the desired behavior.
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from __future__ import unicode_literals

from django.contrib.gis.db import models

class ArchiveLocManager(models.Manager):
    pass

class ArchiveLoc(models.Model):
    chronofile = models.ForeignKey('Trackingmaster', models.DO_NOTHING, db_column='chronofile')
    recordserial = models.BigIntegerField(primary_key=True)
    collar_id = models.TextField()
    fixtime = models.DateTimeField()
    dloadtime = models.DateTimeField()
    lon = models.FloatField()
    lat = models.FloatField()
    comments = models.TextField(blank=True, null=True)
    height = models.FloatField(blank=True, null=True)
    signal_strength = models.TextField(blank=True, null=True)
    convergence = models.TextField(blank=True, null=True)
    collar_speed = models.FloatField(blank=True, null=True)
    gsm_coverage = models.TextField(blank=True, null=True)
    temp = models.FloatField(blank=True, null=True)
    heading = models.FloatField(blank=True, null=True)
    ndvi = models.TextField(blank=True, null=True)
    dop = models.TextField(blank=True, null=True)
    fixstatus = models.SmallIntegerField(blank=True, null=True)
    act = models.TextField(blank=True, null=True)
    act1 = models.TextField(blank=True, null=True)
    act2 = models.TextField(blank=True, null=True)
    sat_id = models.TextField(blank=True, null=True)
    postgis = models.TextField(blank=True, null=True)

    class Meta:

        managed = False
        db_table = 'archive_loc'
        unique_together = (('chronofile', 'fixtime'), ('chronofile', 'recordserial'),)

    objects = ArchiveLocManager()

class Display(models.Model):
    displaygroup = models.TextField(primary_key=True)
    colour = models.TextField(blank=True, null=True)  # This field type is a guess.
    esrimarkericon = models.TextField(blank=True, null=True)
    googlemarkericon = models.TextField(blank=True, null=True)
    esripointstyle = models.TextField(blank=True, null=True)
    googlepointstyle = models.TextField(blank=True, null=True)
    esritrackstyle = models.TextField(blank=True, null=True)
    googletrackstyle = models.TextField(blank=True, null=True)
    logo = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'display'


class Geofencegroups(models.Model):
    geofencegroupname = models.TextField(primary_key=True)
    geofencenames = models.TextField()  # This field type is a guess.

    class Meta:
        managed = False
        db_table = 'geofencegroups'


class Geofencemaster(models.Model):
    chronofile = models.SmallIntegerField(primary_key=True)
    usegeofencing = models.BooleanField()
    searchtimehrs = models.FloatField()
    fencegroup = models.ForeignKey(Geofencegroups, models.DO_NOTHING, db_column='fencegroup', blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'geofencemaster'


class Htmlinfo(models.Model):
    displaygroup = models.ForeignKey(Display, models.DO_NOTHING, db_column='displaygroup', unique=True)
    usehtml = models.BooleanField()
    htmlcontent = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'htmlinfo'


class Mortalityprofiles(models.Model):
    chronofile = models.SmallIntegerField(primary_key=True)
    useprofile = models.BooleanField()
    radiusmeters = models.FloatField()
    timethresholdhrs = models.FloatField()
    pvalue = models.FloatField()
    searchtimehrs = models.FloatField()
    notes = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'mortalityprofiles'


class Proximitygroups(models.Model):
    proximitygroupname = models.TextField(primary_key=True)
    proximitynames = models.TextField()  # This field type is a guess.

    class Meta:
        managed = False
        db_table = 'proximitygroups'


class Proximitymaster(models.Model):
    chronofile = models.SmallIntegerField(primary_key=True)
    useproximity = models.BooleanField()
    searchtimehrs = models.FloatField()
    distthreshold = models.FloatField()
    proximitygroup = models.ForeignKey(Proximitygroups, models.DO_NOTHING, db_column='proximitygroup', blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'proximitymaster'


class RawTcp(models.Model):
    recordserial = models.BigIntegerField(primary_key=True)
    recievetime = models.DateTimeField()
    tcpstring = models.TextField(blank=True, null=True)
    senderip = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'raw_tcp'


class Regions(models.Model):
    chronofile = models.SmallIntegerField(primary_key=True)
    region = models.TextField(blank=True, null=True)
    country = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'regions'


class Speedprofiles(models.Model):
    chronofile = models.SmallIntegerField(primary_key=True)
    useprofile = models.BooleanField()
    percentile = models.FloatField()
    percentileval = models.FloatField()
    timewindowhrs = models.FloatField()
    trainingstart = models.DateTimeField(blank=True, null=True)
    trainingend = models.DateTimeField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'speedprofiles'


class TrackingmasterManager(models.Manager):
    pass

class Trackingmaster(models.Model):

    objects = TrackingmasterManager()

    chronofile = models.SmallIntegerField(primary_key=True)
    collar_type = models.TextField()
    collar_id = models.TextField()
    active = models.SmallIntegerField()
    datasource = models.TextField()
    frequency = models.FloatField(blank=True, null=True)
    animal_id = models.TextField(blank=True, null=True)
    name = models.TextField(blank=True, null=True)
    species = models.TextField()
    data_starts = models.DateTimeField(blank=True, null=True)
    data_stops = models.DateTimeField(blank=True, null=True)
    date_off_or_removed = models.TextField(blank=True, null=True)
    comments = models.TextField(blank=True, null=True)
    predicted_expiry = models.DateTimeField(blank=True, null=True)
    rgb = models.TextField(blank=True, null=True)
    sex = models.TextField(blank=True, null=True)
    gmt = models.DecimalField(max_digits=65535, decimal_places=65535, blank=True, null=True)
    utm = models.DecimalField(max_digits=65535, decimal_places=65535, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'trackingmaster'


class Trackingmasteraux(models.Model):
    chronofile = models.ForeignKey(Trackingmaster, models.DO_NOTHING, db_column='chronofile', primary_key=True)
    data_status = models.TextField(blank=True, null=True)
    data_starts_source = models.TextField(blank=True, null=True)
    data_stops_source = models.TextField(blank=True, null=True)
    data_stops_reason = models.TextField(blank=True, null=True)
    collar_status = models.TextField(blank=True, null=True)
    collar_model = models.TextField(blank=True, null=True)
    has_acc_data = models.NullBooleanField()
    data_owners = models.TextField(blank=True, null=True)  # This field type is a guess.
    adjusted_beacon_freq = models.FloatField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'trackingmasteraux'


class Trackingusers(models.Model):
    userid = models.AutoField(primary_key=True)
    username = models.TextField(unique=True)
    password = models.TextField()
    firstname = models.TextField(blank=True, null=True)
    lastname = models.TextField(blank=True, null=True)
    organization = models.TextField(blank=True, null=True)
    phonenumbers = models.TextField(blank=True, null=True)  # This field type is a guess.
    emails = models.TextField(blank=True, null=True)  # This field type is a guess.
    recievesystemreports = models.BooleanField()
    expiry = models.DateTimeField(blank=True, null=True)
    fulldataaccess = models.IntegerField()
    delay = models.IntegerField()
    notes = models.TextField(blank=True, null=True)
    chronofiles = models.TextField(blank=True, null=True)  # This field type is a guess.

    class Meta:
        managed = False
        db_table = 'trackingusers'


class Trackingusersaux(models.Model):
    username = models.ForeignKey(Trackingusers, models.DO_NOTHING, db_column='username', primary_key=True)
    newpassword = models.TextField(blank=True, null=True)
    subjectgroups = models.TextField(blank=True, null=True)  # This field type is a guess.
    moudatesigned = models.DateTimeField(blank=True, null=True)
    moutype = models.TextField(blank=True, null=True)
    moufilename = models.TextField(blank=True, null=True)
    tech = models.TextField(blank=True, null=True)  # This field type is a guess.

    class Meta:
        managed = False
        db_table = 'trackingusersaux'
