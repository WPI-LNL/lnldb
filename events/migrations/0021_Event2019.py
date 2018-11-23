# Author: Ryan LaPointe <ryan@ryanlapointe.org>
# 2018-10-22

from django.conf import settings
from django.contrib.auth.management import create_permissions
from django.db import migrations, models
from django.db.migrations.operations.models import Operation
import django.db.models.deletion
from six.moves import zip

class CopyFieldsBetweenTables(Operation):

    reversible = False

    def __init__(self, model_from_name, model_to_name, columns):
        self.model_from_name = model_from_name
        self.model_to_name = model_to_name
        self.columns_from, self.columns_to = zip(*columns)

    def state_forwards(self, app_label, state):
        pass

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        columns_to = ", ".join(('`%s`' % col for col in self.columns_to))
        columns_from = ", ".join(('`%s`' % col for col in self.columns_from))
        base_query = 'INSERT INTO %s_%s (%s) SELECT %s FROM %s_%s;' % (
            app_label, self.model_to_name, columns_to, columns_from, app_label, self.model_from_name
        )
        schema_editor.execute(base_query)

    def describe(self):
        return "Copies between two tables for %s" % self.name

def add_polymorphic_ctype_to_events(apps, schema_editor):
    Event = apps.get_model('events', 'Event')
    BaseEvent = apps.get_model('events', 'BaseEvent')
    ContentType = apps.get_model('contenttypes', 'ContentType')

    new_ct = ContentType.objects.get_for_model(Event)
    BaseEvent.objects.filter(polymorphic_ctype__isnull=True).update(polymorphic_ctype=new_ct)

