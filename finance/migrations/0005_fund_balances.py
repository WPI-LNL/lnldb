"""
Fund balances: what each fund holds, how it behaves at June 30, and the year close.

The schema half adds the three tables behind the balance page, the columns that
say how each fund behaves, and lets money coming in name the fund it adds to.
The data half does three things to an install that already has a ledger:

1. **Describes the seeded funds.** Legacy carries forward; the SGA budget's
   unspent balance goes back to SGA; a funding request is reimbursed after the
   spending. All three are held in 226-AG, and each is named by the Tracking
   worktag Workday started exporting in FY27. Only blank columns are filled,
   so a fund a Treasurer has already described is left as it is.

2. **Adds SGA Mandatory Transfer**, Projection's yearly allocation into 315-AG,
   which carries forward like Legacy and so is 315-AG's own money.

3. **Names the fund on revenue already filed.** Until now money coming in could
   not carry one, so every revenue entry is blank; each gets its account's own
   money -- Legacy for 226-AG -- which is what the balance arithmetic would
   have assumed anyway. Saying it outright means the ledger's Fund filter finds
   them, and a reimbursement filed to the wrong fund afterwards is a visible
   choice rather than a blank.
"""
from decimal import Decimal

import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models

from finance.models import org_code_matches, worktag_value

#: (slug, behaviour, account code, Tracking values, description)
FUND_DETAILS = [
    ('legacy', 'carries', '226-AG', 'Student Org Legacy Funds',
     "LNL's own money: event billing and everything else LNL earns. Carries forward "
     "from one year to the next."),
    ('sga_budget', 'returns', '226-AG', 'SGA Budget',
     "The annual SGA budget. Deposited before the year's spending; whatever is unspent "
     "on June 30 goes back to SGA."),
    ('sga_fr', 'reimbursed', '226-AG', 'SGA Funding Request',
     "Out-of-cycle SGA funding requests. LNL spends first and SGA reimburses what was "
     "actually spent, so the balance is negative until SGA pays."),
    ('sga_mandatory', 'carries', '315-AG', '',
     "Projection's yearly SGA mandatory transfer into 315-AG. Deposited automatically, "
     "and carries forward."),
]


def describe_funds(apps, schema_editor):
    """ Fill in the new columns on the seeded funds, and add the mandatory transfer. """
    FundSource = apps.get_model('finance', 'FundSource')
    PartitionCode = apps.get_model('finance', 'PartitionCode')

    accounts = {p.code: p for p in PartitionCode.objects.all()}
    # A fund of that name under another slug is the Treasurer's own row, and
    # creating a second would collide with its name, so it is described instead.
    mandatory = (FundSource.objects.filter(slug='sga_mandatory').first()
                 or FundSource.objects.filter(name='SGA Mandatory Transfer').first()
                 or FundSource.objects.create(slug='sga_mandatory',
                                              name='SGA Mandatory Transfer', sort_order=3))

    for slug, behaviour, code, tracking, description in FUND_DETAILS:
        fund = (mandatory if slug == 'sga_mandatory'
                else FundSource.objects.filter(slug=slug).first())
        if fund is None:
            continue
        # The columns are new, so behaviour is still its default; the other
        # three are only filled where blank.
        fund.behaviour = behaviour
        if fund.account_id is None and code in accounts:
            fund.account = accounts[code]
        if not fund.workday_tracking_values:
            fund.workday_tracking_values = tracking
        if not fund.description:
            fund.description = description
        fund.save()


def _own_funds(FundSource):
    """ ``{account code: fund}``, by the rule in finance.models.account_own_funds. """
    out = {}
    for fund in (FundSource.objects.filter(is_active=True, behaviour='carries',
                                           account__isnull=False)
                 .select_related('account').order_by('-is_default', 'sort_order', 'name')):
        out.setdefault(fund.account.code, fund)
    return out


