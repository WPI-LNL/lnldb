# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):
    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='CarouselImg',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('internal_name', models.CharField(max_length=64)),
                ('img', models.ImageField(upload_to=b'carousel')),
                ('href_words', models.CharField(max_length=64, null=True, blank=True)),
                ('href_desc', models.CharField(max_length=128, null=True, blank=True)),
            ],
        ),
        migrations.CreateModel(
            name='Page',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('title', models.CharField(max_length=64)),
                ('slug', models.SlugField(max_length=64)),
                ('body', models.TextField()),
                ('body_in_hero', models.BooleanField(default=False)),
                ('main_nav', models.BooleanField(default=False)),
                ('nav_pos', models.IntegerField()),
                ('carousel_css', models.CharField(default=b'custom', max_length=32)),
                ('imgs', models.ManyToManyField(to='pages.CarouselImg', blank=True)),
            ],
        ),
        migrations.AddField(
            model_name='carouselimg',
            name='href',
            field=models.ForeignKey(blank=True, to='pages.Page', null=True),
        ),
    ]
