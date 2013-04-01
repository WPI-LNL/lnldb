# -*- coding: utf-8 -*-
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):

    def forwards(self, orm):
        # Deleting field 'Event.time_setup_start'
        db.delete_column('events_event', 'time_setup_start')

        # Deleting field 'Event.time_setup_up'
        db.delete_column('events_event', 'time_setup_up')

        # Deleting field 'Event.date_setup_start'
        db.delete_column('events_event', 'date_setup_start')

        # Adding field 'Event.datetime_setup_start'
        db.add_column('events_event', 'datetime_setup_start',
                      self.gf('django.db.models.fields.DateTimeField')(default=datetime.datetime(2013, 2, 19, 0, 0)),
                      keep_default=False)

        # Adding field 'Event.datetime_setup_complete'
        db.add_column('events_event', 'datetime_setup_complete',
                      self.gf('django.db.models.fields.DateTimeField')(default=datetime.datetime(2013, 2, 19, 0, 0)),
                      keep_default=False)


    def backwards(self, orm):
        # Adding field 'Event.time_setup_start'
        db.add_column('events_event', 'time_setup_start',
                      self.gf('django.db.models.fields.TimeField')(default=datetime.datetime(2013, 2, 19, 0, 0)),
                      keep_default=False)

        # Adding field 'Event.time_setup_up'
        db.add_column('events_event', 'time_setup_up',
                      self.gf('django.db.models.fields.TimeField')(default=datetime.datetime(2013, 2, 19, 0, 0)),
                      keep_default=False)

        # Adding field 'Event.date_setup_start'
        db.add_column('events_event', 'date_setup_start',
                      self.gf('django.db.models.fields.DateField')(default=datetime.datetime(2013, 2, 19, 0, 0)),
                      keep_default=False)

        # Deleting field 'Event.datetime_setup_start'
        db.delete_column('events_event', 'datetime_setup_start')

        # Deleting field 'Event.datetime_setup_complete'
        db.delete_column('events_event', 'datetime_setup_complete')


    models = {
        'auth.group': {
            'Meta': {'object_name': 'Group'},
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '80'}),
            'permissions': ('django.db.models.fields.related.ManyToManyField', [], {'to': "orm['auth.Permission']", 'symmetrical': 'False', 'blank': 'True'})
        },
        'auth.permission': {
            'Meta': {'ordering': "('content_type__app_label', 'content_type__model', 'codename')", 'unique_together': "(('content_type', 'codename'),)", 'object_name': 'Permission'},
            'codename': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'content_type': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['contenttypes.ContentType']"}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '50'})
        },
        'auth.user': {
            'Meta': {'object_name': 'User'},
            'date_joined': ('django.db.models.fields.DateTimeField', [], {'default': 'datetime.datetime.now'}),
            'email': ('django.db.models.fields.EmailField', [], {'max_length': '75', 'blank': 'True'}),
            'first_name': ('django.db.models.fields.CharField', [], {'max_length': '30', 'blank': 'True'}),
            'groups': ('django.db.models.fields.related.ManyToManyField', [], {'to': "orm['auth.Group']", 'symmetrical': 'False', 'blank': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'is_active': ('django.db.models.fields.BooleanField', [], {'default': 'True'}),
            'is_staff': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'is_superuser': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'last_login': ('django.db.models.fields.DateTimeField', [], {'default': 'datetime.datetime.now'}),
            'last_name': ('django.db.models.fields.CharField', [], {'max_length': '30', 'blank': 'True'}),
            'password': ('django.db.models.fields.CharField', [], {'max_length': '128'}),
            'user_permissions': ('django.db.models.fields.related.ManyToManyField', [], {'to': "orm['auth.Permission']", 'symmetrical': 'False', 'blank': 'True'}),
            'username': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '30'})
        },
        'contenttypes.contenttype': {
            'Meta': {'ordering': "('name',)", 'unique_together': "(('app_label', 'model'),)", 'object_name': 'ContentType', 'db_table': "'django_content_type'"},
            'app_label': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'model': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '100'})
        },
        'events.event': {
            'Meta': {'ordering': "['-datetime_start']", 'object_name': 'Event'},
            'approved': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'closed': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'contact_addr': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'contact_email': ('django.db.models.fields.CharField', [], {'max_length': '256', 'null': 'True', 'blank': 'True'}),
            'contact_phone': ('django.db.models.fields.CharField', [], {'max_length': '32', 'null': 'True', 'blank': 'True'}),
            'crew': ('django.db.models.fields.related.ManyToManyField', [], {'blank': 'True', 'related_name': "'crew'", 'null': 'True', 'symmetrical': 'False', 'to': "orm['auth.User']"}),
            'crew_chief': ('django.db.models.fields.related.ManyToManyField', [], {'blank': 'True', 'related_name': "'crewchief'", 'null': 'True', 'symmetrical': 'False', 'to': "orm['auth.User']"}),
            'datetime_end': ('django.db.models.fields.DateTimeField', [], {}),
            'datetime_setup_complete': ('django.db.models.fields.DateTimeField', [], {}),
            'datetime_setup_start': ('django.db.models.fields.DateTimeField', [], {}),
            'datetime_start': ('django.db.models.fields.DateTimeField', [], {}),
            'description': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'event_name': ('django.db.models.fields.CharField', [], {'max_length': '128'}),
            'group': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'to': "orm['events.Organization']", 'null': 'True', 'blank': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'lighting': ('django.db.models.fields.related.ForeignKey', [], {'blank': 'True', 'related_name': "'lighting'", 'null': 'True', 'to': "orm['events.Lighting']"}),
            'location': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['events.Location']"}),
            'paid': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'payment_amount': ('django.db.models.fields.IntegerField', [], {'default': 'None', 'null': 'True', 'blank': 'True'}),
            'person_name': ('django.db.models.fields.CharField', [], {'max_length': '128', 'null': 'True', 'blank': 'True'}),
            'projection': ('django.db.models.fields.CharField', [], {'max_length': '2', 'null': 'True', 'blank': 'True'}),
            'report': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'sound': ('django.db.models.fields.related.ForeignKey', [], {'blank': 'True', 'related_name': "'projection'", 'null': 'True', 'to': "orm['events.Projection']"}),
            'submitted_by': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'submitter'", 'to': "orm['auth.User']"}),
            'submitted_ip': ('django.db.models.fields.IPAddressField', [], {'max_length': '15'})
        },
        'events.extra': {
            'Meta': {'object_name': 'Extra'},
            'cost': ('django.db.models.fields.DecimalField', [], {'max_digits': '8', 'decimal_places': '2'}),
            'desc': ('django.db.models.fields.TextField', [], {}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '64'})
        },
        'events.extrainstance': {
            'Meta': {'object_name': 'ExtraInstance'},
            'event': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['events.Event']"}),
            'extra': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['events.Extra']"}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'quant': ('django.db.models.fields.IntegerField', [], {})
        },
        'events.lighting': {
            'Meta': {'object_name': 'Lighting', '_ormbases': ['events.Service']},
            'service_ptr': ('django.db.models.fields.related.OneToOneField', [], {'to': "orm['events.Service']", 'unique': 'True', 'primary_key': 'True'})
        },
        'events.location': {
            'Meta': {'object_name': 'Location'},
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '64'})
        },
        'events.organization': {
            'Meta': {'object_name': 'Organization'},
            'account': ('django.db.models.fields.IntegerField', [], {'default': '71973'}),
            'address': ('django.db.models.fields.TextField', [], {}),
            'associated_orgs': ('django.db.models.fields.related.ManyToManyField', [], {'blank': 'True', 'related_name': "'associated_orgs_rel_+'", 'null': 'True', 'to': "orm['events.Organization']"}),
            'associated_users': ('django.db.models.fields.related.ManyToManyField', [], {'related_name': "'orgusers'", 'symmetrical': 'False', 'to': "orm['auth.User']"}),
            'email': ('django.db.models.fields.EmailField', [], {'max_length': '75', 'null': 'True', 'blank': 'True'}),
            'email_exec': ('django.db.models.fields.BooleanField', [], {'default': 'True'}),
            'email_normal': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'exec_email': ('django.db.models.fields.EmailField', [], {'max_length': '75', 'null': 'True', 'blank': 'True'}),
            'fund': ('django.db.models.fields.IntegerField', [], {}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '128'}),
            'organization': ('django.db.models.fields.IntegerField', [], {}),
            'phone': ('django.db.models.fields.CharField', [], {'max_length': '32'}),
            'user_in_charge': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'orgowner'", 'to': "orm['auth.User']"})
        },
        'events.projection': {
            'Meta': {'object_name': 'Projection', '_ormbases': ['events.Service']},
            'service_ptr': ('django.db.models.fields.related.OneToOneField', [], {'to': "orm['events.Service']", 'unique': 'True', 'primary_key': 'True'})
        },
        'events.service': {
            'Meta': {'object_name': 'Service'},
            'cost': ('django.db.models.fields.DecimalField', [], {'max_digits': '8', 'decimal_places': '2'}),
            'extra': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'to': "orm['events.Extra']", 'null': 'True', 'blank': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'longname': ('django.db.models.fields.CharField', [], {'max_length': '64'}),
            'shortname': ('django.db.models.fields.CharField', [], {'max_length': '2'})
        },
        'events.sound': {
            'Meta': {'object_name': 'Sound', '_ormbases': ['events.Service']},
            'service_ptr': ('django.db.models.fields.related.OneToOneField', [], {'to': "orm['events.Service']", 'unique': 'True', 'primary_key': 'True'})
        }
    }

    complete_apps = ['events']