def name_revenue_funds(apps, schema_editor):
    """ Give every revenue entry its account's own fund. """
    FundSource = apps.get_model('finance', 'FundSource')
    PartitionCode = apps.get_model('finance', 'PartitionCode')
    ParsedTransaction = apps.get_model('finance', 'ParsedTransaction')

    own = _own_funds(FundSource)
    fallback = FundSource.objects.filter(is_default=True, is_active=True).first()
    codes = list(PartitionCode.objects.values_list('code', 'worktag'))

    revenue = (ParsedTransaction.objects
               .filter(amount__gt=0, refund_of__isnull=True, fund_source__isnull=True,
                       parent_transaction__isnull=False)
               .select_related('parent_transaction'))
    for entry in revenue:
        worktags = entry.parent_transaction.worktags_json
        fund = None
        for code, worktag in codes:
            if org_code_matches(worktag_value(worktags, worktag), code):
                fund = own.get(code)
                break
        fund = fund or fallback
        if fund is not None:
            ParsedTransaction.objects.filter(pk=entry.pk).update(fund_source=fund)


def clear_revenue_funds(apps, schema_editor):
    """
    Undo for the constraint: revenue may not carry a fund before this migration.

    Every revenue entry loses its fund, including any chosen by hand since --
    the schema being reversed to has nowhere to keep it.
    """
    ParsedTransaction = apps.get_model('finance', 'ParsedTransaction')
    ParsedTransaction.objects.filter(amount__gt=0, refund_of__isnull=True).update(
        fund_source=None)


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('finance', '0004_current_spend_categories'),
    ]

    operations = [
        migrations.CreateModel(
            name='BalanceCheckpoint',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('as_of', models.DateField(help_text="The day Workday's figure is for. Lines dated that day are counted in it.", verbose_name='As of the end of')),
                ('balance', models.DecimalField(decimal_places=2, help_text="The account's balance exactly as Workday shows it.", max_digits=12, verbose_name='Workday balance')),
                ('note', models.CharField(blank=True, help_text='Where the figure came from, if that is worth saying.', max_length=255)),
                ('entered_on', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Workday Balance',
                'ordering': ('account__code', '-as_of'),
            },
        ),
        migrations.CreateModel(
            name='FiscalYearClose',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fiscal_year', models.PositiveIntegerField(unique=True)),
                ('closed_on', models.DateTimeField(auto_now_add=True)),
                ('snapshot', models.JSONField(blank=True, default=dict, help_text="Every account's cash and fund balances at the moment of closing.")),
                ('notes', models.TextField(blank=True)),
            ],
            options={
                'verbose_name': 'Fiscal Year Close',
                'ordering': ('-fiscal_year',),
                'permissions': (('close_fiscalyear', 'Close a fiscal year and record its year-end transfers'),),
            },
        ),
        migrations.CreateModel(
            name='FundTransfer',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(default=django.utils.timezone.localdate)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))])),
                ('kind', models.CharField(choices=[('transfer', 'Transfer'), ('opening', 'Opening balance'), ('year_end', 'Year-end close')], default='transfer', max_length=16)),
                ('description', models.CharField(help_text='Why the money moved. Shown to auditors.', max_length=255)),
                ('created_on', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Fund Transfer',
                'ordering': ('-date', '-pk'),
            },
        ),
        migrations.RemoveConstraint(
            model_name='parsedtransaction',
            name='finance_no_expense_routing_on_revenue',
        ),
        migrations.AddField(
            model_name='financesettings',
            name='ledger_start_date',
            field=models.DateField(blank=True, help_text='The first day the subledger accounts for every line. Fund balances are worked out from here: whatever each account held the night before is its opening, and every line on or after it counts. Leave blank to start at the beginning of the fiscal year of the earliest imported line.', null=True, verbose_name='Books start on'),
        ),
        migrations.AddField(
            model_name='fundsource',
            name='account',
            field=models.ForeignKey(blank=True, help_text="The Workday account this money sits in. The carry-forward fund held in an account is that account's own money: a line nothing else identifies is filed to it, and it absorbs the account's opening balance.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='funds', to='finance.partitioncode', verbose_name='Held in'),
        ),
        migrations.AddField(
            model_name='fundsource',
            name='behaviour',
            field=models.CharField(choices=[('carries', 'Carries forward'), ('returns', 'Unspent returns to SGA at year end'), ('reimbursed', 'Reimbursed by SGA after spending')], default='carries', help_text="What happens to this money on June 30. Legacy and the Projection mandatory transfer carry forward; the SGA budget's unspent balance goes back to SGA; a funding request is reimbursed after the spending, so its balance runs negative until SGA pays.", max_length=16, verbose_name='At year end'),
        ),
        migrations.AddField(
            model_name='fundsource',
            name='workday_tracking_values',
            field=models.CharField(blank=True, help_text='Comma-separated values of the Tracking worktag that mean this fund, e.g. "SGA Funding Request". Exports from FY27 on carry it, and a line whose Tracking matches has this fund filled in.', max_length=255, verbose_name='Workday Tracking values'),
        ),
        migrations.AlterField(
            model_name='fundingrequest',
            name='reference',
            field=models.CharField(blank=True, help_text="As SGA numbers it: the body that approved it (A for Appropriations Committee, F for Financial Board, S for Senate), the fiscal year, and the request's number -- e.g. A.27.16.", max_length=64, verbose_name='SGA reference #'),
        ),
        migrations.AlterField(
            model_name='parsedtransaction',
            name='fund_source',
            field=models.ForeignKey(blank=True, help_text='The pot this money came out of, or, for money coming in, the pot it adds to.', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='entries', to='finance.fundsource'),
        ),
        migrations.AddConstraint(
            model_name='parsedtransaction',
            constraint=models.CheckConstraint(check=models.Q(('amount__lt', 0), ('refund_of__isnull', False), models.Q(('fr_line_target__isnull', True), ('lnl_spend_category__isnull', True)), _connector='OR'), name='finance_no_expense_routing_on_revenue'),
        ),
        migrations.AddField(
            model_name='fundtransfer',
            name='account',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='fund_transfers', to='finance.partitioncode'),
        ),
        migrations.AddField(
            model_name='fundtransfer',
            name='created_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='finance_transfers', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='fundtransfer',
            name='fiscal_year_close',
            field=models.ForeignKey(blank=True, help_text='The close that wrote this, which takes it away again if reopened.', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='transfers', to='finance.fiscalyearclose'),
        ),
        migrations.AddField(
            model_name='fundtransfer',
            name='from_fund',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='transfers_out', to='finance.fundsource', verbose_name='From'),
        ),
        migrations.AddField(
            model_name='fundtransfer',
            name='to_fund',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='transfers_in', to='finance.fundsource', verbose_name='To'),
        ),
        migrations.AddField(
            model_name='fiscalyearclose',
            name='closed_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='finance_year_closes', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='balancecheckpoint',
            name='account',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='checkpoints', to='finance.partitioncode'),
        ),
        migrations.AddField(
            model_name='balancecheckpoint',
            name='entered_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='finance_checkpoints', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddConstraint(
            model_name='fundtransfer',
            constraint=models.CheckConstraint(check=models.Q(('amount__gt', 0)), name='finance_transfer_amount_positive'),
        ),
        migrations.AddConstraint(
            model_name='fundtransfer',
            constraint=models.CheckConstraint(check=models.Q(('from_fund', models.F('to_fund')), _negated=True), name='finance_transfer_between_two_funds'),
        ),
        migrations.AddConstraint(
            model_name='balancecheckpoint',
            constraint=models.UniqueConstraint(fields=('account', 'as_of'), name='finance_one_balance_per_account_per_day'),
        ),
        # Last, so every column and the relaxed revenue constraint exist first.
        migrations.RunPython(describe_funds, migrations.RunPython.noop),
        migrations.RunPython(name_revenue_funds, clear_revenue_funds),
    ]