def fix_permissions(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model('auth', 'Permission')
    BaseEvent = apps.get_model('events', 'BaseEvent')
    baseevent_ctype = ContentType.objects.get_for_model(BaseEvent)
    for perm_name in next(zip(*BaseEvent._meta.permissions)):
        try:
            perm = Permission.objects.get(content_type__app_label='events', content_type__model='event', codename=perm_name)
        except Permission.DoesNotExist:
            continue
        perm.content_type = baseevent_ctype
        perm.save()

class Migration(migrations.Migration):
    
    atomic = False

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('events', '0020_organization_delinquent'),
    ]

    state_operations = [
        migrations.CreateModel(
            name='BaseEvent',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('submitted_ip', models.GenericIPAddressField()),
                ('submitted_on', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('event_name', models.CharField(db_index=True, max_length=128)),
                ('description', models.TextField(blank=True, null=True)),
                ('datetime_setup_complete', models.DateTimeField()),
                ('datetime_start', models.DateTimeField(db_index=True)),
                ('datetime_end', models.DateTimeField()),
                ('internal_notes', models.TextField(blank=True, help_text='Notes that the client and general body should never see.', null=True)),
                ('billed_by_semester', models.BooleanField(db_index=True, default=False, help_text='Check if event will be billed in bulk')),
                ('sensitive', models.BooleanField(default=False, help_text='Nobody besides those directly involved should know about this event')),
                ('test_event', models.BooleanField(default=False, help_text="Check to lower the VP's blood pressure after they see the short-notice S4/L4")),
                ('approved', models.BooleanField(default=False)),
                ('approved_on', models.DateTimeField(blank=True, null=True)),
                ('reviewed', models.BooleanField(default=False)),
                ('reviewed_on', models.DateTimeField(blank=True, null=True)),
                ('closed', models.BooleanField(default=False)),
                ('closed_on', models.DateTimeField(blank=True, null=True)),
                ('cancelled', models.BooleanField(default=False)),
                ('cancelled_on', models.DateTimeField(blank=True, null=True)),
                ('cancelled_reason', models.TextField(blank=True, null=True)),
            ],
            options={
                'permissions': (('view_event', "Show an event that isn't hidden"), ('add_raw_event', 'Use the editor to create an event'), ('event_images', 'Upload images to an event'), ('view_hidden_event', 'Show hidden events'), ('cancel_event', 'Declare an event to be cancelled'), ('event_attachments', 'Upload attachments to an event'), ('edit_event_times', 'Modify the dates for an event'), ('add_event_report', 'Add reports about the event'), ('edit_event_fund', 'Change where money for an event comes from'), ('view_event_billing', 'See financial info for event'), ('view_event_reports', 'See reports for event'), ('edit_event_text', 'Update any event descriptions'), ('adjust_event_owner', 'Change the event contact and organization'), ('edit_event_hours', 'Modify the time sheets'), ('edit_event_flags', 'Add flags to an event'), ('event_view_sensitive', 'Show internal notes and other metadata marked as not public'), ('approve_event', 'Accept an event'), ('decline_event', 'Decline an event'), ('can_chief_event', 'Can crew chief an event'), ('review_event', 'Review an event for billing'), ('adjust_event_charges', 'Add charges and change event type'), ('bill_event', 'Send bills and mark event paid'), ('close_event', 'Lock an event after everything is done.'), ('view_test_event', 'Show events for testing'), ('event_view_granular', 'See debug data like ip addresses'), ('event_view_debug', 'See debug events'), ('reopen_event', 'Reopen a closed, declined, or cancelled event')),
                'ordering': ['-datetime_start'],
                'verbose_name': 'Event',
            },
        ),
        migrations.AddField(
            model_name='baseevent',
            name='approved_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='eventapprovals', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='baseevent',
            name='billing_org',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='billedevents', to='events.Organization'),
        ),
        migrations.AddField(
            model_name='baseevent',
            name='cancelled_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='eventcancellations', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='baseevent',
            name='closed_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='eventclosings', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='baseevent',
            name='contact',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL, verbose_name='Contact'),
        ),
        migrations.AddField(
            model_name='baseevent',
            name='location',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='events.Location'),
        ),
        migrations.AddField(
            model_name='baseevent',
            name='org',
            field=models.ManyToManyField(blank=True, to='events.Organization', verbose_name='Client', related_name='events'),
        ),
        migrations.AddField(
            model_name='baseevent',
            name='polymorphic_ctype',
            field=models.ForeignKey(editable=False, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='polymorphic_events.baseevent_set+', to='contenttypes.ContentType'),
        ),
        migrations.AddField(
            model_name='baseevent',
            name='reviewed_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='eventbillingreview', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='baseevent',
            name='submitted_by',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='submitter', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterModelOptions(
            name='event',
            options={'base_manager_name': 'objects'},
        ),
        migrations.AlterModelOptions(
            name='event',
            options={'verbose_name': '2012 Event'},
        ),
        CopyFieldsBetweenTables(
            model_from_name='event',
            model_to_name='baseevent',
            columns=[('id', 'id'), ('approved', 'approved'), ('approved_by_id', 'approved_by_id'),
                     ('approved_on', 'approved_on'), ('billed_by_semester', 'billed_by_semester'),
                     ('billing_org_id', 'billing_org_id'), ('cancelled', 'cancelled'), ('cancelled_by_id', 'cancelled_by_id'),
                     ('cancelled_on', 'cancelled_on'), ('cancelled_reason', 'cancelled_reason'), ('closed', 'closed'),
                     ('closed_by_id', 'closed_by_id'), ('closed_on', 'closed_on'), ('contact_id', 'contact_id'),
                     ('datetime_end', 'datetime_end'), ('datetime_setup_complete', 'datetime_setup_complete'),
                     ('datetime_start', 'datetime_start'), ('description', 'description'), ('event_name', 'event_name'),
                     ('internal_notes', 'internal_notes'), ('location_id', 'location_id'), ('reviewed', 'reviewed'),
                     ('reviewed_by_id', 'reviewed_by_id'), ('reviewed_on', 'reviewed_on'), ('sensitive', 'sensitive'),
                     ('submitted_by_id', 'submitted_by_id'), ('submitted_ip', 'submitted_ip'),
                     ('submitted_on', 'submitted_on'), ('test_event', 'test_event')],
        ),
        CopyFieldsBetweenTables(
            model_from_name='event_org',
            model_to_name='baseevent_org',
            columns=[('event_id', 'baseevent_id'), ('organization_id', 'organization_id')],
        ),
        migrations.RenameField(
            model_name='event',
            old_name='id',
            new_name='baseevent_ptr',
        ),
        migrations.RemoveField(
            model_name='event',
            name='approved',
        ),
        migrations.RemoveField(
            model_name='event',
            name='approved_by',
        ),
        migrations.RemoveField(
            model_name='event',
            name='approved_on',
        ),
        migrations.RemoveField(
            model_name='event',
            name='billed_by_semester',
        ),
        migrations.RemoveField(
            model_name='event',
            name='billing_org',
        ),
        migrations.RemoveField(
            model_name='event',
            name='cancelled',
        ),
        migrations.RemoveField(
            model_name='event',
            name='cancelled_by',
        ),
        migrations.RemoveField(
            model_name='event',
            name='cancelled_on',
        ),
        migrations.RemoveField(
            model_name='event',
            name='cancelled_reason',
        ),
        migrations.RemoveField(
            model_name='event',
            name='closed',
        ),
        migrations.RemoveField(
            model_name='event',
            name='closed_by',
        ),
        migrations.RemoveField(
            model_name='event',
            name='closed_on',
        ),
        migrations.RemoveField(
            model_name='event',
            name='contact',
        ),
        migrations.RemoveField(
            model_name='event',
            name='datetime_end',
        ),
        migrations.RemoveField(
            model_name='event',
            name='datetime_setup_complete',
        ),
        migrations.RemoveField(
            model_name='event',
            name='datetime_start',
        ),
        migrations.RemoveField(
            model_name='event',
            name='description',
        ),
        migrations.RemoveField(
            model_name='event',
            name='event_name',
        ),
        migrations.RemoveField(
            model_name='event',
            name='internal_notes',
        ),
        migrations.RemoveField(
            model_name='event',
            name='location',
        ),
        migrations.RemoveField(
            model_name='event',
            name='org',
        ),
        migrations.RemoveField(
            model_name='event',
            name='reviewed',
        ),
        migrations.RemoveField(
            model_name='event',
            name='reviewed_by',
        ),
        migrations.RemoveField(
            model_name='event',
            name='reviewed_on',
        ),
        migrations.RemoveField(
            model_name='event',
            name='sensitive',
        ),
        migrations.RemoveField(
            model_name='event',
            name='submitted_by',
        ),
        migrations.RemoveField(
            model_name='event',
            name='submitted_ip',
        ),
        migrations.RemoveField(
            model_name='event',
            name='submitted_on',
        ),
        migrations.RemoveField(
            model_name='event',
            name='test_event',
        ),
        migrations.AlterField(
            model_name='ccreport',
            name='crew_chief',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name='event',
            name='lighting',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='lighting', to='events.Lighting'),
        ),
        migrations.AlterField(
            model_name='event',
            name='projection',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='projection', to='events.Projection'),
        ),
        migrations.AlterField(
            model_name='event',
            name='setup_location',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='setuplocation', to='events.Location'),
        ),
        migrations.AlterField(
            model_name='event',
            name='sound',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='sound', to='events.Sound'),
        ),
        migrations.AlterField(
            model_name='eventccinstance',
            name='service',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='ccinstances', to='events.Service'),
        ),
        migrations.AlterField(
            model_name='eventccinstance',
            name='setup_location',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='ccinstances', to='events.Location'),
        ),
        migrations.AlterField(
            model_name='extra',
            name='category',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='events.Category'),
        ),
        migrations.AlterField(
            model_name='extrainstance',
            name='extra',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='events.Extra'),
        ),
        migrations.AlterField(
            model_name='hours',
            name='service',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='hours', to='events.Service'),
        ),
        migrations.AlterField(
            model_name='location',
            name='building',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='events.Building'),
        ),
        migrations.AlterField(
            model_name='multibilling',
            name='org',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='multibillings', to='events.Organization'),
        ),
        migrations.AlterField(
            model_name='organization',
            name='user_in_charge',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='orgowner', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name='service',
            name='category',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='events.Category'),
        ),
        migrations.AlterField(
            model_name='event',
            name='baseevent_ptr',
            field=models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='events.BaseEvent'),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='multibilling',
            name='events',
            field=models.ManyToManyField(to='events.BaseEvent', related_name='multibillings'),
        ),
        migrations.AlterField(
            model_name='billing',
            name='event',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='billings', to='events.BaseEvent'),
        ),
        migrations.AlterField(
            model_name='ccreport',
            name='event',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='events.BaseEvent'),
        ),
        migrations.AlterField(
            model_name='eventarbitrary',
            name='event',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='arbitraryfees', to='events.BaseEvent'),
        ),
        migrations.AlterField(
            model_name='eventattachment',
            name='event',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attachments', to='events.BaseEvent'),
        ),
        migrations.AlterField(
            model_name='hours',
            name='event',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='hours', to='events.BaseEvent'),
        ),
        migrations.AlterField(
            model_name='reportreminder',
            name='event',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ccreportreminders', to='events.BaseEvent'),
        ),
        migrations.AlterField(
            model_name='eventccinstance',
            name='event',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ccinstances', to='events.BaseEvent'),
        ),
        migrations.AlterField(
            model_name='extrainstance',
            name='event',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='events.BaseEvent'),
        ),
        migrations.AlterField(
            model_name='eventccinstance',
            name='service',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='ccinstances', to='events.Service'),
        ),
        migrations.AddField(
            model_name='eventccinstance',
            name='category',
            field=models.ForeignKey(default=99999, on_delete=django.db.models.deletion.PROTECT, related_name='ccinstances', to='events.Category'),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='hours',
            name='category',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='hours', to='events.Category'),
        ),
        migrations.CreateModel(
            name='Event2019',
            fields=[
                ('baseevent_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='events.BaseEvent')),
            ],
            options={
                'base_manager_name': 'objects',
                'abstract': False,
            },
            bases=('events.baseevent',),
        ),
        migrations.AlterModelOptions(
            name='event2019',
            options={'verbose_name': '2019 Event'},
        ),
        migrations.CreateModel(
            name='ServiceInstance',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('detail', models.TextField(blank=True)),
                ('event', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='events.BaseEvent')),
                ('service', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='events.Service')),
            ],
        ),
    ]
    
    database_operations = state_operations + [
        # Fix ManyToMany fields
        # ---------------------
        migrations.CreateModel(
            name='event_otherservices_temp',
            fields=[
                ('event_id', models.IntegerField()),
                ('service_id', models.IntegerField()),
            ]
        ),
        CopyFieldsBetweenTables(
            model_from_name='event_otherservices',
            model_to_name='event_otherservices_temp',
            columns=[('event_id', 'event_id'), ('service_id', 'service_id')],
        ),
        migrations.RemoveField(
            model_name='event',
            name='otherservices',
        ),
        migrations.AddField(
            model_name='event',
            name='otherservices',
            field=models.ManyToManyField(to='events.Service', blank=True),
        ),
        CopyFieldsBetweenTables(
            model_from_name='event_otherservices_temp',
            model_to_name='event_otherservices',
            columns=[('event_id', 'event_id'), ('service_id', 'service_id')],
        ),
        migrations.DeleteModel('event_otherservices_temp'),
        # ---------------------
        migrations.CreateModel(
            name='event_crew_chief_temp',
            fields=[
                ('event_id', models.IntegerField()),
                ('user_id', models.IntegerField()),
            ]
        ),
        CopyFieldsBetweenTables(
            model_from_name='event_crew_chief',
            model_to_name='event_crew_chief_temp',
            columns=[('event_id', 'event_id'), ('user_id', 'user_id')],
        ),
        migrations.RemoveField(
            model_name='event',
            name='crew_chief',
        ),
        migrations.AddField(
            model_name='event',
            name='crew_chief',
            field=models.ManyToManyField(to=settings.AUTH_USER_MODEL, blank=True, related_name='crewchiefx'),
        ),
        CopyFieldsBetweenTables(
            model_from_name='event_crew_chief_temp',
            model_to_name='event_crew_chief',
            columns=[('event_id', 'event_id'), ('user_id', 'user_id')],
        ),
        migrations.DeleteModel('event_crew_chief_temp'),
        # ---------------------
        migrations.CreateModel(
            name='event_crew_temp',
            fields=[
                ('event_id', models.IntegerField()),
                ('user_id', models.IntegerField()),
            ]
        ),
        CopyFieldsBetweenTables(
            model_from_name='event_crew',
            model_to_name='event_crew_temp',
            columns=[('event_id', 'event_id'), ('user_id', 'user_id')],
        ),
        migrations.RemoveField(
            model_name='event',
            name='crew',
        ),
        migrations.AddField(
            model_name='event',
            name='crew',
            field=models.ManyToManyField(to=settings.AUTH_USER_MODEL, blank=True, related_name='crewx'),
        ),
        CopyFieldsBetweenTables(
            model_from_name='event_crew_temp',
            model_to_name='event_crew',
            columns=[('event_id', 'event_id'), ('user_id', 'user_id')],
        ),
        migrations.DeleteModel('event_crew_temp'),
    ]
    
    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=database_operations,
            state_operations=state_operations
        ),
        migrations.RunPython(add_polymorphic_ctype_to_events, migrations.RunPython.noop),
        migrations.RunPython(fix_permissions),
    ]
