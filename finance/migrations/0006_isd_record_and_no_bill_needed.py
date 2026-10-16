"""
Bills record what their ISD charged, and an event can be marked "No bill
needed".

Both kinds of bill gain the worktag and fund charged, when the Treasurer
recorded a worktag a client sent by email, and the Internal Service Delivery's
number, amount, date and who recorded it. Existing bills get none of them, so
nothing about where they stand changes; a bill marked entered into Workday
before this is still waiting on approval. "No bill needed" is a new table, one
row per event the Treasurer decided not to bill.
"""
from django.conf import settings
import django.core.validators
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import re


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0019_move_bills_to_finance'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('finance', '0005_multibill_attach_event_invoices'),
    ]

    operations = [
        migrations.AddField(
            model_name='billing',
            name='fund_charged',
            field=models.PositiveIntegerField(blank=True, help_text='The Workday fund the ISD charges, such as 110.', null=True, verbose_name='Fund'),
        ),
        migrations.AddField(
            model_name='billing',
            name='isd_amount',
            field=models.DecimalField(blank=True, decimal_places=2, help_text='What the ISD charges.', max_digits=8, null=True, verbose_name='ISD amount'),
        ),
        migrations.AddField(
            model_name='billing',
            name='isd_entered_by',
            field=models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='ISD entered by'),
        ),
        migrations.AddField(
            model_name='billing',
            name='isd_entered_on',
            field=models.DateField(blank=True, null=True, verbose_name='ISD entered on'),
        ),
        migrations.AddField(
            model_name='billing',
            name='isd_number',
            field=models.CharField(blank=True, help_text='The number Workday gave the Internal Service Delivery, such as 25090179-ISD.', max_length=20, null=True, unique=True, validators=[django.core.validators.RegexValidator(re.compile('^\\d+-ISD$'), "Workday's ISD numbers are digits, then -ISD, such as 25090179-ISD.")], verbose_name='ISD number'),
        ),
        migrations.AddField(
            model_name='billing',
            name='worktag_charged',
            field=models.CharField(blank=True, help_text='The worktag the ISD charges, such as 1234-CC.', max_length=20, verbose_name='Worktag'),
        ),
        migrations.AddField(
            model_name='billing',
            name='worktag_entered_on',
            field=models.DateField(blank=True, help_text="When the Treasurer recorded the worktag, for a client who sent it by email rather than through the bill's form.", null=True),
        ),
        migrations.AddField(
            model_name='multibilling',
            name='fund_charged',
            field=models.PositiveIntegerField(blank=True, help_text='The Workday fund the ISD charges, such as 110.', null=True, verbose_name='Fund'),
        ),
        migrations.AddField(
            model_name='multibilling',
            name='isd_amount',
            field=models.DecimalField(blank=True, decimal_places=2, help_text='What the ISD charges.', max_digits=8, null=True, verbose_name='ISD amount'),
        ),
        migrations.AddField(
            model_name='multibilling',
            name='isd_entered_by',
            field=models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='ISD entered by'),
        ),
        migrations.AddField(
            model_name='multibilling',
            name='isd_entered_on',
            field=models.DateField(blank=True, null=True, verbose_name='ISD entered on'),
        ),
        migrations.AddField(
            model_name='multibilling',
            name='isd_number',
            field=models.CharField(blank=True, help_text='The number Workday gave the Internal Service Delivery, such as 25090179-ISD.', max_length=20, null=True, unique=True, validators=[django.core.validators.RegexValidator(re.compile('^\\d+-ISD$'), "Workday's ISD numbers are digits, then -ISD, such as 25090179-ISD.")], verbose_name='ISD number'),
        ),
        migrations.AddField(
            model_name='multibilling',
            name='worktag_charged',
            field=models.CharField(blank=True, help_text='The worktag the ISD charges, such as 1234-CC.', max_length=20, verbose_name='Worktag'),
        ),
        migrations.AddField(
            model_name='multibilling',
            name='worktag_entered_on',
            field=models.DateField(blank=True, help_text="When the Treasurer recorded the worktag, for a client who sent it by email rather than through the bill's form.", null=True),
        ),
        migrations.CreateModel(
            name='NoBillNeeded',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reason', models.CharField(choices=[('sga-funded', 'SGA-funded'), ('not-applicable', 'Billing not applicable'), ('lnl', "LNL's own event"), ('other', 'Other')], max_length=16)),
                ('note', models.TextField(blank=True, help_text='Why, in a sentence. Needed when the reason is Other.')),
                ('decided_on', models.DateTimeField(default=django.utils.timezone.now)),
                ('decided_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('event', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='no_bill_needed', to='events.baseevent')),
            ],
            options={
                'verbose_name': 'No bill needed',
                'verbose_name_plural': 'No bill needed',
            },
        ),
        migrations.AddConstraint(
            model_name='nobillneeded',
            constraint=models.CheckConstraint(check=models.Q(models.Q(('reason', 'other'), _negated=True), models.Q(('note', ''), _negated=True), _connector='OR'), name='finance_no_bill_needed_other_has_a_note'),
        ),
    ]
