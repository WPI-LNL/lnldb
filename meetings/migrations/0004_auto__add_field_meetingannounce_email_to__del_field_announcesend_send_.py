# -*- coding: utf-8 -*-
from south.db import db
from south.v2 import SchemaMigration


class Migration(SchemaMigration):
    def forwards(self, orm):
        # Adding field 'MeetingAnnounce.email_to'
        db.add_column(u'meetings_meetingannounce', 'email_to',
                      self.gf('django.db.models.fields.related.ForeignKey')(default=2,
                                                                            to=orm['meetings.TargetEmailList']),
                      keep_default=False)

        # Deleting field 'AnnounceSend.send_to'
        db.delete_column(u'meetings_announcesend', 'send_to_id')

    def backwards(self, orm):
        # Deleting field 'MeetingAnnounce.email_to'
        db.delete_column(u'meetings_meetingannounce', 'email_to_id')

        # Adding field 'AnnounceSend.send_to'
        db.add_column(u'meetings_announcesend', 'send_to',
                      self.gf('django.db.models.fields.related.ForeignKey')(default=2,
                                                                            to=orm['meetings.TargetEmailList']),
                      keep_default=False)

    models = {
        u'auth.group': {
            'Meta': {'object_name': 'Group'},
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '80'}),
            'permissions': ('django.db.models.fields.related.ManyToManyField', [],
                            {'to': u"orm['auth.Permission']", 'symmetrical': 'False', 'blank': 'True'})
        },
        u'auth.permission': {
            'Meta': {'ordering': "(u'content_type__app_label', u'content_type__model', u'codename')",
                     'unique_together': "((u'content_type', u'codename'),)", 'object_name': 'Permission'},
            'codename': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'content_type': (
                'django.db.models.fields.related.ForeignKey', [], {'to': u"orm['contenttypes.ContentType']"}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '50'})
        },
        u'auth.user': {
            'Meta': {'object_name': 'User'},
            'date_joined': ('django.db.models.fields.DateTimeField', [], {'default': 'datetime.datetime.now'}),
            'email': ('django.db.models.fields.EmailField', [], {'max_length': '75', 'blank': 'True'}),
            'first_name': ('django.db.models.fields.CharField', [], {'max_length': '30', 'blank': 'True'}),
            'groups': ('django.db.models.fields.related.ManyToManyField', [],
                       {'to': u"orm['auth.Group']", 'symmetrical': 'False', 'blank': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'is_active': ('django.db.models.fields.BooleanField', [], {'default': 'True'}),
            'is_staff': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'is_superuser': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'last_login': ('django.db.models.fields.DateTimeField', [], {'default': 'datetime.datetime.now'}),
            'last_name': ('django.db.models.fields.CharField', [], {'max_length': '30', 'blank': 'True'}),
            'password': ('django.db.models.fields.CharField', [], {'max_length': '128'}),
            'user_permissions': ('django.db.models.fields.related.ManyToManyField', [],
                                 {'to': u"orm['auth.Permission']", 'symmetrical': 'False', 'blank': 'True'}),
            'username': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '30'})
        },
        u'contenttypes.contenttype': {
            'Meta': {'ordering': "('name',)", 'unique_together': "(('app_label', 'model'),)",
                     'object_name': 'ContentType', 'db_table': "'django_content_type'"},
            'app_label': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'model': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '100'})
        },
        u'events.category': {
            'Meta': {'object_name': 'Category'},
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '16'})
        },
        u'events.event': {
            'Meta': {'ordering': "['-datetime_start']", 'object_name': 'Event'},
            'approved': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'closed': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'contact_addr': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'contact_email': (
                'django.db.models.fields.CharField', [], {'max_length': '256', 'null': 'True', 'blank': 'True'}),
            'contact_phone': (
                'django.db.models.fields.CharField', [], {'max_length': '32', 'null': 'True', 'blank': 'True'}),
            'crew': ('django.db.models.fields.related.ManyToManyField', [],
                     {'blank': 'True', 'related_name': "'crewx'", 'null': 'True', 'symmetrical': 'False',
                      'to': u"orm['auth.User']"}),
            'crew_chief': ('django.db.models.fields.related.ManyToManyField', [],
                           {'blank': 'True', 'related_name': "'crewchiefx'", 'null': 'True', 'symmetrical': 'False',
                            'to': u"orm['auth.User']"}),
            'datetime_end': ('django.db.models.fields.DateTimeField', [], {}),
            'datetime_setup_complete': ('django.db.models.fields.DateTimeField', [], {}),
            'datetime_setup_start': ('django.db.models.fields.DateTimeField', [], {}),
            'datetime_start': ('django.db.models.fields.DateTimeField', [], {}),
            'description': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'event_name': ('django.db.models.fields.CharField', [], {'max_length': '128'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'lighting': ('django.db.models.fields.related.ForeignKey', [],
                         {'blank': 'True', 'related_name': "'lighting'", 'null': 'True',
                          'to': u"orm['events.Lighting']"}),
            'lighting_reqs': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'location': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['events.Location']"}),
            'org': ('django.db.models.fields.related.ManyToManyField', [],
                    {'symmetrical': 'False', 'to': u"orm['events.Organization']", 'null': 'True', 'blank': 'True'}),
            'paid': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'payment_amount': (
                'django.db.models.fields.IntegerField', [], {'default': 'None', 'null': 'True', 'blank': 'True'}),
            'person_name': (
                'django.db.models.fields.CharField', [], {'max_length': '128', 'null': 'True', 'blank': 'True'}),
            'proj_reqs': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'projection': ('django.db.models.fields.related.ForeignKey', [],
                           {'blank': 'True', 'related_name': "'projection'", 'null': 'True',
                            'to': u"orm['events.Projection']"}),
            'sound': ('django.db.models.fields.related.ForeignKey', [],
                      {'blank': 'True', 'related_name': "'sound'", 'null': 'True', 'to': u"orm['events.Sound']"}),
            'sound_reqs': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'submitted_by': ('django.db.models.fields.related.ForeignKey', [],
                             {'related_name': "'submitter'", 'to': u"orm['auth.User']"}),
            'submitted_ip': ('django.db.models.fields.IPAddressField', [], {'max_length': '15'}),
            'submitted_on': ('django.db.models.fields.DateTimeField', [], {'auto_now_add': 'True', 'blank': 'True'})
        },
        u'events.lighting': {
            'Meta': {'object_name': 'Lighting', '_ormbases': [u'events.Service']},
            u'service_ptr': ('django.db.models.fields.related.OneToOneField', [],
                             {'to': u"orm['events.Service']", 'unique': 'True', 'primary_key': 'True'})
        },
        u'events.location': {
            'Meta': {'object_name': 'Location'},
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '64'})
        },
        u'events.organization': {
            'Meta': {'object_name': 'Organization'},
            'account': ('django.db.models.fields.IntegerField', [], {'default': '71973'}),
            'address': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'associated_orgs': ('django.db.models.fields.related.ManyToManyField', [],
                                {'blank': 'True', 'related_name': "'associated_orgs_rel_+'", 'null': 'True',
                                 'to': u"orm['events.Organization']"}),
            'associated_users': ('django.db.models.fields.related.ManyToManyField', [],
                                 {'related_name': "'orgusers'", 'symmetrical': 'False', 'to': u"orm['auth.User']"}),
            'email': ('django.db.models.fields.EmailField', [], {'max_length': '75', 'null': 'True', 'blank': 'True'}),
            'email_exec': ('django.db.models.fields.BooleanField', [], {'default': 'True'}),
            'email_normal': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'exec_email': (
                'django.db.models.fields.EmailField', [], {'max_length': '75', 'null': 'True', 'blank': 'True'}),
            'fund': ('django.db.models.fields.IntegerField', [], {}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '128'}),
            'notes': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'organization': ('django.db.models.fields.IntegerField', [], {}),
            'personal': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'phone': ('django.db.models.fields.CharField', [], {'max_length': '32'}),
            'user_in_charge': (
                'django.db.models.fields.related.ForeignKey', [],
                {'related_name': "'orgowner'", 'to': u"orm['auth.User']"})
        },
        u'events.projection': {
            'Meta': {'object_name': 'Projection', '_ormbases': [u'events.Service']},
            u'service_ptr': ('django.db.models.fields.related.OneToOneField', [],
                             {'to': u"orm['events.Service']", 'unique': 'True', 'primary_key': 'True'})
        },
        u'events.service': {
            'Meta': {'object_name': 'Service'},
            'addtl_cost': ('django.db.models.fields.DecimalField', [], {'max_digits': '8', 'decimal_places': '2'}),
            'base_cost': ('django.db.models.fields.DecimalField', [], {'max_digits': '8', 'decimal_places': '2'}),
            'category': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['events.Category']"}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'longname': ('django.db.models.fields.CharField', [], {'max_length': '64'}),
            'shortname': ('django.db.models.fields.CharField', [], {'max_length': '2'})
        },
        u'events.sound': {
            'Meta': {'object_name': 'Sound', '_ormbases': [u'events.Service']},
            u'service_ptr': ('django.db.models.fields.related.OneToOneField', [],
                             {'to': u"orm['events.Service']", 'unique': 'True', 'primary_key': 'True'})
        },
        u'meetings.announcesend': {
            'Meta': {'object_name': 'AnnounceSend'},
            'announce': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['meetings.MeetingAnnounce']"}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'sent_at': ('django.db.models.fields.DateTimeField', [], {'auto_now_add': 'True', 'blank': 'True'}),
            'sent_success': ('django.db.models.fields.BooleanField', [], {'default': 'False'})
        },
        u'meetings.meeting': {
            'Meta': {'object_name': 'Meeting'},
            'attendance': (
                'django.db.models.fields.related.ManyToManyField', [],
                {'to': u"orm['auth.User']", 'symmetrical': 'False'}),
            'datetime': ('django.db.models.fields.DateTimeField', [], {}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'meeting_type': (
                'django.db.models.fields.related.ForeignKey', [],
                {'default': '1', 'to': u"orm['meetings.MeetingType']"})
        },
        u'meetings.meetingannounce': {
            'Meta': {'object_name': 'MeetingAnnounce'},
            'email_to': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['meetings.TargetEmailList']"}),
            'events': ('django.db.models.fields.related.ManyToManyField', [],
                       {'related_name': "'meetingannouncements'", 'symmetrical': 'False',
                        'to': u"orm['events.Event']"}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'meeting': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['meetings.Meeting']"}),
            'message': ('django.db.models.fields.TextField', [], {})
        },
        u'meetings.meetingtype': {
            'Meta': {'object_name': 'MeetingType'},
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '32'})
        },
        u'meetings.targetemaillist': {
            'Meta': {'object_name': 'TargetEmailList'},
            'email': ('django.db.models.fields.EmailField', [], {'max_length': '75'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '16'})
        }
    }

    complete_apps = ['meetings']