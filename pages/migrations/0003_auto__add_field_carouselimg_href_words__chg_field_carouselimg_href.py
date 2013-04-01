# -*- coding: utf-8 -*-
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):

    def forwards(self, orm):
        # Adding field 'CarouselImg.href_words'
        db.add_column('pages_carouselimg', 'href_words',
                      self.gf('django.db.models.fields.CharField')(default='', max_length=16),
                      keep_default=False)


        # Renaming column for 'CarouselImg.href' to match new field type.
        db.rename_column('pages_carouselimg', 'href', 'href_id')
        # Changing field 'CarouselImg.href'
        db.alter_column('pages_carouselimg', 'href_id', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['pages.Page']))
        # Adding index on 'CarouselImg', fields ['href']
        db.create_index('pages_carouselimg', ['href_id'])


    def backwards(self, orm):
        # Removing index on 'CarouselImg', fields ['href']
        db.delete_index('pages_carouselimg', ['href_id'])

        # Deleting field 'CarouselImg.href_words'
        db.delete_column('pages_carouselimg', 'href_words')


        # Renaming column for 'CarouselImg.href' to match new field type.
        db.rename_column('pages_carouselimg', 'href_id', 'href')
        # Changing field 'CarouselImg.href'
        db.alter_column('pages_carouselimg', 'href', self.gf('django.db.models.fields.CharField')(max_length=16))

    models = {
        'pages.carouselimg': {
            'Meta': {'object_name': 'CarouselImg'},
            'href': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['pages.Page']"}),
            'href_desc': ('django.db.models.fields.CharField', [], {'max_length': '64'}),
            'href_words': ('django.db.models.fields.CharField', [], {'max_length': '16'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'img': ('django.db.models.fields.files.ImageField', [], {'max_length': '100'}),
            'internal_name': ('django.db.models.fields.CharField', [], {'max_length': '64'})
        },
        'pages.page': {
            'Meta': {'object_name': 'Page'},
            'body': ('django.db.models.fields.TextField', [], {}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'imgs': ('django.db.models.fields.related.ManyToManyField', [], {'to': "orm['pages.CarouselImg']", 'symmetrical': 'False'}),
            'main_nav': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'slug': ('django.db.models.fields.SlugField', [], {'max_length': '64'}),
            'title': ('django.db.models.fields.CharField', [], {'max_length': '64'})
        }
    }

    complete_apps = ['pages']