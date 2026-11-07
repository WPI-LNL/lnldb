"""
Takes over the bills -- Billing, MultiBilling and the two email records --
from the events app, which gave them up in events 0019_move_bills_to_finance.

Only Django's record of which app owns them changes. No table is created,
dropped, renamed or copied: each model names the events_* table it has always
used, linking tables included, so the rows stay exactly where they are.

The one write is to django_content_type. The four rows are relabelled from
events to finance rather than left behind, so anything that points at them by
id -- the admin's change history, the models' permissions -- follows the
models instead of being orphaned.
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


STATE_OPERATIONS = [
    migrations.CreateModel(
        name='Billing',
        fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('date_billed', models.DateField()),
            ('date_paid', models.DateField(blank=True, null=True)),
            ('amount', models.DecimalField(decimal_places=2, max_digits=8)),
            ('event', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='billings', to='events.baseevent')),
        ],
        options={
            'db_table': 'events_billing',
            'ordering': ('-date_billed', 'date_paid'),
        },
    ),
    migrations.CreateModel(
        name='MultiBilling',
        fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('date_billed', models.DateField()),
            ('date_paid', models.DateField(blank=True, null=True)),
            ('amount', models.DecimalField(decimal_places=2, max_digits=8)),
            ('events', models.ManyToManyField(db_table='events_multibilling_events', related_name='multibillings', to='events.baseevent')),
            ('org', models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='multibillings', to='events.organization')),
        ],
        options={
            'db_table': 'events_multibilling',
            'ordering': ('-date_billed', 'date_paid'),
        },
    ),
    migrations.CreateModel(
        name='MultiBillingEmail',
        fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('subject', models.CharField(max_length=128)),
            ('message', models.TextField()),
            ('sent_at', models.DateTimeField(null=True)),
            ('email_to_orgs', models.ManyToManyField(db_table='events_multibillingemail_email_to_orgs', to='events.organization')),
            ('email_to_users', models.ManyToManyField(db_table='events_multibillingemail_email_to_users', to=settings.AUTH_USER_MODEL)),
            ('multibilling', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='finance.multibilling')),
        ],
        options={
            'db_table': 'events_multibillingemail',
        },
    ),
    migrations.CreateModel(
        name='BillingEmail',
        fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('subject', models.CharField(max_length=128)),
            ('message', models.TextField()),
            ('sent_at', models.DateTimeField(null=True)),
            ('billing', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='finance.billing')),
            ('email_to_orgs', models.ManyToManyField(db_table='events_billingemail_email_to_orgs', to='events.organization')),
            ('email_to_users', models.ManyToManyField(db_table='events_billingemail_email_to_users', to=settings.AUTH_USER_MODEL)),
        ],
        options={
            'db_table': 'events_billingemail',
        },
    ),
]


#: The content types that move with the models.
BILL_MODELS = ('billing', 'multibilling', 'billingemail', 'multibillingemail')


def relabel_content_types(source, target):
    def relabel(apps, schema_editor):
        ContentType = apps.get_model('contenttypes', 'ContentType')
        types = ContentType.objects.using(schema_editor.connection.alias)
        for model in BILL_MODELS:
            # Already there if a later migrate created it: then the old row is
            # simply stale, and Django's remove_stale_contenttypes clears it.
            if not types.filter(app_label=target, model=model).exists():
                types.filter(app_label=source, model=model).update(app_label=target)
    return relabel


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0019_move_bills_to_finance'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('finance', '0002_seed_reference_data'),
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        # Django's record only: the tables are already there, under these names.
        migrations.SeparateDatabaseAndState(state_operations=STATE_OPERATIONS),
        migrations.RunPython(relabel_content_types('events', 'finance'),
                             relabel_content_types('finance', 'events')),
    ]
