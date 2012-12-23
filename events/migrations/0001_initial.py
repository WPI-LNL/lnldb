# -*- coding: utf-8 -*-
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):

    def forwards(self, orm):
        # Adding model 'Location'
        db.create_table('events_location', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('name', self.gf('django.db.models.fields.CharField')(max_length=64)),
        ))
        db.send_create_signal('events', ['Location'])

        # Adding model 'Event'
        db.create_table('events_event', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('submitted_by', self.gf('django.db.models.fields.related.ForeignKey')(related_name='submitter', to=orm['auth.User'])),
            ('submitted_ip', self.gf('django.db.models.fields.IPAddressField')(max_length=15)),
            ('event_name', self.gf('django.db.models.fields.CharField')(max_length=128)),
            ('person_name', self.gf('django.db.models.fields.CharField')(max_length=128, null=True, blank=True)),
            ('contact_email', self.gf('django.db.models.fields.CharField')(max_length=256, null=True, blank=True)),
            ('contact_addr', self.gf('django.db.models.fields.TextField')(null=True, blank=True)),
            ('contact_phone', self.gf('django.db.models.fields.CharField')(max_length=32, null=True, blank=True)),
            ('date_setup_start', self.gf('django.db.models.fields.DateField')()),
            ('time_setup_start', self.gf('django.db.models.fields.TimeField')()),
            ('time_setup_up', self.gf('django.db.models.fields.TimeField')()),
            ('datetime_start', self.gf('django.db.models.fields.DateTimeField')()),
            ('datetime_end', self.gf('django.db.models.fields.DateTimeField')()),
            ('location', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['events.Location'])),
            ('lights', self.gf('django.db.models.fields.BooleanField')(default=False)),
            ('sound', self.gf('django.db.models.fields.BooleanField')(default=False)),
            ('power', self.gf('django.db.models.fields.BooleanField')(default=False)),
            ('projection', self.gf('django.db.models.fields.CharField')(max_length=2, null=True, blank=True)),
            ('l', self.gf('django.db.models.fields.CharField')(max_length=1, null=True, blank=True)),
            ('s', self.gf('django.db.models.fields.CharField')(max_length=1, null=True, blank=True)),
            ('description', self.gf('django.db.models.fields.TextField')(null=True, blank=True)),
            ('approved', self.gf('django.db.models.fields.BooleanField')(default=False)),
            ('closed', self.gf('django.db.models.fields.BooleanField')(default=False)),
            ('payment_amount', self.gf('django.db.models.fields.IntegerField')(default=None, null=True, blank=True)),
            ('paid', self.gf('django.db.models.fields.BooleanField')(default=False)),
            ('report', self.gf('django.db.models.fields.TextField')(null=True, blank=True)),
        ))
        db.send_create_signal('events', ['Event'])

        # Adding M2M table for field group on 'Event'
        db.create_table('events_event_group', (
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('event', models.ForeignKey(orm['events.event'], null=False)),
            ('organization', models.ForeignKey(orm['events.organization'], null=False))
        ))
        db.create_unique('events_event_group', ['event_id', 'organization_id'])

        # Adding M2M table for field crew_chief on 'Event'
        db.create_table('events_event_crew_chief', (
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('event', models.ForeignKey(orm['events.event'], null=False)),
            ('user', models.ForeignKey(orm['auth.user'], null=False))
        ))
        db.create_unique('events_event_crew_chief', ['event_id', 'user_id'])

        # Adding M2M table for field crew on 'Event'
        db.create_table('events_event_crew', (
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('event', models.ForeignKey(orm['events.event'], null=False)),
            ('user', models.ForeignKey(orm['auth.user'], null=False))
        ))
        db.create_unique('events_event_crew', ['event_id', 'user_id'])

        # Adding model 'Organization'
        db.create_table('events_organization', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('name', self.gf('django.db.models.fields.CharField')(unique=True, max_length=128)),
            ('email', self.gf('django.db.models.fields.EmailField')(max_length=75)),
            ('address', self.gf('django.db.models.fields.TextField')()),
            ('phone', self.gf('django.db.models.fields.CharField')(max_length=32)),
            ('fund', self.gf('django.db.models.fields.IntegerField')()),
            ('organization', self.gf('django.db.models.fields.IntegerField')()),
            ('account', self.gf('django.db.models.fields.IntegerField')(default=71973)),
        ))
        db.send_create_signal('events', ['Organization'])


    def backwards(self, orm):
        # Deleting model 'Location'
        db.delete_table('events_location')

        # Deleting model 'Event'
        db.delete_table('events_event')

        # Removing M2M table for field group on 'Event'
        db.delete_table('events_event_group')

        # Removing M2M table for field crew_chief on 'Event'
        db.delete_table('events_event_crew_chief')

        # Removing M2M table for field crew on 'Event'
        db.delete_table('events_event_crew')

        # Deleting model 'Organization'
        db.delete_table('events_organization')


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
            'Meta': {'object_name': 'Event'},
            'approved': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'closed': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'contact_addr': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'contact_email': ('django.db.models.fields.CharField', [], {'max_length': '256', 'null': 'True', 'blank': 'True'}),
            'contact_phone': ('django.db.models.fields.CharField', [], {'max_length': '32', 'null': 'True', 'blank': 'True'}),
            'crew': ('django.db.models.fields.related.ManyToManyField', [], {'blank': 'True', 'related_name': "'crew'", 'null': 'True', 'symmetrical': 'False', 'to': "orm['auth.User']"}),
            'crew_chief': ('django.db.models.fields.related.ManyToManyField', [], {'blank': 'True', 'related_name': "'crewchief'", 'null': 'True', 'symmetrical': 'False', 'to': "orm['auth.User']"}),
            'date_setup_start': ('django.db.models.fields.DateField', [], {}),
            'datetime_end': ('django.db.models.fields.DateTimeField', [], {}),
            'datetime_start': ('django.db.models.fields.DateTimeField', [], {}),
            'description': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'event_name': ('django.db.models.fields.CharField', [], {'max_length': '128'}),
            'group': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'to': "orm['events.Organization']", 'null': 'True', 'blank': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'l': ('django.db.models.fields.CharField', [], {'max_length': '1', 'null': 'True', 'blank': 'True'}),
            'lights': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'location': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['events.Location']"}),
            'paid': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'payment_amount': ('django.db.models.fields.IntegerField', [], {'default': 'None', 'null': 'True', 'blank': 'True'}),
            'person_name': ('django.db.models.fields.CharField', [], {'max_length': '128', 'null': 'True', 'blank': 'True'}),
            'power': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'projection': ('django.db.models.fields.CharField', [], {'max_length': '2', 'null': 'True', 'blank': 'True'}),
            'report': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            's': ('django.db.models.fields.CharField', [], {'max_length': '1', 'null': 'True', 'blank': 'True'}),
            'sound': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'submitted_by': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'submitter'", 'to': "orm['auth.User']"}),
            'submitted_ip': ('django.db.models.fields.IPAddressField', [], {'max_length': '15'}),
            'time_setup_start': ('django.db.models.fields.TimeField', [], {}),
            'time_setup_up': ('django.db.models.fields.TimeField', [], {})
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
            'email': ('django.db.models.fields.EmailField', [], {'max_length': '75'}),
            'fund': ('django.db.models.fields.IntegerField', [], {}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '128'}),
            'organization': ('django.db.models.fields.IntegerField', [], {}),
            'phone': ('django.db.models.fields.CharField', [], {'max_length': '32'})
        }
    }

    complete_apps = ['events']