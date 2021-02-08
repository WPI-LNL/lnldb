# Generated by Django 3.1.6 on 2021-02-07 22:52

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('data', '0007_auto_20201028_1405'),
    ]

    operations = [
        migrations.AddField(
            model_name='resizedredirect',
            name='name',
            field=models.CharField(blank=True, help_text='User friendly name', max_length=64, null=True),
        ),
        migrations.AddField(
            model_name='resizedredirect',
            name='sitemap',
            field=models.BooleanField(default=False, verbose_name='Include in Sitemap'),
        ),
    ]