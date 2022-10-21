# Generated by Django 2.2.11 on 2020-05-16 13:50

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('choices', '0013_auto_20200310_1826'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='actiontaken',
            options={'verbose_name': 'Action Taken', 'verbose_name_plural': 'Actions Taken'},
        ),
        migrations.AlterModelOptions(
            name='animalsex',
            options={'verbose_name': 'Animal Sex', 'verbose_name_plural': 'Animal Sexes'},
        ),
        migrations.AlterModelOptions(
            name='causeofdeath',
            options={'verbose_name': 'Cause of Death', 'verbose_name_plural': 'Causes of Death'},
        ),
        migrations.AlterModelOptions(
            name='conservancy',
            options={'verbose_name': 'Conservancy', 'verbose_name_plural': 'Conservancies'},
        ),
        migrations.AlterModelOptions(
            name='crops',
            options={'verbose_name': 'Crops', 'verbose_name_plural': 'Crops'},
        ),
        migrations.AlterModelOptions(
            name='fencedamage',
            options={'verbose_name': 'Fence Damage', 'verbose_name_plural': 'Fence Damage'},
        ),
        migrations.AlterModelOptions(
            name='firestatus',
            options={'verbose_name': 'Fire Status', 'verbose_name_plural': 'Fire Statuses'},
        ),
        migrations.AlterModelOptions(
            name='health',
            options={'verbose_name': 'Health', 'verbose_name_plural': 'Health'},
        ),
        migrations.AlterModelOptions(
            name='illegalactivity',
            options={'verbose_name': 'Illegal Activity', 'verbose_name_plural': 'Illegal Activities'},
        ),
        migrations.AlterModelOptions(
            name='keyspecies',
            options={'verbose_name': 'Key Species', 'verbose_name_plural': 'Key Species'},
        ),
        migrations.AlterModelOptions(
            name='livestock',
            options={'verbose_name': 'Livestock', 'verbose_name_plural': 'Livestock'},
        ),
        migrations.AlterModelOptions(
            name='medicalequipmentrequired',
            options={'verbose_name': 'Medical Equipment Required', 'verbose_name_plural': 'Medical Equipment Required'},
        ),
        migrations.AlterModelOptions(
            name='medicalevacsecurity',
            options={'verbose_name': 'Medical Evac Security', 'verbose_name_plural': 'Medical Evac Securities'},
        ),
        migrations.AlterModelOptions(
            name='snarestatus',
            options={'verbose_name': 'Snare Status', 'verbose_name_plural': 'Snare Statuses'},
        ),
        migrations.AlterModelOptions(
            name='species',
            options={'verbose_name': 'Species', 'verbose_name_plural': 'Species'},
        ),
        migrations.AlterModelOptions(
            name='trackstype',
            options={'verbose_name': 'Track Type', 'verbose_name_plural': 'Track Types'},
        ),
        migrations.AlterModelOptions(
            name='trafficactivity',
            options={'verbose_name': 'Traffic Activity', 'verbose_name_plural': 'Traffic Activities'},
        ),
        migrations.AlterModelOptions(
            name='trophystatus',
            options={'verbose_name': 'Trophy Status', 'verbose_name_plural': 'Trophy Statuses'},
        ),
        migrations.AlterModelOptions(
            name='typeofillegalactivity',
            options={'verbose_name': 'Type of Illegal Activity', 'verbose_name_plural': 'Type of Illegal Activities'},
        ),
        migrations.AlterModelOptions(
            name='typeofshots',
            options={'verbose_name': 'Type of Shots', 'verbose_name_plural': 'Type of Shots'},
        ),
        migrations.AlterModelOptions(
            name='typeoftrophy',
            options={'verbose_name': 'Type of Trophy', 'verbose_name_plural': 'Type of Trophies'},
        ),
        migrations.AlterModelOptions(
            name='vehicletypes',
            options={'verbose_name': 'Vehicle Types', 'verbose_name_plural': 'Vehicle Types'},
        ),
        migrations.AlterModelOptions(
            name='weapontypes',
            options={'verbose_name': 'Types of Weapons', 'verbose_name_plural': 'Types of Weapons'},
        ),
        migrations.AlterField(
            model_name='choice',
            name='model',
            field=models.CharField(choices=[('activity.eventtype', 'Field Report Type'), ('activity.event', 'Field Reports'), ('mapping.TileLayer', 'Maps'), ('observations.region', 'Region'), ('observations.Source', 'Sources'), ('accounts.user.User', 'User')], default='activity.event', max_length=50),
        ),
    ]
