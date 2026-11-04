"""
The Budget Report Form: SGA's proof of spending for the year's budget.

SGA asks, for every line item of the budget, for a *payment request* saying
what the line was used for, that it was an "Expense", how much SGA money and
how much of the group's own money was spent, receipts that match those
amounts, the date the money was spent (the last day, if it was spent over
several) and how many undergraduates benefited. A line with no payment
request is cut from next year's budget. SGA's form also asks how each was
paid; LNL's Treasurer doesn't need that from here, so it isn't kept.

Whether SGA wants one payment request per line or one per purchase is not
known, so the form gives both: each line's totals, and every purchase under it
with its own amounts, date and receipt.

:func:`gather` works out what goes on it from the ledger. "Group funds" is the
rest of the same Workday line charged to money that carries forward (Legacy,
the mandatory transfer) -- the club's own money spent beside SGA's on the one
purchase. Receipts follow the Funding Request Report Form's rules
(:mod:`finance.frrf`), numbered line by line, because each line's PDF stands
on its own. :func:`finance.reports.budget_report_form` lays the form out to
check on screen; :func:`line_pdf` draws one line's PDF and :func:`all_pdfs`
puts every line's in a zip.
"""
import zipfile
from io import BytesIO

from django.db.models import F, Sum
from django.template.loader import render_to_string
from django.utils import timezone
from pypdf import PdfWriter
from xhtml2pdf import pisa

from finance.frrf import Receipt, receipt_pages
from finance.models import (ZERO, FundBehaviour, ParsedTransaction, WorkdayTransaction,
                            fiscal_year_for, fund_source_for_tracking, money)
from finance.suggestions import parse_memo
from pdfs.views import link_callback


class BudgetPurchase(object):
    """
    One entry charged to a budget line: a payment SGA may ask a request for.

    ``sga`` is the SGA money spent, positive (a refund is negative, as it
    takes money off). ``group`` is the group's own money spent on the same
    Workday line. ``amount`` is the two together, which is what the receipt
    has to show. ``receipt_total`` is what the Workday line came to, and so
    what its receipt says; anything beyond ``amount`` is charged elsewhere.
    """

    def __init__(self, entry, group=ZERO, receipt=None):
        self.entry = entry
        self.receipt = receipt
        txn = entry.parent_transaction
        self.line = entry.fr_line_target
        self.date = entry.effective_date
        self.payee = entry.payee_label
        self.description = entry.description or (txn.memo or '')[:80]
        self.workday = txn.reference.split(':', 1)[-1].strip()
        self.sga = -money(entry.amount)
        self.group = group
        self.amount = self.sga + group
        self.receipt_total = -money(txn.net_amount)
        self.is_refund = entry.refund_of_id is not None

    @property
    def charged_elsewhere(self):
        """ What else the Workday line, and so its receipt, covers. """
        return self.receipt_total - self.amount if not self.is_refund else ZERO


class BudgetLineReport(object):
    """ One budget line's payment request: its purchases, receipts and totals. """

    def __init__(self, line, purchases, receipts):
        self.line = line
        self.purchases = purchases
        self.receipts = receipts
        self.sga = sum((p.sga for p in purchases), ZERO)
        self.group = sum((p.group for p in purchases), ZERO)
        self.total = self.sga + self.group
        dates = [p.date for p in purchases if not p.is_refund and p.date]
        #: SGA's form asks for the last day when the money was spent over several.
        self.last_date = max(dates) if dates else None

    @property
    def spent_on(self):
        """ Whether anything was bought on the line: what SGA needs a request for. """
        return any(not p.is_refund for p in self.purchases)

    @property
    def missing(self):
        """ Purchases with no receipt. A refund needs none. """
        return [p for p in self.purchases if p.receipt is None and not p.is_refund]

    @property
    def mismatched(self):
        """ Purchases whose receipt also covers money charged to something else. """
        return [p for p in self.purchases if p.receipt is not None and p.charged_elsewhere]

    @property
    def used_for(self):
        """ What the line was used for, for SGA's form: its description, else its purchases'. """
        if self.line.description:
            return self.line.description
        seen = []
        for purchase in self.purchases:
            if purchase.description and purchase.description not in seen:
                seen.append(purchase.description)
        return '; '.join(seen)

    @property
    def file_part(self):
        return self.line.number or 'line-%s' % self.line.pk

    @property
    def filename(self):
        """ ``lnl-budget-fy27-4521.pdf``. """
        return 'lnl-budget-fy%s-%s.pdf' % (str(self.line.funding_request.fiscal_year)[-2:],
                                           self.file_part)


