# -*- coding: utf-8 -*-
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):
    def forwards(self, orm):
        # Adding model 'Category'
        db.create_table('inventory_category', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('name', self.gf('django.db.models.fields.CharField')(max_length=64)),
        ))
        db.send_create_signal('inventory', ['Category'])

        # Adding model 'SubCategory'
        db.create_table('inventory_subcategory', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('name', self.gf('django.db.models.fields.CharField')(max_length=64)),
            ('category', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['inventory.Category'])),
        ))
        db.send_create_signal('inventory', ['SubCategory'])

        # Adding model 'EquipmentMaintEntry'
        db.create_table('inventory_equipmentmaintentry', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('ts', self.gf('django.db.models.fields.DateTimeField')(auto_now_add=True, blank=True)),
            ('date', self.gf('django.db.models.fields.DateField')(auto_now_add=True, blank=True)),
            ('user', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['auth.User'])),
            ('entry', self.gf('django.db.models.fields.TextField')()),
            ('equipment', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['inventory.Equipment'])),
        ))
        db.send_create_signal('inventory', ['EquipmentMaintEntry'])

        # Adding model 'Equipment'
        db.create_table('inventory_equipment', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('name', self.gf('django.db.models.fields.CharField')(max_length=256)),
            ('subcategory', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['inventory.SubCategory'])),
            ('major', self.gf('django.db.models.fields.BooleanField')(default=False)),
            ('description', self.gf('django.db.models.fields.TextField')()),
            ('purchase_date', self.gf('django.db.models.fields.DateField')()),
            ('purchase_price', self.gf('django.db.models.fields.IntegerField')()),
            ('model_number', self.gf('django.db.models.fields.CharField')(max_length=256)),
            ('serial_number', self.gf('django.db.models.fields.CharField')(max_length=256)),
            ('road_case', self.gf('django.db.models.fields.CharField')(max_length=16)),
            ('manufacturer', self.gf('django.db.models.fields.CharField')(max_length=128)),
            ('home', self.gf('django.db.models.fields.CharField')(max_length=2, null=True, blank=True)),
            ('equip_status', self.gf('django.db.models.fields.CharField')(default='AV', max_length=2)),
        ))
        db.send_create_signal('inventory', ['Equipment'])

    def backwards(self, orm):
        # Deleting model 'Category'
        db.delete_table('inventory_category')

        # Deleting model 'SubCategory'
        db.delete_table('inventory_subcategory')

        # Deleting model 'EquipmentMaintEntry'
        db.delete_table('inventory_equipmentmaintentry')

        # Deleting model 'Equipment'
        db.delete_table('inventory_equipment')

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
        'inventory.category': {
            'Meta': {'object_name': 'Category'},
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '64'})
        },
        'inventory.equipment': {
            'Meta': {'object_name': 'Equipment'},
            'description': ('django.db.models.fields.TextField', [], {}),
            'equip_status': ('django.db.models.fields.CharField', [], {'default': "'AV'", 'max_length': '2'}),
            'home': ('django.db.models.fields.CharField', [], {'max_length': '2', 'null': 'True', 'blank': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'major': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'manufacturer': ('django.db.models.fields.CharField', [], {'max_length': '128'}),
            'model_number': ('django.db.models.fields.CharField', [], {'max_length': '256'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '256'}),
            'purchase_date': ('django.db.models.fields.DateField', [], {}),
            'purchase_price': ('django.db.models.fields.IntegerField', [], {}),
            'road_case': ('django.db.models.fields.CharField', [], {'max_length': '16'}),
            'serial_number': ('django.db.models.fields.CharField', [], {'max_length': '256'}),
            'subcategory': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['inventory.SubCategory']"})
        },
        'inventory.equipmentmaintentry': {
            'Meta': {'object_name': 'EquipmentMaintEntry'},
            'date': ('django.db.models.fields.DateField', [], {'auto_now_add': 'True', 'blank': 'True'}),
            'entry': ('django.db.models.fields.TextField', [], {}),
            'equipment': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['inventory.Equipment']"}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'ts': ('django.db.models.fields.DateTimeField', [], {'auto_now_add': 'True', 'blank': 'True'}),
            'user': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['auth.User']"})
        },
        'inventory.subcategory': {
            'Meta': {'object_name': 'SubCategory'},
            'category': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['inventory.Category']"}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '64'})
        }
    }

    complete_apps = ['inventory']