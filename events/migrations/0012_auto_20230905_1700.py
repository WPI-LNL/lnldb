# Generated by Django 3.1.14 on 2023-09-05 21:00

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0011_auto_20230905_1623'),
    ]

    operations = [
        migrations.AlterField(
            model_name='baseevent',
            name='event_status',
            field=models.CharField(choices=[('Pre-Request', 'Pre-Request'), ('Prospective', 'Prospective'), ('Incoming', 'Incoming'), ('Confirmed', 'Confirmed'), ('Post Event', 'Post Event')], default='Prospective', max_length=20),
        ),
    ]