class BudgetReportForm(object):
    """
    Everything the form says about one budget.

    ``lines`` holds a :class:`BudgetLineReport` for every line, in the
    budget's own order (category by category, the lines in no category last).
    """

    def __init__(self, budget, lines, encumbered, unsettled):
        self.budget = budget
        self.lines = lines
        self.encumbered = encumbered
        self.unsettled = unsettled

    @property
    def spent_lines(self):
        return [line for line in self.lines if line.spent_on]

    @property
    def unspent(self):
        """
        Approved lines nothing has been bought on: no payment request can be
        made for them, and SGA cuts such a line from next year's budget.
        """
        return [line for line in self.lines
                if not line.spent_on and line.line.amount_awarded]

    @property
    def sga(self):
        return sum((line.sga for line in self.lines), ZERO)

    @property
    def group(self):
        return sum((line.group for line in self.lines), ZERO)

    @property
    def receipt_count(self):
        """ Receipts across every line, each counted once. """
        return len({receipt.file.name for line in self.lines for receipt in line.receipts})

    @property
    def file_part(self):
        return 'fy%s' % str(self.budget.fiscal_year)[-2:]

    @property
    def zip_filename(self):
        """ ``lnl-budget-report-fy27.zip``. """
        return 'lnl-budget-report-%s.zip' % self.file_part

    def line(self, pk):
        """ The line report for the line ``pk``, or ``None``. """
        return next((line for line in self.lines if line.line.pk == pk), None)


def budget_lines_in_order(budget):
    """ The budget's lines, category by category in its order, those in none last. """
    return list(budget.line_items.select_related('category', 'funding_request')
                .order_by(F('category__sort_order').asc(nulls_last=True), 'category__name',
                          'category__pk', 'sort_order', 'pk'))


def unsettled_lines(budget, numbers):
    """
    Spending in the queue that will be missing from the form until it is
    settled: lines quoting one of the budget's Request IDs, or tracked to the
    budget's fund, in the budget's year.
    """
    found = []
    for txn in (WorkdayTransaction.objects.unreconciled().filter(net_amount__lt=0)
                .order_by('accounting_date', 'pk')):
        if fiscal_year_for(txn.accounting_date) != budget.fiscal_year:
            continue
        quoted = parse_memo(txn.journal_line_memo or txn.memo).budget_line
        tracked = fund_source_for_tracking(txn.worktag('tracking'))
        if (quoted and quoted in numbers) or (tracked is not None and tracked.draws_on_budget):
            found.append(txn)
    return found


