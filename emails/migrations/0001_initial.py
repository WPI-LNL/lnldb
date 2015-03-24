# -*- coding: utf-8 -*-
from south.db import db
from south.v2 import SchemaMigration


class Migration(SchemaMigration):
    def forwards(self, orm):
        # Adding model 'MeetingNoticeMail'
        db.create_table(u'emails_meetingnoticemail', (
            (u'id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('ts', self.gf('django.db.models.fields.DateTimeField')(auto_now_add=True, blank=True)),
            ('place', self.gf('django.db.models.fields.CharField')(default='AK219', max_length=32)),
            ('time', self.gf('django.db.models.fields.TimeField')(default='17:00')),
            ('date', self.gf('django.db.models.fields.DateField')()),
            ('note', self.gf('django.db.models.fields.TextField')()),
            ('start_param', self.gf('django.db.models.fields.DateField')()),
            ('end_param', self.gf('django.db.models.fields.DateField')()),
            ('sent', self.gf('django.db.models.fields.BooleanField')(default=False)),
        ))
        db.send_create_signal(u'emails', ['MeetingNoticeMail'])

    def backwards(self, orm):
        # Deleting model 'MeetingNoticeMail'
        db.delete_table(u'emails_meetingnoticemail')

    models = {
        u'emails.meetingnoticemail': {
            'Meta': {'object_name': 'MeetingNoticeMail'},
            'date': ('django.db.models.fields.DateField', [], {}),
            'end_param': ('django.db.models.fields.DateField', [], {}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'note': ('django.db.models.fields.TextField', [], {}),
            'place': ('django.db.models.fields.CharField', [], {'default': "'AK219'", 'max_length': '32'}),
            'sent': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'start_param': ('django.db.models.fields.DateField', [], {}),
            'time': ('django.db.models.fields.TimeField', [], {'default': "'17:00'"}),
            'ts': ('django.db.models.fields.DateTimeField', [], {'auto_now_add': 'True', 'blank': 'True'})
        }
    }

    complete_apps = ['emails']