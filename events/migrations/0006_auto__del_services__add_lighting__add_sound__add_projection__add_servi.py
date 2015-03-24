# -*- coding: utf-8 -*-
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):
    def forwards(self, orm):
        # Deleting model 'Services'
        db.delete_table('events_services')

        # Removing M2M table for field extra on 'Services'
        db.delete_table('events_services_extra')

        # Adding model 'Lighting'
        db.create_table('events_lighting', (
            ('service_ptr',
             self.gf('django.db.models.fields.related.OneToOneField')(to=orm['events.Service'], unique=True,
                                                                      primary_key=True)),
        ))
        db.send_create_signal('events', ['Lighting'])

        # Adding model 'Sound'
        db.create_table('events_sound', (
            ('service_ptr',
             self.gf('django.db.models.fields.related.OneToOneField')(to=orm['events.Service'], unique=True,
                                                                      primary_key=True)),
        ))
        db.send_create_signal('events', ['Sound'])

        # Adding model 'Projection'
        db.create_table('events_projection', (
            ('service_ptr',
             self.gf('django.db.models.fields.related.OneToOneField')(to=orm['events.Service'], unique=True,
                                                                      primary_key=True)),
        ))
        db.send_create_signal('events', ['Projection'])

        # Adding model 'Service'
        db.create_table('events_service', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('shortname', self.gf('django.db.models.fields.CharField')(max_length=2)),
            ('longname', self.gf('django.db.models.fields.CharField')(max_length=64)),
            ('cost', self.gf('django.db.models.fields.DecimalField')(max_digits=8, decimal_places=2)),
        ))
        db.send_create_signal('events', ['Service'])

        # Adding M2M table for field extra on 'Service'
        db.create_table('events_service_extra', (
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('service', models.ForeignKey(orm['events.service'], null=False)),
            ('extra', models.ForeignKey(orm['events.extra'], null=False))
        ))
        db.create_unique('events_service_extra', ['service_id', 'extra_id'])


        # Changing field 'Event.lighting'
        db.alter_column('events_event', 'lighting_id',
                        self.gf('django.db.models.fields.related.ForeignKey')(null=True, to=orm['events.Lighting']))

        # Changing field 'Event.sound'
        db.alter_column('events_event', 'sound_id',
                        self.gf('django.db.models.fields.related.ForeignKey')(null=True, to=orm['events.Projection']))

    def backwards(self, orm):
        # Adding model 'Services'
        db.create_table('events_services', (
            ('cost', self.gf('django.db.models.fields.DecimalField')(max_digits=8, decimal_places=2)),
            ('longname', self.gf('django.db.models.fields.CharField')(max_length=64)),
            ('shortname', self.gf('django.db.models.fields.CharField')(max_length=2)),
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
        ))
        db.send_create_signal('events', ['Services'])

        # Adding M2M table for field extra on 'Services'
        db.create_table('events_services_extra', (
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('services', models.ForeignKey(orm['events.services'], null=False)),
            ('extra', models.ForeignKey(orm['events.extra'], null=False))
        ))
        db.create_unique('events_services_extra', ['services_id', 'extra_id'])

        # Deleting model 'Lighting'
        db.delete_table('events_lighting')

        # Deleting model 'Sound'
        db.delete_table('events_sound')

        # Deleting model 'Projection'
        db.delete_table('events_projection')

        # Deleting model 'Service'
        db.delete_table('events_service')

        # Removing M2M table for field extra on 'Service'
        db.delete_table('events_service_extra')


        # Changing field 'Event.lighting'
        db.alter_column('events_event', 'lighting_id',
                        self.gf('django.db.models.fields.related.ForeignKey')(null=True, to=orm['events.Services']))

        # Changing field 'Event.sound'
        db.alter_column('events_event', 'sound_id',
                        self.gf('django.db.models.fields.related.ForeignKey')(null=True, to=orm['events.Services']))

    models = {
        'auth.group': {
            'Meta': {'object_name': 'Group'},
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '80'}),
            'permissions': ('django.db.models.fields.related.ManyToManyField', [],
                            {'to': "orm['auth.Permission']", 'symmetrical': 'False', 'blank': 'True'})
        },
        'auth.permission': {
            'Meta': {'ordering': "('content_type__app_label', 'content_type__model', 'codename')",
                     'unique_together': "(('content_type', 'codename'),)", 'object_name': 'Permission'},
            'codename': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'content_type': (
                'django.db.models.fields.related.ForeignKey', [], {'to': "orm['contenttypes.ContentType']"}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '50'})
        },
        'auth.user': {
            'Meta': {'object_name': 'User'},
            'date_joined': ('django.db.models.fields.DateTimeField', [], {'default': 'datetime.datetime.now'}),
            'email': ('django.db.models.fields.EmailField', [], {'max_length': '75', 'blank': 'True'}),
            'first_name': ('django.db.models.fields.CharField', [], {'max_length': '30', 'blank': 'True'}),
            'groups': ('django.db.models.fields.related.ManyToManyField', [],
                       {'to': "orm['auth.Group']", 'symmetrical': 'False', 'blank': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'is_active': ('django.db.models.fields.BooleanField', [], {'default': 'True'}),
            'is_staff': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'is_superuser': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'last_login': ('django.db.models.fields.DateTimeField', [], {'default': 'datetime.datetime.now'}),
            'last_name': ('django.db.models.fields.CharField', [], {'max_length': '30', 'blank': 'True'}),
            'password': ('django.db.models.fields.CharField', [], {'max_length': '128'}),
            'user_permissions': ('django.db.models.fields.related.ManyToManyField', [],
                                 {'to': "orm['auth.Permission']", 'symmetrical': 'False', 'blank': 'True'}),
            'username': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '30'})
        },
        'contenttypes.contenttype': {
            'Meta': {'ordering': "('name',)", 'unique_together': "(('app_label', 'model'),)",
                     'object_name': 'ContentType', 'db_table': "'django_content_type'"},
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
            'contact_email': (
                'django.db.models.fields.CharField', [], {'max_length': '256', 'null': 'True', 'blank': 'True'}),
            'contact_phone': (
                'django.db.models.fields.CharField', [], {'max_length': '32', 'null': 'True', 'blank': 'True'}),
            'crew': ('django.db.models.fields.related.ManyToManyField', [],
                     {'blank': 'True', 'related_name': "'crew'", 'null': 'True', 'symmetrical': 'False',
                      'to': "orm['auth.User']"}),
            'crew_chief': ('django.db.models.fields.related.ManyToManyField', [],
                           {'blank': 'True', 'related_name': "'crewchief'", 'null': 'True', 'symmetrical': 'False',
                            'to': "orm['auth.User']"}),
            'date_setup_start': ('django.db.models.fields.DateField', [], {}),
            'datetime_end': ('django.db.models.fields.DateTimeField', [], {}),
            'datetime_start': ('django.db.models.fields.DateTimeField', [], {}),
            'description': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'event_name': ('django.db.models.fields.CharField', [], {'max_length': '128'}),
            'group': ('django.db.models.fields.related.ManyToManyField', [],
                      {'symmetrical': 'False', 'to': "orm['events.Organization']", 'null': 'True', 'blank': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'lighting': ('django.db.models.fields.related.ForeignKey', [],
                         {'blank': 'True', 'related_name': "'lighting'", 'null': 'True',
                          'to': "orm['events.Lighting']"}),
            'location': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['events.Location']"}),
            'paid': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'payment_amount': (
                'django.db.models.fields.IntegerField', [], {'default': 'None', 'null': 'True', 'blank': 'True'}),
            'person_name': (
                'django.db.models.fields.CharField', [], {'max_length': '128', 'null': 'True', 'blank': 'True'}),
            'projection': (
                'django.db.models.fields.CharField', [], {'max_length': '2', 'null': 'True', 'blank': 'True'}),
            'report': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'sound': ('django.db.models.fields.related.ForeignKey', [],
                      {'blank': 'True', 'related_name': "'projection'", 'null': 'True',
                       'to': "orm['events.Projection']"}),
            'submitted_by': ('django.db.models.fields.related.ForeignKey', [],
                             {'related_name': "'submitter'", 'to': "orm['auth.User']"}),
            'submitted_ip': ('django.db.models.fields.IPAddressField', [], {'max_length': '15'}),
            'time_setup_start': ('django.db.models.fields.TimeField', [], {}),
            'time_setup_up': ('django.db.models.fields.TimeField', [], {})
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
            'service_ptr': ('django.db.models.fields.related.OneToOneField', [],
                            {'to': "orm['events.Service']", 'unique': 'True', 'primary_key': 'True'})
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
            'associated_orgs': ('django.db.models.fields.related.ManyToManyField', [],
                                {'blank': 'True', 'related_name': "'associated_orgs_rel_+'", 'null': 'True',
                                 'to': "orm['events.Organization']"}),
            'associated_users': ('django.db.models.fields.related.ManyToManyField', [],
                                 {'related_name': "'orgusers'", 'symmetrical': 'False', 'to': "orm['auth.User']"}),
            'email': ('django.db.models.fields.EmailField', [], {'max_length': '75', 'null': 'True', 'blank': 'True'}),
            'email_exec': ('django.db.models.fields.BooleanField', [], {'default': 'True'}),
            'email_normal': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'exec_email': (
                'django.db.models.fields.EmailField', [], {'max_length': '75', 'null': 'True', 'blank': 'True'}),
            'fund': ('django.db.models.fields.IntegerField', [], {}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '128'}),
            'organization': ('django.db.models.fields.IntegerField', [], {}),
            'phone': ('django.db.models.fields.CharField', [], {'max_length': '32'}),
            'user_in_charge': (
                'django.db.models.fields.related.ForeignKey', [],
                {'related_name': "'orgowner'", 'to': "orm['auth.User']"})
        },
        'events.projection': {
            'Meta': {'object_name': 'Projection', '_ormbases': ['events.Service']},
            'service_ptr': ('django.db.models.fields.related.OneToOneField', [],
                            {'to': "orm['events.Service']", 'unique': 'True', 'primary_key': 'True'})
        },
        'events.service': {
            'Meta': {'object_name': 'Service'},
            'cost': ('django.db.models.fields.DecimalField', [], {'max_digits': '8', 'decimal_places': '2'}),
            'extra': ('django.db.models.fields.related.ManyToManyField', [],
                      {'to': "orm['events.Extra']", 'symmetrical': 'False'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'longname': ('django.db.models.fields.CharField', [], {'max_length': '64'}),
            'shortname': ('django.db.models.fields.CharField', [], {'max_length': '2'})
        },
        'events.sound': {
            'Meta': {'object_name': 'Sound', '_ormbases': ['events.Service']},
            'service_ptr': ('django.db.models.fields.related.OneToOneField', [],
                            {'to': "orm['events.Service']", 'unique': 'True', 'primary_key': 'True'})
        }
    }

    complete_apps = ['events']