def gather(budget):
    """
    The budget's purchases, line by line, with the group funds beside each
    and the receipt behind it.

    A purchase is any entry charged to a budget line that has reached
    Workday, settled or not: an encumbrance has not been spent. The group's
    own money on a Workday line is counted once, beside the first of its
    entries charged to this budget, so a line split across two budget lines
    does not count it twice.
    """
    entries = list(ParsedTransaction.objects
                   .filter(fr_line_target__funding_request=budget,
                           parent_transaction__isnull=False)
                   .select_related('parent_transaction', 'encumbrance', 'fr_line_target')
                   .order_by('effective_date', 'pk'))
    parents = {entry.parent_transaction_id for entry in entries}

    group_by_parent, shared = {}, {}
    for sibling in (ParsedTransaction.objects.filter(parent_transaction__in=parents)
                    .select_related('fund_source').order_by('pk')):
        fund = sibling.fund_source
        if (sibling.fr_line_target_id is None and fund is not None
                and fund.behaviour == FundBehaviour.CARRIES):
            group_by_parent[sibling.parent_transaction_id] = (
                group_by_parent.get(sibling.parent_transaction_id, ZERO) - money(sibling.amount))
        if sibling.receipt_file:
            shared.setdefault(sibling.parent_transaction_id, sibling.receipt_file)

    counted, by_line = set(), {}
    for entry in entries:
        group = ZERO
        if entry.parent_transaction_id not in counted:
            counted.add(entry.parent_transaction_id)
            group = group_by_parent.get(entry.parent_transaction_id, ZERO)
        file, from_encumbrance = entry.receipt_file, False
        if not file:
            file = shared.get(entry.parent_transaction_id)
        if not file and entry.encumbrance is not None and entry.encumbrance.receipt_file:
            file, from_encumbrance = entry.encumbrance.receipt_file, True
        purchase = BudgetPurchase(entry, group)
        purchase.receipt_file = (file, from_encumbrance) if file else None
        by_line.setdefault(entry.fr_line_target_id, []).append(purchase)

    lines = []
    for line in budget_lines_in_order(budget):
        purchases = by_line.get(line.pk, [])
        receipts = {}
        ordered = []
        for purchase in purchases:
            if purchase.receipt_file is None:
                continue
            file, from_encumbrance = purchase.receipt_file
            receipt = receipts.get(file.name)
            if receipt is None:
                receipt = receipts[file.name] = Receipt(len(ordered) + 1, file, from_encumbrance)
                ordered.append(receipt)
            receipt.purchases.append(purchase)
            purchase.receipt = receipt
        lines.append(BudgetLineReport(line, purchases, ordered))

    encumbered = -money(ParsedTransaction.objects
                        .filter(fr_line_target__funding_request=budget,
                                parent_transaction__isnull=True)
                        .aggregate(t=Sum('amount'))['t'])
    numbers = {line.line.number for line in lines if line.line.number}
    return BudgetReportForm(budget, lines, encumbered, unsettled_lines(budget, numbers))


# ---------------------------------------------------------------------------
# The PDFs
# ---------------------------------------------------------------------------

def line_pdf(form, line, request=None):
    """
    One line's payment request as PDF bytes: what SGA's form asks for, the
    purchases, then each of the line's receipts in number order.
    """
    html = render_to_string('finance/brf_pdf.html', {
        'form': form,
        'budget': form.budget,
        'item': line,
        'generated_on': timezone.localdate(),
    }, request=request)
    front = BytesIO()
    pisa.CreatePDF(html, dest=front, link_callback=link_callback)
    writer = PdfWriter()
    writer.append(front)
    for receipt in line.receipts:
        for page in receipt_pages(receipt, len(line.receipts)):
            writer.add_page(page)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def all_pdfs(form, request=None):
    """ A zip of every line's PDF that has spending to report, as bytes. """
    out = BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as archive:
        for line in form.spent_lines:
            archive.writestr(line.filename, line_pdf(form, line, request))
    return out.getvalue()


def save_answers(form, data):
    """
    Save the undergraduates typed on the form's page for each line
    (``undergraduates-<line pk>``). Only lines of this budget are touched;
    the caller checks the permission to manage funding requests.

    Returns ``(saved, problems)``: how many were changed, and what was refused.
    """
    saved, problems = 0, []
    for line in form.lines:
        key = 'undergraduates-%s' % line.line.pk
        if key not in data:
            continue
        raw = (data.get(key) or '').strip()
        if raw and not raw.isdigit():
            problems.append("%s: undergraduates has to be a whole number." % line.line.label)
            continue
        value = int(raw) if raw else None
        if value != line.line.undergraduates:
            line.line.undergraduates = value
            line.line.save(update_fields=['undergraduates'])
            saved += 1
    return saved, problems
