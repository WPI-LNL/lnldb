# -*- coding: utf-8 -*-
from south.db import db
from south.v2 import SchemaMigration


class Migration(SchemaMigration):
    def forwards(self, orm):
        # Adding field 'Page.nav_pos'
        db.add_column('pages_page', 'nav_pos',
                      self.gf('django.db.models.fields.IntegerField')(default=0),
                      keep_default=False)

    def backwards(self, orm):
        # Deleting field 'Page.nav_pos'
        db.delete_column('pages_page', 'nav_pos')

    models = {
        'pages.carouselimg': {
            'Meta': {'object_name': 'CarouselImg'},
            'href': ('django.db.models.fields.related.ForeignKey', [],
                     {'to': "orm['pages.Page']", 'null': 'True', 'blank': 'True'}),
            'href_desc': (
                'django.db.models.fields.CharField', [], {'max_length': '64', 'null': 'True', 'blank': 'True'}),
            'href_words': (
                'django.db.models.fields.CharField', [], {'max_length': '16', 'null': 'True', 'blank': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'img': ('django.db.models.fields.files.ImageField', [], {'max_length': '100'}),
            'internal_name': ('django.db.models.fields.CharField', [], {'max_length': '64'})
        },
        'pages.page': {
            'Meta': {'object_name': 'Page'},
            'body': ('django.db.models.fields.TextField', [], {}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'imgs': ('django.db.models.fields.related.ManyToManyField', [],
                     {'to': "orm['pages.CarouselImg']", 'symmetrical': 'False'}),
            'main_nav': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'nav_pos': ('django.db.models.fields.IntegerField', [], {}),
            'slug': ('django.db.models.fields.SlugField', [], {'max_length': '64'}),
            'title': ('django.db.models.fields.CharField', [], {'max_length': '64'})
        }
    }

    complete_apps = ['pages']
