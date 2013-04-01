# -*- coding: utf-8 -*-
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):

    def forwards(self, orm):

        # Changing field 'CarouselImg.href_words'
        db.alter_column('pages_carouselimg', 'href_words', self.gf('django.db.models.fields.CharField')(max_length=64, null=True))

        # Changing field 'CarouselImg.href_desc'
        db.alter_column('pages_carouselimg', 'href_desc', self.gf('django.db.models.fields.CharField')(max_length=128, null=True))

    def backwards(self, orm):

        # Changing field 'CarouselImg.href_words'
        db.alter_column('pages_carouselimg', 'href_words', self.gf('django.db.models.fields.CharField')(max_length=16, null=True))

        # Changing field 'CarouselImg.href_desc'
        db.alter_column('pages_carouselimg', 'href_desc', self.gf('django.db.models.fields.CharField')(max_length=64, null=True))

    models = {
        'pages.carouselimg': {
            'Meta': {'object_name': 'CarouselImg'},
            'href': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['pages.Page']", 'null': 'True', 'blank': 'True'}),
            'href_desc': ('django.db.models.fields.CharField', [], {'max_length': '128', 'null': 'True', 'blank': 'True'}),
            'href_words': ('django.db.models.fields.CharField', [], {'max_length': '64', 'null': 'True', 'blank': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'img': ('django.db.models.fields.files.ImageField', [], {'max_length': '100'}),
            'internal_name': ('django.db.models.fields.CharField', [], {'max_length': '64'})
        },
        'pages.page': {
            'Meta': {'object_name': 'Page'},
            'body': ('django.db.models.fields.TextField', [], {}),
            'body_in_hero': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'carousel_css': ('django.db.models.fields.CharField', [], {'default': "'custom'", 'max_length': '32'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'imgs': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'to': "orm['pages.CarouselImg']", 'null': 'True', 'blank': 'True'}),
            'main_nav': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'nav_pos': ('django.db.models.fields.IntegerField', [], {}),
            'slug': ('django.db.models.fields.SlugField', [], {'max_length': '64'}),
            'title': ('django.db.models.fields.CharField', [], {'max_length': '64'})
        }
    }

    complete_apps = ['pages']