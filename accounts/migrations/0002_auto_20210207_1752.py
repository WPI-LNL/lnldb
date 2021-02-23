# Generated by Django 3.1.6 on 2021-02-07 22:52

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='carrier',
            field=models.CharField(blank=True, choices=[('', 'Opt-out'), ('txt.att.net', 'AT&T'), ('myboostmobile.com', 'Boost Mobile'), ('mms.cricketwireless.net', 'Cricket'), ('msg.fi.google.com', 'Google Fi'), ('mymetropcs.com', 'Metro PCS'), ('mmst5.tracfone.com', 'Simple Mobile'), ('messaging.sprintpcs.com', 'Sprint'), ('tmomail.net', 'T-Mobile'), ('vtext.com', 'Verizon'), ('vmobl.com', 'Virgin Mobile'), ('vmobile.ca', 'Virgin Mobile Canada'), ('vtext.com', 'Xfinity Mobile')], default='', help_text='By selecting your cellular carrier you consent to receiving text messages from LNL', max_length=25, null=True, verbose_name='Cellular Carrier'),
        ),
    ]