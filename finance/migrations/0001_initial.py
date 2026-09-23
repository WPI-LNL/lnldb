"""
The finance schema, as one step.

The app was built through sixteen migrations -- text columns that became
foreign keys, a constraint added and then replaced, several passes of data
repair against a development database. None of that history is of any use to a
new installation: it describes how this laptop got here, not what the tables
should look like. Since the app had never been deployed anywhere when this was
written, the whole sequence was collapsed into this file plus
``0002_seed_reference_data``.

There is deliberately no ``replaces`` list. That mechanism exists to keep
installations that already ran the old sequence working, and there are none:
the only database that ever applied those sixteen is the developer's own, which
was reconciled by hand when this landed. Carrying a ``replaces`` list naming
sixteen files that no longer exist would be permanent clutter in service of a
migration path nobody needs.
"""
from decimal import Decimal
from django.conf import settings
import django.core.validators
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import finance.models
import mptt.fields


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('events', '0017_is_sga_funded_squashed_0018_pricelist_extras'),
    ]

    operations = [
        migrations.CreateModel(
            name='ColumnAlias',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('canonical', models.CharField(help_text='The name the importer knows the column by, e.g. student_organization. Pick from the list on the Workday transaction admin if unsure.', max_length=64, verbose_name='Importer field')),
                ('alias', models.CharField(help_text='The column heading as Workday now writes it. Case, punctuation and extra spaces are ignored when matching.', max_length=128, unique=True, verbose_name='Header in the export')),
                ('notes', models.TextField(blank=True)),
            ],
            options={
                'verbose_name': 'CSV Column Alias',
                'verbose_name_plural': 'CSV Column Aliases',
                'ordering': ('canonical', 'alias'),
            },
        ),
        migrations.CreateModel(
            name='FinanceSettings',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fiscal_year_start_month', models.PositiveSmallIntegerField(choices=[(1, 'January'), (2, 'February'), (3, 'March'), (4, 'April'), (5, 'May'), (6, 'June'), (7, 'July'), (8, 'August'), (9, 'September'), (10, 'October'), (11, 'November'), (12, 'December')], default=7, help_text="WPI's runs July–June, so FY26 is Jul 2025 – Jun 2026 and is named for the year it ends in. Changing this re-files every transaction ever recorded into different fiscal years, so change it only if the institution genuinely moves its year.", verbose_name='Fiscal year starts in')),
                ('student_org_workday_fund', models.PositiveIntegerField(default=810, help_text='The Workday fund number that marks a client as a student organization (810 for 810-FD). Everything else billing through Workday is treated as a department. Drives the client-type breakdown on the dashboard.', verbose_name='Student organization fund')),
                ('fiscal_years_back', models.PositiveSmallIntegerField(default=6, help_text='How many previous fiscal years the filter bar offers.', verbose_name='Past years in the picker')),
                ('fiscal_years_forward', models.PositiveSmallIntegerField(default=1, help_text='How many upcoming fiscal years to offer, for encumbrances and awards booked ahead of time.', verbose_name='Future years in the picker')),
            ],
            options={
                'verbose_name': 'Finance Configuration',
                'verbose_name_plural': 'Finance Configuration',
            },
        ),
        migrations.CreateModel(
            name='FRLineItem',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=192)),
                ('description', models.TextField(blank=True, help_text='What this line covers, in the words used on the SGA request')),
                ('amount_awarded', models.DecimalField(decimal_places=2, max_digits=10, validators=[django.core.validators.MinValueValidator(Decimal('0.00'))])),
                ('sort_order', models.PositiveIntegerField(default=0)),
            ],
            options={
                'verbose_name': 'Funding Request Line Item',
                'ordering': ('sort_order', 'pk'),
            },
        ),
        migrations.CreateModel(
            name='FundingRequest',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=192)),
                ('reference', models.CharField(blank=True, max_length=64, verbose_name='SGA reference #')),
                ('fiscal_year', models.PositiveIntegerField(db_index=True, default=finance.models.current_fiscal_year)),
                ('date_submitted', models.DateField(blank=True, null=True)),
                ('date_approved', models.DateField(blank=True, null=True)),
                ('is_projection', models.BooleanField(default=False, verbose_name='Projection request')),
                ('closed', models.BooleanField(default=False, help_text='Closed requests are hidden from the dashboard burndown')),
                ('notes', models.TextField(blank=True)),
                ('created_on', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Funding Request',
                'ordering': ('-fiscal_year', 'name'),
                'permissions': (('manage_fundingrequest', 'Create and edit funding requests'),),
            },
        ),
        migrations.CreateModel(
            name='FundSource',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=96, unique=True)),
                ('slug', models.SlugField(help_text='Stable key used in links and by the importer. Safe to leave alone; changing it will break saved links and bookmarks.', max_length=48, unique=True)),
                ('sort_order', models.PositiveIntegerField(default=0, help_text='Lower numbers appear first in dropdowns.')),
                ('is_active', models.BooleanField(default=True, help_text='Uncheck to retire an option. Existing records keep it; it just stops being offered for new ones.')),
                ('description', models.TextField(blank=True)),
                ('workday_fund_codes', models.CharField(blank=True, help_text="Comma-separated Fund codes from the export that mean this bucket and only this bucket. A line whose Fund matches is filled in automatically, so only list a code when it genuinely identifies this fund -- 810-FD is on all of LNL's spending and says nothing about whose money it was. Leave blank and this fund is never chosen for you.", max_length=192, verbose_name='Workday fund codes')),
                ('requires_funding_request', models.BooleanField(default=False, help_text="Money from a specific SGA funding request has to burn down one of that request's lines, or the request's balance silently drifts. Turn this on and an expense on this fund cannot be saved without an FR line -- and no other fund is allowed to name one.", verbose_name='Must name a funding request line')),
            ],
            options={
                'verbose_name': 'Fund Source',
                'ordering': ('sort_order', 'name'),
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='PartitionCode',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(help_text='The organisation code as Workday writes it, e.g. 226-AG. A trailing description in the export is ignored when matching.', max_length=32, unique=True)),
                ('is_projection', models.BooleanField(default=False, help_text='Checked: money on this code is Projection spending unless told otherwise. Unchecked: Event Production unless told otherwise. This is the starting position, not a rule -- see the field below.', verbose_name='Projection side')),
                ('crossing_requires_reason', models.BooleanField(default=False, help_text='Off: moving money off this side is allowed and merely shows a warning, which is right for the main account -- a Projection purchase paid out of it and reimbursed by SGA is normal. On: it is still allowed, but the entry cannot be saved without saying why. Turn this on for the account SGA funds for Projection directly.', verbose_name='Filing it the other way needs an explanation')),
                ('worktag', models.CharField(default='student_organization', help_text='Which Workday worktag carries this code. Real exports put it in Student Organization, not Ledger Account.', max_length=48)),
                ('notes', models.TextField(blank=True)),
            ],
            options={
                'verbose_name': 'Partition Code',
                'ordering': ('code',),
            },
        ),
        migrations.CreateModel(
            name='RevenueSource',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=96, unique=True)),
                ('slug', models.SlugField(help_text='Stable key used in links and by the importer. Safe to leave alone; changing it will break saved links and bookmarks.', max_length=48, unique=True)),
                ('sort_order', models.PositiveIntegerField(default=0, help_text='Lower numbers appear first in dropdowns.')),
                ('is_active', models.BooleanField(default=True, help_text='Uncheck to retire an option. Existing records keep it; it just stops being offered for new ones.')),
                ('description', models.TextField(blank=True)),
            ],
            options={
                'verbose_name': 'Non-Event Revenue Source',
                'ordering': ('sort_order', 'name'),
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='SpendCategory',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=96, unique=True)),
                ('slug', models.SlugField(help_text='Stable key used in links and by the importer. Safe to leave alone; changing it will break saved links and bookmarks.', max_length=48, unique=True)),
                ('sort_order', models.PositiveIntegerField(default=0, help_text='Lower numbers appear first in dropdowns.')),
                ('is_active', models.BooleanField(default=True, help_text='Uncheck to retire an option. Existing records keep it; it just stops being offered for new ones.')),
                ('color', models.CharField(default='#BAB0AC', help_text='Used for this category everywhere it appears in a chart.', max_length=7, validators=[django.core.validators.RegexValidator('^#[0-9A-Fa-f]{6}$', 'Use a six-digit hex colour such as #4E79A7.')], verbose_name='Chart colour')),
                ('description', models.TextField(blank=True)),
                ('is_event_passthrough', models.BooleanField(default=False, help_text='The category to file an expense under when it names the event it was incurred for -- a sub-rental hired for one show, passed straight through. Filled in automatically so the Treasurer does not have to pick a category that says nothing the linked event does not.', verbose_name='Use for costs billed to an event')),
            ],
            options={
                'verbose_name': 'LNL Spend Category',
                'verbose_name_plural': 'LNL Spend Categories',
                'ordering': ('sort_order', 'name'),
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='WorkdayTransaction',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('operational_transaction', models.CharField(blank=True, db_index=True, help_text="Workday's reference for the document this line belongs to. One invoice covers many lines, and journal entries carry none at all, so this is a grouping label -- not an identifier.", max_length=128, verbose_name='Operational Transaction')),
                ('accounting_date', models.DateField(db_index=True)),
                ('net_amount', models.DecimalField(decimal_places=2, help_text="Workday 'Credit Minus Debit'. Positive = revenue, negative = expense.", max_digits=12, verbose_name='Net amount')),
                ('supplier', models.CharField(blank=True, max_length=255)),
                ('employee', models.CharField(blank=True, max_length=255)),
                ('memo', models.TextField(blank=True, help_text='Journal Line Memo + Header Memo, concatenated')),
                ('worktags_json', models.JSONField(blank=True, default=dict, help_text='Remaining Workday columns (fund, cost center, ledger account, spend category, program...) kept verbatim for auto-suggest and audit', verbose_name='Workday worktags')),
                ('row_fingerprint', models.CharField(blank=True, db_index=True, editable=False, help_text='Content hash of the exported line: date, amount, payee, memo and worktags', max_length=64, verbose_name='Row fingerprint')),
                ('fingerprint_ordinal', models.PositiveIntegerField(default=1, editable=False, help_text='Which occurrence of an otherwise identical line this is. Two genuinely separate charges that Workday exports identically are occurrence 1 and 2.', verbose_name='Occurrence')),
                ('imported_on', models.DateTimeField(auto_now_add=True)),
                ('source_file', models.CharField(blank=True, max_length=255)),
                ('imported_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='workday_imports', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Workday Transaction',
                'ordering': ('-accounting_date', '-pk'),
                'permissions': (('import_workdaytransaction', 'Import Workday CSV exports'),),
            },
        ),
        migrations.CreateModel(
            name='SuggestionRule',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('match_field', models.CharField(choices=[('ledger_account', 'Workday ledger account'), ('spend_category', "Workday's own spend category"), ('supplier', 'Supplier or employee name'), ('memo', 'Memo text')], default='spend_category', help_text='Which part of the imported line to look at.', max_length=24)),
                ('match_mode', models.CharField(choices=[('exact', 'Is exactly — the whole value, e.g. "Rent - Equipment"'), ('starts', 'Starts with — e.g. the account number 71100'), ('contains', 'Contains — a guess about wording'), ('word', 'Contains the whole word — a guess about wording')], default='exact', help_text='Exact and starts-with count as lookups: what they find is filled into the reconciliation form, because the export itself said it. Contains counts as a guess and is only ever offered as a chip to click.', max_length=12, verbose_name='Match how')),
                ('pattern', models.CharField(help_text='Text to look for. Case-insensitive; surrounding spaces are ignored.', max_length=128)),
                ('confidence', models.CharField(choices=[('high', 'High — pre-select it confidently'), ('medium', 'Medium'), ('low', 'Low — offer it as a guess')], default='high', max_length=8)),
                ('priority', models.PositiveIntegerField(default=100, help_text='Lower numbers are checked first. Put specific rules above general ones.')),
                ('is_active', models.BooleanField(default=True)),
                ('notes', models.CharField(blank=True, max_length=192)),
                ('spend_category', models.ForeignKey(help_text='The category to suggest when this rule matches.', on_delete=django.db.models.deletion.CASCADE, related_name='suggestion_rules', to='finance.spendcategory')),
            ],
            options={
                'verbose_name': 'Spend Category Suggestion Rule',
                'ordering': ('priority', 'pk'),
            },
        ),
        migrations.CreateModel(
            name='ServiceColor',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('color', models.CharField(help_text='Hex, e.g. #4E79A7.', max_length=7, validators=[django.core.validators.RegexValidator('^#[0-9A-Fa-f]{6}$', 'Use a hex colour such as #4E79A7.')], verbose_name='Chart colour')),
                ('category', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='finance_color', to='events.category')),
            ],
            options={
                'verbose_name': 'Service Colour',
                'ordering': ('category__name',),
            },
        ),
        migrations.CreateModel(
            name='ProjectTag',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=128)),
                ('code', models.SlugField(help_text='Short unique key used on reports, e.g. NEL26 or D60-LUSTR', max_length=32, unique=True)),
                ('description', models.TextField(blank=True)),
                ('is_projection', models.BooleanField(default=False, help_text='Projects belonging to the Projection partition', verbose_name='Projection project')),
                ('archived', models.BooleanField(default=False)),
                ('created_on', models.DateTimeField(auto_now_add=True)),
                ('lft', models.PositiveIntegerField(editable=False)),
                ('rght', models.PositiveIntegerField(editable=False)),
                ('tree_id', models.PositiveIntegerField(db_index=True, editable=False)),
                ('level', models.PositiveIntegerField(editable=False)),
                ('parent', mptt.fields.TreeForeignKey(blank=True, help_text='Leave blank to create a top-level project', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='children', to='finance.projecttag', verbose_name='Parent project')),
            ],
            options={
                'verbose_name': 'Project Tag',
                'permissions': (('manage_projecttag', 'Create and edit project tags'),),
            },
        ),
        migrations.CreateModel(
            name='ParsedTransaction',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, help_text='Positive = money in, negative = money out. Must be non-zero.', max_digits=12)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('settled', 'Settled')], db_index=True, default='pending', max_length=16)),
                ('is_projection', models.BooleanField(db_index=True, default=False, help_text='Which activity the money was for, which is not always which account paid. Starts from the org code on the bank line and from the funding request, and can be changed.', verbose_name='Projection partition')),
                ('effective_date', models.DateField(db_index=True, default=django.utils.timezone.localdate)),
                ('description', models.CharField(blank=True, max_length=255)),
                ('audit_explanation', models.TextField(blank=True, help_text='Why this money moved. Shown to auditors.')),
                ('receipt_file', models.FileField(blank=True, null=True, upload_to='finance/receipts/%Y/%m/', verbose_name='Receipt')),
                ('created_on', models.DateTimeField(auto_now_add=True)),
                ('updated_on', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='subledger_entries', to=settings.AUTH_USER_MODEL)),
                ('fr_line_target', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='allocations', to='finance.frlineitem', verbose_name='Funding request line')),
                ('fund_source', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='entries', to='finance.fundsource')),
                ('linked_event', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='subledger_entries', to='events.baseevent', verbose_name='Linked event')),
                ('lnl_spend_category', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='entries', to='finance.spendcategory', verbose_name='LNL spend category')),
                ('non_event_revenue_type', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='entries', to='finance.revenuesource', verbose_name='Non-event revenue type')),
                ('parent_transaction', models.ForeignKey(blank=True, help_text='The bank line this slice belongs to. Blank while this is a pending encumbrance.', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='slices', to='finance.workdaytransaction')),
                ('project_tag', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='transactions', to='finance.projecttag')),
                ('refund_of', models.ForeignKey(blank=True, help_text='The original purchase this credit reverses', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='refunds', to='finance.parsedtransaction', verbose_name='Refund of')),
            ],
            options={
                'verbose_name': 'Subledger Entry',
                'verbose_name_plural': 'Subledger Entries',
                'ordering': ('-effective_date', '-pk'),
                'permissions': (('view_subledger', 'View the financial subledger'), ('edit_subledger', 'Create and edit subledger entries'), ('settle_subledger', 'Reconcile and settle transactions'), ('view_subledger_receipts', 'View uploaded receipts')),
            },
        ),
        migrations.AddField(
            model_name='frlineitem',
            name='funding_request',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='line_items', to='finance.fundingrequest'),
        ),
        migrations.AddField(
            model_name='frlineitem',
            name='lnl_spend_category',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='fr_line_items', to='finance.spendcategory', verbose_name='Expected spend category'),
        ),
        migrations.AddField(
            model_name='frlineitem',
            name='project_tag',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='fr_line_items', to='finance.projecttag'),
        ),
        migrations.AddConstraint(
            model_name='workdaytransaction',
            constraint=models.UniqueConstraint(fields=('row_fingerprint', 'fingerprint_ordinal'), name='finance_workday_line_occurrence_once'),
        ),
        migrations.AddConstraint(
            model_name='parsedtransaction',
            constraint=models.CheckConstraint(check=models.Q(('amount', 0), _negated=True), name='finance_slice_amount_nonzero'),
        ),
        migrations.AddConstraint(
            model_name='parsedtransaction',
            constraint=models.CheckConstraint(check=models.Q(('parent_transaction__isnull', False), ('status', 'pending'), _connector='OR'), name='finance_encumbrance_must_be_pending'),
        ),
        migrations.AddConstraint(
            model_name='parsedtransaction',
            constraint=models.CheckConstraint(check=models.Q(models.Q(('amount__gt', 0), ('refund_of__isnull', True)), ('non_event_revenue_type__isnull', True), _connector='OR'), name='finance_no_revenue_routing_on_expense'),
        ),
        migrations.AddConstraint(
            model_name='parsedtransaction',
            constraint=models.CheckConstraint(check=models.Q(('amount__lt', 0), ('refund_of__isnull', False), models.Q(('fr_line_target__isnull', True), ('fund_source__isnull', True), ('lnl_spend_category__isnull', True)), _connector='OR'), name='finance_no_expense_routing_on_revenue'),
        ),
        migrations.AddConstraint(
            model_name='parsedtransaction',
            constraint=models.CheckConstraint(check=models.Q(('refund_of__isnull', True), ('amount__gt', 0), _connector='OR'), name='finance_refund_must_be_positive'),
        ),
    ]
