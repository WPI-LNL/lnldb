# -*- coding: utf-8 -*-
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):
    def forwards(self, orm):
        # Adding model 'Page'
        db.create_table('pages_page', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('title', self.gf('django.db.models.fields.CharField')(max_length=64)),
            ('slug', self.gf('django.db.models.fields.SlugField')(max_length=64)),
            ('body', self.gf('django.db.models.fields.TextField')()),
            ('main_nav', self.gf('django.db.models.fields.BooleanField')(default=False)),
        ))
        db.send_create_signal('pages', ['Page'])

        # Adding M2M table for field imgs on 'Page'
        db.create_table('pages_page_imgs', (
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('page', models.ForeignKey(orm['pages.page'], null=False)),
            ('carouselimg', models.ForeignKey(orm['pages.carouselimg'], null=False))
        ))
        db.create_unique('pages_page_imgs', ['page_id', 'carouselimg_id'])

        # Adding model 'CarouselImg'
        db.create_table('pages_carouselimg', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('img', self.gf('django.db.models.fields.files.ImageField')(max_length=100)),
            ('href', self.gf('django.db.models.fields.CharField')(max_length=16)),
            ('href_desc', self.gf('django.db.models.fields.CharField')(max_length=64)),
        ))
        db.send_create_signal('pages', ['CarouselImg'])

    def backwards(self, orm):
        # Deleting model 'Page'
        db.delete_table('pages_page')

        # Removing M2M table for field imgs on 'Page'
        db.delete_table('pages_page_imgs')

        # Deleting model 'CarouselImg'
        db.delete_table('pages_carouselimg')

    models = {
        'pages.carouselimg': {
            'Meta': {'object_name': 'CarouselImg'},
            'href': ('django.db.models.fields.CharField', [], {'max_length': '16'}),
            'href_desc': ('django.db.models.fields.CharField', [], {'max_length': '64'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'img': ('django.db.models.fields.files.ImageField', [], {'max_length': '100'})
        },
        'pages.page': {
            'Meta': {'object_name': 'Page'},
            'body': ('django.db.models.fields.TextField', [], {}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'imgs': ('django.db.models.fields.related.ManyToManyField', [],
                     {'to': "orm['pages.CarouselImg']", 'symmetrical': 'False'}),
            'main_nav': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'slug': ('django.db.models.fields.SlugField', [], {'max_length': '64'}),
            'title': ('django.db.models.fields.CharField', [], {'max_length': '64'})
        }
    }

    complete_apps = ['pages']