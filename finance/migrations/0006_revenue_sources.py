"""
Revenue sources that know their fund, and SGA's payments tied to their request.

The schema half adds three columns:

* ``RevenueSource.credits_fund`` -- the fund a kind of income always goes into.
  SGA pays each of its three kinds of money into its own pot, so the source
  decides the fund and a mismatch is refused.
* ``ParsedTransaction.funding_request`` -- the request an SGA payment is for:
  the one a reimbursement repays, or the one SGA took money back for. Spending
  still names a funding request *line*; the two are never on one entry.
* ``FundingRequest.owed_at_books_start`` -- what SGA owed for a request whose
  spending began before the books did, so what it owes now can be worked out.

The data half reconciles an install that has already run the seed:

1. **The revenue sources.** "SGA Baseline" is the annual budget, so it is
   renamed "SGA Budget" and pays into the SGA Budget fund. (This file first
   named it "SGA Budget Deposit"; an install that ran that version keeps the
   name until 0007 renames it.) Two rows are added:
   "SGA Funding Request Reimbursement", into SGA Funding Request, and "SGA
   Mandatory Transfer", into the fund of the same name. A row a Treasurer has
   already renamed or reordered keeps what they gave it; only values still
   matching the original seed are changed, and only blank columns filled.

2. **Reimbursements already filed.** Revenue in a fund that draws on funding
   requests now has to name the request. Where the bank line's memo quotes a
   request number lnldb holds, that request is filled in.
"""
import re
from decimal import Decimal

import django.db.models.deletion
from django.db import migrations, models

#: (slug, name, name in the original seed, sort order, sort order in the
#: original seed, fund slug, description). A ``None`` original means the row is
#: new here.
SOURCES = [
    ('sga_fr_reimbursement', 'SGA Funding Request Reimbursement', None, 0, None, 'sga_fr',
     'SGA paying back what LNL spent on a funding request -- actual spending, never the '
     'award. The memo quotes the request, e.g. F.26.86.'),
    ('sga_baseline', 'SGA Budget', 'SGA Baseline', 1, 0, 'sga_budget',
     "The annual SGA budget, deposited before the year's spending. Whatever is unspent on "
     "June 30 goes back to SGA."),
    ('sga_mandatory', 'SGA Mandatory Transfer', None, 2, None, 'sga_mandatory',
     "Projection's yearly allocation into 315-AG. It carries forward."),
    ('asset_liquidation', 'Asset Liquidation', 'Asset Liquidation', 3, 1, None, ''),
    ('alumni', 'Alumni / Donation', 'Alumni / Donation', 4, 2, None, ''),
]

#: An SGA request number in a memo, as finance.suggestions.FR_REFERENCE reads
#: it. Copied rather than imported: a migration must not change behaviour when
#: the application code it was written against does.
REFERENCE = re.compile(r'\b([AFSafs])\.(\d{2})\.(\d+)\b')


def describe_revenue_sources(apps, schema_editor):
    """ Rename, reorder, add and point the revenue sources at their funds. """
    RevenueSource = apps.get_model('finance', 'RevenueSource')
    FundSource = apps.get_model('finance', 'FundSource')

    funds = {fund.slug: fund for fund in FundSource.objects.all()}
    for slug, name, old_name, order, old_order, fund_slug, description in SOURCES:
        source = RevenueSource.objects.filter(slug=slug).first()
        created = False
        if source is None:
            # The Treasurer's own row by that name, under another slug: describe
            # it rather than collide with it.
            source = RevenueSource.objects.filter(name=name).first()
        if source is None:
            source = RevenueSource(slug=slug, name=name, sort_order=order)
            created = True
        if not created:
            if old_name is not None and source.name == old_name:
                source.name = name
            if old_order is not None and source.sort_order == old_order:
                source.sort_order = order
        if not source.description:
            source.description = description
        if source.credits_fund_id is None and fund_slug in funds:
            source.credits_fund = funds[fund_slug]
        source.save()


def _reference(text):
    """ The first request number in ``text``, normalised, or ``''``. """
    match = REFERENCE.search(text or '')
    if match is None:
        return ''
    letter, year, number = match.groups()
    return '%s.%s.%s' % (letter.upper(), year, number)


def link_reimbursements(apps, schema_editor):
    """ Name the request on reimbursements filed before it could be named. """
    ParsedTransaction = apps.get_model('finance', 'ParsedTransaction')
    FundingRequest = apps.get_model('finance', 'FundingRequest')

    requests = {}
    for request in FundingRequest.objects.exclude(reference=''):
        key = re.sub(r'\s+', '', request.reference).upper()
        requests.setdefault(key, request)
    if not requests:
        return

    entries = (ParsedTransaction.objects
               .filter(amount__gt=0, refund_of__isnull=True, funding_request__isnull=True,
                       fund_source__requires_funding_request=True,
                       parent_transaction__isnull=False)
               .select_related('parent_transaction'))
    for entry in entries:
        line = entry.parent_transaction
        memo = (line.worktags_json or {}).get('journal_line_memo') or line.memo
        request = requests.get(_reference(memo))
        if request is not None:
            ParsedTransaction.objects.filter(pk=entry.pk).update(funding_request=request)


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0005_fund_balances'),
    ]

    operations = [
        migrations.AddField(
            model_name='fundingrequest',
            name='owed_at_books_start',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text="Only for a request whose spending began before the subledger's books start: what SGA still owed LNL for it on that day, spent and not yet reimbursed. A negative figure is what SGA had overpaid. Leave at zero when every charge against the request is in the ledger.", max_digits=10, verbose_name='Owed by SGA when the books started'),
        ),
        migrations.AddField(
            model_name='parsedtransaction',
            name='funding_request',
            field=models.ForeignKey(blank=True, help_text="SGA's own payment for a funding request: the request a reimbursement repays, or the one SGA took money back for. Spending against a request names one of its lines instead.", null=True, on_delete=django.db.models.deletion.PROTECT, related_name='sga_payments', to='finance.fundingrequest', verbose_name='SGA funding request'),
        ),
        migrations.AddField(
            model_name='revenuesource',
            name='credits_fund',
            field=models.ForeignKey(blank=True, help_text="The fund this kind of income always adds to. Picking the source fills it in, and filing the money anywhere else is refused. When the fund draws on funding requests, the income has to name the request it reimburses. Leave blank for income that is simply the account's own money.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='revenue_sources', to='finance.fundsource', verbose_name='Goes into'),
        ),
        migrations.AddConstraint(
            model_name='parsedtransaction',
            constraint=models.CheckConstraint(check=models.Q(('funding_request__isnull', True), ('fr_line_target__isnull', True), _connector='OR'), name='finance_sga_payment_is_not_a_charge'),
        ),
        # Last, so every column exists first. Neither undoes anything on the
        # way back: the columns they fill go with the schema.
        migrations.RunPython(describe_revenue_sources, migrations.RunPython.noop),
        migrations.RunPython(link_reimbursements, migrations.RunPython.noop),
    ]
