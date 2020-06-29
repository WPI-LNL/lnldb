# -*- coding: utf-8 -*-
# Generated by Django 1.11.29 on 2020-05-30 01:55
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pages', '0001_initial'),
    ]

    operations = [
        migrations.RenameField(
            model_name='carouselimg',
            old_name='href_desc',
            new_name='caption_desc',
        ),
        migrations.RenameField(
            model_name='carouselimg',
            old_name='href_words',
            new_name='caption_title',
        ),
        migrations.RenameField(
            model_name='page',
            old_name='body_in_hero',
            new_name='body_in_jumbo',
        ),
        migrations.RemoveField(
            model_name='page',
            name='carousel_css',
        ),
        migrations.RemoveField(
            model_name='page',
            name='main_nav',
        ),
        migrations.RemoveField(
            model_name='page',
            name='nav_pos',
        ),
        migrations.AddField(
            model_name='page',
            name='css',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='page',
            name='description',
            field=models.TextField(blank=True, help_text=b'This page description may appear in search engine results and along with any links to this page.'),
        ),
        migrations.AddField(
            model_name='page',
            name='noindex',
            field=models.BooleanField(default=False, verbose_name=b'Hide from search engines'),
        ),
        migrations.AlterField(
            model_name='page',
            name='body',
            field=models.TextField(help_text=b'Accepts raw text and/or HTML input'),
        ),
    ]