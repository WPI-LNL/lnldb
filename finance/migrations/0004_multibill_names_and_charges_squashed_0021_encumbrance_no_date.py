"""
Every schema change since the bills moved into finance, as one step.

Eighteen migrations, 0004 to 0021, were written while billing, encumbrances,
revenue sources and the SGA paperwork were built, and while the forecast was
built and taken out again. This is the schema they end at, worked out from the
models in one pass, so a new installation creates each table once in its final
shape instead of adding, altering and dropping its way there.

The old migrations' data steps are left out, because on a new installation
there is nothing for them to do. They repaired existing rows (open
encumbrances, permission names, the Active group's grants), and the seed rows
they brought up to date are already seeded in their final form by
``0002_seed_reference_data``.

Unlike ``0001_initial``, this keeps a ``replaces`` list, because the names
change. The Treasurer's development database ran all eighteen. Django sees them
all recorded there, counts this one as applied, and runs nothing. A database
that has run some of them but not all can't use this file. It would need the
old files back to finish first. The only database that ran them was fully
migrated when they were removed.
"""
from django.conf import settings
import django.core.validators
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import re


class Migration(migrations.Migration):

    replaces = [
        ('finance', '0004_multibill_names_and_charges'),
        ('finance', '0005_multibill_attach_event_invoices'),
        ('finance', '0006_isd_record_and_no_bill_needed'),
        ('finance', '0007_bill_paid_note'),
        ('finance', '0008_billing_digest_limits'),
        ('finance', '0009_still_billed_share'),
        ('finance', '0010_encumbrance_wording'),
        ('finance', '0011_settle_wording'),
        ('finance', '0012_fr_reference_bodies'),
        ('finance', '0013_encumbrance_lines'),
        ('finance', '0014_remove_forecast'),
        ('finance', '0015_remove_books_start_setting'),
        ('finance', '0016_revenue_sources_and_category_names'),
        ('finance', '0017_remove_project_code'),
        ('finance', '0018_revenue_links_to_multibill'),
        ('finance', '0019_bill_sent_by_hand'),
        ('finance', '0020_finance_officers_only'),
        ('finance', '0021_encumbrance_no_date'),
    ]

    dependencies = [
        ('events', '0019_move_bills_to_finance'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('finance', '0003_bills_from_events'),
    ]

    operations = [
        migrations.CreateModel(
            name='Encumbrance',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('description', models.CharField(help_text='What the purchase is.', max_length=255)),
                ('receipt_file', models.FileField(blank=True, null=True, upload_to='finance/receipts/%Y/%m/', verbose_name='Receipt or quote')),
                ('created_on', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ('-created_on', '-pk'),
            },
        ),
        migrations.CreateModel(
            name='MultiBillingCharge',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('oneoff', 'One-off charge or credit'), ('rental', 'Rental'), ('percent', 'Percentage fee or discount')], default='oneoff', max_length=8)),
                ('description', models.CharField(max_length=128)),
                ('quantity', models.PositiveSmallIntegerField(default=1)),
                ('unit_price', models.DecimalField(blank=True, decimal_places=2, help_text='Negative for a credit.', max_digits=8, null=True)),
                ('rental_fee_percent', models.DecimalField(blank=True, decimal_places=2, help_text='The rental fee added to a rental, fixed when the fee was added so a later change to the default pricelist does not reprice the bill.', max_digits=5, null=True)),
                ('percent', models.DecimalField(blank=True, decimal_places=2, help_text="Of the events' total. Negative for a discount.", max_digits=5, null=True)),
            ],
            options={
                'verbose_name': 'Multi-bill charge',
                'ordering': ('pk',),
            },
        ),
        migrations.CreateModel(
            name='NoBillNeeded',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reason', models.CharField(choices=[('sga-funded', 'SGA-funded'), ('not-applicable', 'Billing not applicable'), ('lnl', "LNL's own event"), ('other', 'Other')], max_length=16)),
                ('note', models.TextField(blank=True, help_text='Why, in a sentence. Needed when the reason is Other.')),
                ('decided_on', models.DateTimeField(default=django.utils.timezone.now)),
            ],
            options={
                'verbose_name': 'No bill needed',
                'verbose_name_plural': 'No bill needed',
            },
        ),
        migrations.RemoveField(
            model_name='historyoverride',
            name='line',
        ),
        migrations.RemoveField(
            model_name='historyoverride',
            name='spend_category',
        ),
        migrations.RemoveField(
            model_name='historyoverride',
            name='updated_by',
        ),
        migrations.RemoveField(
            model_name='plannedpurchase',
            name='created_by',
        ),
        migrations.RemoveField(
            model_name='plannedpurchase',
            name='fund_source',
        ),
        migrations.RemoveField(
            model_name='plannedpurchase',
            name='spend_category',
        ),
        migrations.AlterModelOptions(
            name='parsedtransaction',
            options={'ordering': ('-effective_date', '-pk'), 'permissions': (('view_subledger', 'View the financial subledger'), ('edit_subledger', 'Create and edit subledger entries'), ('settle_subledger', 'Settle Workday lines'), ('view_subledger_receipts', 'View uploaded receipts')), 'verbose_name': 'Subledger Entry', 'verbose_name_plural': 'Subledger Entries'},
        ),
        migrations.RemoveConstraint(
            model_name='parsedtransaction',
            name='finance_no_revenue_routing_on_expense',
        ),
        migrations.RemoveField(
            model_name='financesettings',
            name='department_billing_share',
        ),
        migrations.RemoveField(
            model_name='financesettings',
            name='ledger_start_date',
        ),
        migrations.RemoveField(
            model_name='financesettings',
            name='minimum_reserve',
        ),
        migrations.RemoveField(
            model_name='projecttag',
            name='code',
        ),
        migrations.RemoveField(
            model_name='spendcategory',
            name='forecast_from_plans',
        ),
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
            name='paid_note',
            field=models.CharField(blank=True, help_text='How it was paid, when no payment received in Workday covers it: cash, a check, or a bill from before the books start.', max_length=200, verbose_name='How it was paid'),
        ),
        migrations.AddField(
            model_name='billing',
            name='sent_note',
            field=models.CharField(blank=True, help_text='How the bill reached the client, such as handed over at a meeting.', max_length=200, verbose_name='How it was sent'),
        ),
        migrations.AddField(
            model_name='billing',
            name='sent_on',
            field=models.DateField(blank=True, help_text='When the bill reached the client some other way than its email from lnldb.', null=True, verbose_name='Sent on'),
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
            model_name='financesettings',
            name='digest_approval_days',
            field=models.PositiveSmallIntegerField(default=21, help_text='The weekly billing digest lists an ISD still waiting for the client to approve it this many days after it was recorded.', verbose_name='Billing digest: waiting on approval after (days)'),
        ),
        migrations.AddField(
            model_name='financesettings',
            name='digest_client_days',
            field=models.PositiveSmallIntegerField(default=14, help_text='The weekly billing digest lists a bill the client has not answered this many days after it was last emailed, so you can email it again.', verbose_name='Billing digest: waiting on client after (days)'),
        ),
        migrations.AddField(
            model_name='multibilling',
            name='attach_event_invoices',
            field=models.BooleanField(default=False, help_text="Follow the bill's invoice with each event's own itemized invoice. The download and every email get the same document.", verbose_name="Add each event's invoice"),
        ),
        migrations.AddField(
            model_name='multibilling',
            name='description',
            field=models.TextField(blank=True, help_text='Shown on the invoice under the name.'),
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
            name='name',
            field=models.CharField(blank=True, help_text='What the bill is for, such as "Fall films". Shown on the invoice and in the email\'s subject.', max_length=128),
        ),
        migrations.AddField(
            model_name='multibilling',
            name='paid_note',
            field=models.CharField(blank=True, help_text='How it was paid, when no payment received in Workday covers it: cash, a check, or a bill from before the books start.', max_length=200, verbose_name='How it was paid'),
        ),
        migrations.AddField(
            model_name='multibilling',
            name='sent_note',
            field=models.CharField(blank=True, help_text='How the bill reached the client, such as handed over at a meeting.', max_length=200, verbose_name='How it was sent'),
        ),
        migrations.AddField(
            model_name='multibilling',
            name='sent_on',
            field=models.DateField(blank=True, help_text='When the bill reached the client some other way than its email from lnldb.', null=True, verbose_name='Sent on'),
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
        migrations.AddField(
            model_name='parsedtransaction',
            name='linked_multibill',
            field=models.ForeignKey(blank=True, help_text='A payment for a multi-bill. Each of its events is credited with its share, by price, as the bill is split.', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='subledger_entries', to='finance.multibilling', verbose_name='Linked multi-bill'),
        ),
        migrations.AlterField(
            model_name='fundingrequest',
            name='reference',
            field=models.CharField(blank=True, help_text="As SGA numbers it: the body that approved it (A for Appropriations Committee, F for Financial Board, S for Senate, E for Exec), the fiscal year, and the request's number -- e.g. A.27.16. When SGA's number came with ? for the letter, enter it that way.", max_length=64, verbose_name='SGA reference #'),
        ),
        migrations.AlterField(
            model_name='fundsource',
            name='account',
            field=models.ForeignKey(blank=True, help_text="The Workday account this money sits in. The carry-forward fund held in an account is that account's own money: a line nothing else identifies is settled to it, and it absorbs the account's opening balance.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='funds', to='finance.partitioncode', verbose_name='Held in'),
        ),
        migrations.AlterField(
            model_name='fundsource',
            name='is_default',
            field=models.BooleanField(default=False, help_text='The fund an expense is filled in with when neither the memo nor the Fund worktag identifies one. This is a stated default, not a reading of the export, and the queue labels it as such -- but leaving the one required box on every row blank is what made settling a typing job. Tick it on exactly one fund.', verbose_name='Fill this in when nothing else says'),
        ),
        migrations.AlterField(
            model_name='multibilling',
            name='org',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='multibillings', to='events.organization', verbose_name='Bill to'),
        ),
        migrations.AlterField(
            model_name='partitioncode',
            name='crossing_requires_reason',
            field=models.BooleanField(default=False, help_text='Off: moving money off this side is allowed and merely shows a warning, which is right for the main account -- a Projection purchase paid out of it and reimbursed by SGA is normal. On: it is still allowed, but the entry cannot be saved without saying why. Turn this on for the account SGA funds for Projection directly.', verbose_name='Counting it on the other side needs an explanation'),
        ),
        migrations.AlterField(
            model_name='revenuesource',
            name='credits_fund',
            field=models.ForeignKey(blank=True, help_text="The fund this kind of income always adds to. Picking the source fills it in, and putting the money anywhere else is refused. When the fund draws on funding requests, the income has to name the request it reimburses. Leave blank for income that is simply the account's own money.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='revenue_sources', to='finance.fundsource', verbose_name='Goes into'),
        ),
        migrations.AlterField(
            model_name='spendcategory',
            name='is_event_passthrough',
            field=models.BooleanField(default=False, help_text='The category an expense gets when it names the event it was incurred for -- a sub-rental hired for one show, passed straight through. Filled in automatically so the Treasurer does not have to pick a category that says nothing the linked event does not.', verbose_name='Use for costs billed to an event'),
        ),
        migrations.AlterField(
            model_name='suggestionrule',
            name='match_mode',
            field=models.CharField(choices=[('exact', 'Is exactly — the whole value, e.g. "Rent - Equipment"'), ('starts', 'Starts with — e.g. the account number 71100'), ('contains', 'Contains — a guess about wording'), ('word', 'Contains the whole word — a guess about wording')], default='exact', help_text="Exact and starts-with count as lookups: what they find is filled into the queue's form, because the export itself said it. Contains counts as a guess and is only ever offered as a chip to click.", max_length=12, verbose_name='Match how'),
        ),
        migrations.AddConstraint(
            model_name='parsedtransaction',
            constraint=models.CheckConstraint(check=models.Q(models.Q(('amount__gt', 0), ('refund_of__isnull', True)), models.Q(('linked_multibill__isnull', True), ('non_event_revenue_type__isnull', True)), _connector='OR'), name='finance_no_revenue_routing_on_expense'),
        ),
        migrations.AddConstraint(
            model_name='parsedtransaction',
            constraint=models.CheckConstraint(check=models.Q(('linked_multibill__isnull', True), models.Q(('linked_event__isnull', True), ('non_event_revenue_type__isnull', True)), _connector='OR'), name='finance_multibill_payment_names_only_the_bill'),
        ),
        migrations.DeleteModel(
            name='HistoryOverride',
        ),
        migrations.DeleteModel(
            name='PlannedPurchase',
        ),
        migrations.AddField(
            model_name='nobillneeded',
            name='decided_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='nobillneeded',
            name='event',
            field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='no_bill_needed', to='events.baseevent'),
        ),
        migrations.AddField(
            model_name='multibillingcharge',
            name='multibilling',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='charges', to='finance.multibilling'),
        ),
        migrations.AddField(
            model_name='encumbrance',
            name='created_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='encumbrances', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='parsedtransaction',
            name='encumbrance',
            field=models.ForeignKey(blank=True, help_text='The encumbrance this entry was written as a line of.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='lines', to='finance.encumbrance'),
        ),
        migrations.AddConstraint(
            model_name='nobillneeded',
            constraint=models.CheckConstraint(check=models.Q(models.Q(('reason', 'other'), _negated=True), models.Q(('note', ''), _negated=True), _connector='OR'), name='finance_no_bill_needed_other_has_a_note'),
        ),
        migrations.AddConstraint(
            model_name='multibillingcharge',
            constraint=models.CheckConstraint(check=models.Q(models.Q(('kind', 'percent'), ('percent__isnull', False), ('unit_price__isnull', True)), models.Q(models.Q(('kind', 'percent'), _negated=True), ('percent__isnull', True), ('unit_price__isnull', False)), _connector='OR'), name='finance_multibill_charge_priced_by_kind'),
        ),
        migrations.AddConstraint(
            model_name='multibillingcharge',
            constraint=models.CheckConstraint(check=models.Q(('kind', 'rental'), ('rental_fee_percent__isnull', True), _connector='OR'), name='finance_multibill_charge_fee_on_rentals_only'),
        ),
    ]
