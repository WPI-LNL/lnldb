"""
Auto-suggest routing.

Everything here is advisory: nothing is written without a human submitting the
form. What the module decides is how much of that form is already filled in
when the Treasurer gets to it, and how each answer explains itself.

The design turns on where an answer came from, which :attr:`Suggestion.source`
records:

``AWARD``
    The funding request line the memo names was awarded for this. Somebody
    entered that when the award was recorded, so re-asking is double entry.

``MEMO``
    The Treasurer wrote it into the Workday memo themselves. LNL's memos are
    written to a house format -- ``{description}, {FR line}, {FR code}``, as in
    ``Velcro restock, consumables, (A.27.16)`` -- so the memo carries the
    routing outright and reading it back is reading their own answer.

``EXPORT``
    Workday stated it, through a table a Treasurer maintains: the ledger
    account, Workday's own spend category, a Fund code, a project code.

``DEFAULT``
    Nothing said, so the fallback configured in the admin. Only the fund has
    one: the account's own money (see :func:`finance.models.account_own_funds`),
    else :attr:`finance.models.FundSource.is_default`.

``GUESS``
    Our own reading of the line -- a word noticed in some prose, a resemblance.

The first four fill the box in. A guess is offered as a chip to click and fills
in nothing, because a pre-selected dropdown gets accepted without being read,
and that is precisely the wrong thing to do with a guess.

Filling a box in is not deciding anything. Every autofilled field renders with
a caption saying which of the above answered it, the row still has to be
submitted by a person, and changing any box is one click. What it buys is that
the ordinary line -- and on a house-format memo that is most of them -- is read
and confirmed rather than retyped.
"""
import calendar
import datetime
import re
from decimal import Decimal

from django.db.models import DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils.formats import date_format

from finance.models import (ZERO, FundSource, ProjectTag, SuggestionRule,
                            default_fund_source, fund_source_for_tracking,
                            fund_source_for_workday_fund, money, normalise_sga_reference,
                            normalise_term, own_fund_for_account, reimbursement_source,
                            revenue_sources_by_fund, spend_category_named)

HIGH, MEDIUM, LOW = 'high', 'medium', 'low'

#: Where a filled-in answer came from. See the module docstring; the order is
#: the order the suggesters try them in, most specific first.
AWARD, MEMO, EXPORT, DEFAULT, GUESS = 'award', 'memo', 'export', 'default', 'guess'

#: The sources that entitle an answer to fill the form in rather than offer a
#: chip. ``GUESS`` is deliberately the only one left out.
FILLS_IN = (AWARD, MEMO, EXPORT, DEFAULT)


def active_suggestion_rules():
    """ The rule table in priority order, category preloaded. """
    return list(SuggestionRule.objects.filter(is_active=True,
                                              spend_category__is_active=True)
                .select_related('spend_category'))


class Suggestion(object):
    """
    One proposed value for one field, and why it is being proposed.

    ``source`` is the interesting part -- see the module docstring. It decides
    whether the form pre-fills this or merely offers it, and it decides what
    the caption under the box says, which is what keeps a filled box from
    claiming more certainty than it has.
    """

    def __init__(self, value, confidence, reason, label='', source=GUESS):
        """ Hold the proposed ``value`` together with where it came from. """
        self.value = value
        self.confidence = confidence
        self.reason = reason
        self.label = label
        self.source = source

    def __repr__(self):
        return "<Suggestion %s (%s, %s)>" % (self.value, self.confidence, self.source)

    @property
    def is_lookup(self):
        """
        Whether this may fill the form in, rather than only offer itself.

        Named for what it meant when the only two kinds were "the export said
        so" and "we guessed": the forms and templates ask this question, not
        which of the four filling sources it was.
        """
        return self.source in FILLS_IN

    @property
    def css_class(self):
        """ The Bootstrap suffix for this suggestion's confidence badge. """
        return {HIGH: 'success', MEDIUM: 'info', LOW: 'default'}.get(self.confidence, 'default')


# ---------------------------------------------------------------------------
# Reading the memo
#
# The single richest thing in a Workday export, because LNL writes it rather
# than Workday. Everything below is about getting the three fields back out of
# it without ever insisting they are there.
# ---------------------------------------------------------------------------

#: An SGA request number as it appears in a memo: F.26.6, A.26.115, F.25.33.
#: The letter is the body that heard it -- A for Appropriations Committee, F for
#: Financial Board, S for Senate, by the size of the ask -- then the fiscal
#: year, then the number within that body's year. Only those three letters, so
#: "Invoice B.4.12" is not read as a funding request. See
#: :data:`finance.models.SGA_REFERENCE`.
FR_REFERENCE = re.compile(r'\b([AFSafs])\.(\d{2})\.(\d+)\b')


def funding_request_references(text):
    """ Every SGA request number mentioned in a piece of text, normalised. """
    return ['%s.%s.%s' % (letter.upper(), year, number)
            for letter, year, number in FR_REFERENCE.findall(text or '')]


#: Kept under its old name: the queue compares memo references with it.
normalise_reference = normalise_sga_reference


def _collapse(text):
    """ One space between words, nothing at either end. """
    return re.sub(r'\s+', ' ', text or '').strip()


def _without_reference(segment):
    """
    One comma-separated segment with any request number taken out of it.

    Brackets go with it, but only on a segment that actually carried a
    reference: "Live at the CC Window (Apr 27)" is a name with a date in it and
    the brackets are part of how the show is told from the other four of it.
    """
    if not FR_REFERENCE.search(segment or ''):
        return _collapse(segment)
    return _collapse(re.sub(r'[()\[\]]', ' ', FR_REFERENCE.sub(' ', segment)))


class MemoFields(object):
    """
    What a Workday memo turned out to be carrying.

    Three optional fields, none of which any particular memo has to have:

    ``description``
        What the line was for, in LNL's words. The ledger's description.
    ``line_hint``
        The funding request line the spending comes out of, as written -- often
        the category name, often the line's own name, and matched against both.
    ``reference``
        The SGA request number, e.g. ``A.27.16``.
    """

    __slots__ = ('description', 'line_hint', 'reference')

    def __init__(self, description='', line_hint='', reference=''):
        self.description = description
        self.line_hint = line_hint
        self.reference = reference

    def __repr__(self):
        return "<MemoFields %r / %r / %r>" % (self.description, self.line_hint,
                                              self.reference)


def parse_memo(text):
    """
    Pull LNL's house memo format apart into its three fields.

    The format is ``{line description}, {FR line}, {FR code}``::

        Velcro restock, consumables, (A.27.16)

    Nothing insists on it, and the parser is written so that a memo which does
    not follow it degrades to "the whole thing is the description" rather than
    to nonsense. Three real shapes, all handled:

    * the full format above, which yields all three fields;
    * a description with the request number written into it --
      ``Truman Show Film Rights (F.26.6)`` -- which yields a description and a
      reference and leaves the line to be worked out another way;
    * anything else at all, which is a description.

    The request number is looked for anywhere in the text rather than only in
    the last segment, because it is as often written inline as appended. The
    segment it leaves empty behind it is dropped; the segment it leaves words
    behind in is kept, minus the number.

    Where several segments survive, the **last** is the line hint and the rest
    rejoin as the description, so a description that itself contains a comma --
    "Gaff tape, spike tape, consumables" -- keeps both halves.
    """
    text = _collapse(text)
    if not text:
        return MemoFields()

    references = funding_request_references(text)
    reference = references[0] if references else ''

    segments = [s for s in (_without_reference(part) for part in text.split(',')) if s]
    if not segments:
        # A memo that was nothing but a request number. Odd, but it happens,
        # and the number is the useful half anyway.
        return MemoFields(reference=reference)
    if len(segments) == 1:
        return MemoFields(description=segments[0], reference=reference)
    return MemoFields(description=', '.join(segments[:-1]), line_hint=segments[-1],
                      reference=reference)


def memo_fields(txn):
    """
    :func:`parse_memo` applied to the part of a bank line LNL wrote.

    The Journal Line Memo is what somebody typed; ``memo`` is that with
    Workday's header memo concatenated on, which is nobody's sentence and would
    put a stranger's words into the ledger's description column.
    """
    return parse_memo(txn.journal_line_memo or txn.memo)


def suggest_description(txn):
    """
    What LNL said this line was for, in their own words, or ``''``.

    The first field of the memo, which is the whole point of the house format:
    "Velcro restock", not "Velcro restock, consumables, (A.27.16)". The routing
    that follows it is about to be recorded in its own columns, and repeating
    it in prose is how a description column stops being read.

    Empty when the memo is empty, deliberately, and callers that need a label
    whatever happens fall back themselves. Reaching for the payee here would
    put "B&H Photo" in a Description column on a row that already says B&H
    Photo -- and, worse, would make a blank spare row in the split modal look
    like one somebody had filled in.
    """
    return memo_fields(txn).description


# ---------------------------------------------------------------------------
# Funding requests
# ---------------------------------------------------------------------------

def _named_category(line):
    """ The normalised name of the category a line was awarded for, or ``''``. """
    category = line.lnl_spend_category
    return normalise_term(category.name) if category is not None else ''


def match_fr_line(funding_request, hint):
    """
    The line of ``funding_request`` a memo's middle field names, or ``None``.

    Tried in descending order of how sure it makes us:

    1. The line's own name, normalised -- "Film Rights" for a line called
       ``Film Rights``.
    2. The spend category that line was awarded for, because a memo written as
       ``..., consumables, (A.27.16)`` is naming the category as often as the
       line, and on a well-formed request those are the same thing anyway.
    3. One containing the other, which catches "consumables" against a line
       called "Consumable Supplies" -- but only where exactly one line matches
       that way. Two candidates is not a near miss, it is a question, and
       picking one of them would answer it silently.

    A request with a single line falls through to that line whatever the hint
    said, which is how this behaved before memos were parsed at all: there is
    nowhere else the money could have come from.
    """
    # ``.all()`` rather than a fresh ``select_related``, so a caller that
    # prefetched the lines -- :func:`suggest_funding_request` does, once per
    # row of a queue page -- gets to use what it fetched.
    lines = list(funding_request.line_items.all())
    if not lines:
        return None

    wanted = normalise_term(hint)
    if wanted:
        # Three separate passes rather than three tests per line, so that the
        # order above is the order that actually decides: a line *named*
        # "Consumables" must beat one merely awarded for consumables, whichever
        # of the two the request happens to list first.
        for line in lines:
            if normalise_term(line.name) == wanted:
                return line
        for line in lines:
            if _named_category(line) == wanted:
                return line
        loose = [line for line in lines
                 if normalise_term(line.name)
                 and (wanted in normalise_term(line.name)
                      or normalise_term(line.name) in wanted)]
        if len(loose) == 1:
            return loose[0]

    return lines[0] if len(lines) == 1 else None


def suggest_funding_request(txn, fields=None):
    """
    The funding request the memo quotes, and the line of it the memo names.

    Workday memos routinely carry the SGA request the spending was approved
    under, and LNL's house format carries the line as well -- that is what the
    middle field of ``Velcro restock, consumables, (A.27.16)`` is for. Both are
    the Treasurer's own reference, written down at the time, so reading them
    back is a lookup and not a guess.

    Returns ``(funding_request, line_or_None)``.
    """
    from django.db.models import Prefetch

    from finance.models import FRLineItem, FundingRequest

    fields = memo_fields(txn) if fields is None else fields
    if not fields.reference:
        return None, None

    # Compared in Python rather than SQL: references are written inconsistently
    # ("F.26.6", "F 26.6") and there are only ever a handful of open requests.
    #
    # The lines come with their awarded spend category attached, because that
    # category is the next question this answers -- see
    # :func:`suggest_spend_category` -- and fetching it per line would be a
    # query per line per row of the queue.
    wanted = normalise_reference(fields.reference)
    candidates = FundingRequest.objects.filter(closed=False).prefetch_related(
        Prefetch('line_items',
                 queryset=FRLineItem.objects.select_related('lnl_spend_category')))
    for funding_request in candidates:
        if normalise_reference(funding_request.reference) == wanted:
            return funding_request, match_fr_line(funding_request, fields.line_hint)
    return None, None


def near_miss_funding_request(reference, include_closed=False):
    """
    The open request numbered like ``reference`` in every part but the letter.

    SGA numbers each body's requests separately, so A.27.16 and F.27.16 are two
    different requests and nothing here may treat them as one. But LNL's memos
    have quoted A.27.16 for weeks against a request lnldb holds as F.27.16, and
    A.27.81 beside F.27.81: a memo whose number lnldb lacks, while the same year
    and number exist under another letter, is far more often a typo on one side
    than a coincidence. So the request is offered as a chip, labelled as the
    question it is, and only a person decides which side has the typo.

    ``None`` when the reference is not SGA's format, when nothing matches, or
    when two do -- two candidates is a question this cannot narrow down.

    ``include_closed`` looks at closed requests too, which is right for SGA's
    payments: a reimbursement often arrives after a request is closed.
    """
    from django.db.models import Prefetch

    from finance.models import SGA_REFERENCE, FRLineItem, FundingRequest

    match = SGA_REFERENCE.match(normalise_reference(reference))
    if match is None:
        return None
    letter, year, number = match.groups()

    found = []
    candidates = FundingRequest.objects.all()
    if not include_closed:
        candidates = candidates.filter(closed=False)
    candidates = candidates.prefetch_related(
        Prefetch('line_items',
                 queryset=FRLineItem.objects.select_related('lnl_spend_category')))
    for funding_request in candidates:
        theirs = SGA_REFERENCE.match(normalise_reference(funding_request.reference))
        if theirs is None:
            continue
        their_letter, their_year, their_number = theirs.groups()
        if (their_letter != letter and their_year == year
                and int(their_number) == int(number)):
            found.append(funding_request)
    return found[0] if len(found) == 1 else None


def suggest_near_miss_line(reference, funding_request, fields):
    """
    A chip for the line of a request whose letter disagrees with the memo's.

    Never a fill: the memo names a request lnldb does not have, and the request
    offered is a different one that merely shares its number. See
    :func:`near_miss_funding_request`.
    """
    if funding_request is None:
        return None
    line = match_fr_line(funding_request, fields.line_hint)
    if line is None:
        return None
    return Suggestion(
        line.pk, MEDIUM,
        'Memo says %s, which lnldb does not have; %s (%s) has the same number. '
        'Check which letter is right' % (reference, funding_request.reference,
                                         funding_request.name),
        line.picker_label, source=GUESS)


def suggest_fr_line(funding_request, line, fields):
    """ The FR line picker's answer, as a :class:`Suggestion` or ``None``. """
    if line is None:
        return None
    if fields.line_hint and normalise_term(fields.line_hint) != normalise_term(line.name):
        reason = ('Memo quotes %s and names "%s"'
                  % (funding_request.reference, fields.line_hint))
    elif fields.line_hint:
        reason = 'Memo quotes %s and names its %s line' % (funding_request.reference,
                                                           line.name)
    else:
        # Reached only when the request has exactly one line, so say so --
        # otherwise the caption claims the memo named a line it never did.
        reason = '%s has only the one line' % funding_request.reference
    return Suggestion(line.pk, HIGH, reason, line.picker_label, source=MEMO)


# ---------------------------------------------------------------------------
# SGA's own payments
#
# SGA moves money with a journal entry: no supplier, no employee, and a memo
# quoting the request -- "F.26.86 Film Posters and Concessions" coming in as a
# reimbursement, "SGA FR F.25.33 was doubled paid to 226-AG" going out when SGA
# takes back a payment it made twice. That shape is what separates SGA paying
# for a request from LNL spending on one: a supplier's credit quotes the request
# too ("Solder wick, Consumables, (A.27.16)"), and it is a refund.
# ---------------------------------------------------------------------------

#: What :attr:`WorkdayTransaction.document_type` reads for a journal entry.
JOURNAL_ENTRY_DOCUMENT_TYPE = 'journal entry'


def is_sga_transfer(txn, fields=None):
    """
    Whether a bank line is SGA moving money for a funding request.

    A journal entry naming nobody, whose memo quotes a request number. Every
    such line in LNL's exports has been SGA's: reimbursements in, and the
    occasional payment taken back out.
    """
    fields = memo_fields(txn) if fields is None else fields
    if not fields.reference:
        return False
    if (txn.document_type or '').strip().lower() != JOURNAL_ENTRY_DOCUMENT_TYPE:
        return False
    return not (txn.supplier or txn.employee)


def find_funding_request(reference):
    """
    The request numbered ``reference``, open or closed, or ``None``.

    Closed requests count here, unlike when matching spending: SGA's payment
    for a request routinely arrives after it was closed for spending.
    """
    from finance.models import FundingRequest

    wanted = normalise_reference(reference)
    if not wanted:
        return None
    # Compared in Python for the reason suggest_funding_request gives.
    for funding_request in FundingRequest.objects.exclude(reference='').with_totals():
        if normalise_reference(funding_request.reference) == wanted:
            return funding_request
    return None


def suggest_sga_payment(txn, fields=None):
    """
    The request an SGA payment is for, read off its memo.

    Returns ``(suggestion, request, near_miss)``. The suggestion fills the box
    when lnldb holds the request the memo quotes; when it holds the same number
    under another body's letter, that one is offered as a chip and named as
    ``near_miss``, because a typo on one side is likelier than a coincidence --
    see :func:`near_miss_funding_request`.
    """
    fields = memo_fields(txn) if fields is None else fields
    if not fields.reference:
        return None, None, None
    request = find_funding_request(fields.reference)
    if request is not None:
        reason = ('Memo quotes %s' % request.reference if txn.net_amount > 0
                  else 'Memo says SGA took back money for %s' % request.reference)
        return (Suggestion(request.pk, HIGH, reason, request.picker_label, source=MEMO),
                request, None)
    near = near_miss_funding_request(fields.reference, include_closed=True)
    if near is None:
        return None, None, None
    return (Suggestion(
        near.pk, MEDIUM,
        'Memo says %s, which lnldb does not have; %s (%s) has the same number. '
        'Check which letter is right' % (fields.reference, near.reference, near.name),
        near.picker_label, source=GUESS), None, near)


def unknown_request(fields):
    """
    What to pre-fill a new funding request with, for a number lnldb lacks.

    The memo has the number and usually the request's name after it, and the
    number has the fiscal year in it, so most of the form can be filled from
    the line that mentioned it.
    """
    from finance.models import SGA_REFERENCE

    match = SGA_REFERENCE.match(normalise_reference(fields.reference))
    if match is None:
        return None
    return {'reference': normalise_reference(fields.reference),
            'name': fields.description,
            'fiscal_year': 2000 + int(match.group(2))}


# ---------------------------------------------------------------------------
# Where income came from
# ---------------------------------------------------------------------------

def suggest_revenue_source(txn, fields=None, fund=None, sga_transfer=False):
    """
    The kind of non-event income a line is, when the export says.

    Two answers, both lookups:

    1. **SGA reimbursing a request.** An SGA journal entry quoting a request
       number is the reimbursement source -- whichever active source pays into
       the fund that draws on funding requests.
    2. **The fund Workday named.** When the Tracking worktag or the Fund code
       says which pot a deposit went into and exactly one kind of income goes
       there -- a deposit tracked "SGA Budget" is the budget deposit -- that is
       the source. A fund that is only the account's own money by default says
       nothing about where the money came from, so it is not read this way.

    ``fund`` is the fund suggestion already worked out for the line.
    """
    fields = memo_fields(txn) if fields is None else fields
    if sga_transfer:
        source = reimbursement_source()
        if source is not None:
            return Suggestion(source.pk, HIGH,
                              'Memo quotes %s: SGA reimbursing a funding request'
                              % fields.reference, str(source), source=MEMO)
        return None
    if fund is None or fund.source not in (MEMO, EXPORT):
        return None
    sources = revenue_sources_by_fund().get(fund.value) or []
    if len(sources) != 1:
        return None
    source = sources[0]
    # A reimbursement is recognised by SGA's journal entry, never by the fund
    # alone: a supplier's credit on a funding-request purchase is tracked to
    # the same fund, and it is a refund.
    if source.repays_funding_requests:
        return None
    return Suggestion(source.pk, HIGH, '%s, and %s is what goes there' % (fund.reason, source),
                      str(source), source=EXPORT)


#: How long before the money arrives a multi-bill may have been sent and still
#: be offered as what the money pays.
MULTIBILL_LOOKBACK_DAYS = 365


def suggest_multibill(txn, linked_event=None):
    """
    The multi-bill a deposit pays, as ``{'multibill', 'reason', 'source'}`` or ``None``.

    One bill can cover several shows, and one payment settles it, so the line
    has to be split between the shows for each one's P&L to see its share.
    Found two ways:

    * the event the memo names was billed on a multi-bill for exactly this
      amount -- the memo said which bill, in effect, so this is a lookup;
    * otherwise one multi-bill, and only one, for exactly this amount, sent in
      the year before the money arrived -- a resemblance, offered as a guess.

    Either way the queue only offers a link to the split page, which lays the
    shares out to be checked and saved: nothing here files anything.
    """
    from events.models import MultiBilling

    if txn.net_amount <= 0:
        return None
    amount = money(txn.net_amount)
    if linked_event is not None and linked_event.is_lookup:
        bill = (MultiBilling.objects.filter(events__pk=linked_event.value, amount=amount)
                .order_by('-date_billed', '-pk').prefetch_related('events').first())
        if bill is None:
            return None
        return {'multibill': bill, 'source': MEMO,
                'reason': 'Memo names one of the %s events on a multi-bill for exactly this '
                          'amount' % bill.events.count()}

    earliest = txn.accounting_date - datetime.timedelta(days=MULTIBILL_LOOKBACK_DAYS)
    latest = txn.accounting_date + datetime.timedelta(days=7)
    candidates = list(MultiBilling.objects.filter(amount=amount,
                                                  date_billed__range=(earliest, latest))
                      .prefetch_related('events')[:2])
    if len(candidates) != 1:
        return None
    bill = candidates[0]
    return {'multibill': bill, 'source': GUESS,
            'reason': 'A multi-bill for exactly this amount, sent %s -- check it'
                      % date_format(bill.date_billed, 'M j, Y')}


# ---------------------------------------------------------------------------
# Spend category
# ---------------------------------------------------------------------------

def rule_reason(rule, txn):
    """ Human explanation shown on the auto-suggest badge. """
    if rule.match_field == SuggestionRule.LEDGER_ACCOUNT:
        return 'Ledger account %s' % (txn.ledger_account or rule.pattern)
    if rule.match_field == SuggestionRule.SPEND_CATEGORY:
        return 'Workday spend category "%s"' % txn.worktag('spend_category')
    if rule.match_field == SuggestionRule.SUPPLIER:
        return 'Supplier "%s"' % txn.payee
    return 'Memo mentions "%s"' % rule.pattern


def suggest_spend_category(txn, rules=None, fr_line=None, fields=None):
    """
    Work out the LNL spend category, most specific evidence first.

    Four passes, and the order is the whole of the logic:

    1. **What the funding request line was awarded for.** If the memo named a
       line and somebody recorded a category against that line when the award
       was entered, that is the answer -- it is the same question, asked once
       already, by the person best placed to answer it.
    2. **What the memo says.** The middle field of the house format is usually
       an LNL category by name: ``Velcro restock, consumables, (A.27.16)``.
       Matching it back to the row is reading the Treasurer's own answer, and
       it outranks Workday's category because WPI's list is not LNL's and never
       was -- everything LNL buys arrives as "Supplies" or "Equipment -
       General" whatever it was really for.
    3. **The rule table**, in priority order: Workday's own spend category
       matched exactly, then the ledger account matched on its number. Both are
       codes somebody at WPI assigned, read through a mapping a Treasurer
       maintains in the admin, so a new code is one row rather than a deploy.
    4. **Wording**, which is a guess and stays a chip.

    ``rules`` lets a caller rendering many rows load the table once.
    """
    if fr_line is not None and fr_line.lnl_spend_category_id:
        return Suggestion(
            fr_line.lnl_spend_category_id, HIGH,
            'The %s line of %s is awarded for it'
            % (fr_line.name, fr_line.funding_request.reference
               or fr_line.funding_request.name),
            str(fr_line.lnl_spend_category), source=AWARD)

    fields = memo_fields(txn) if fields is None else fields
    named = spend_category_named(fields.line_hint)
    if named is not None:
        return Suggestion(named.pk, HIGH, 'Memo says "%s"' % fields.line_hint,
                          str(named), source=MEMO)

    for rule in (active_suggestion_rules() if rules is None else rules):
        if rule.matches(txn):
            return Suggestion(rule.spend_category_id, rule.confidence,
                              rule_reason(rule, txn), str(rule.spend_category),
                              source=EXPORT if rule.is_lookup else GUESS)
    return None


def unmapped_spend_categories(transactions, rules=None):
    """
    Workday spend categories on these lines that no rule will fill a box from.

    Every one of them is a category the Treasurer will have to pick by hand on
    every line that carries it, so the importer reports them: one row in the
    admin retires the question permanently.

    A category matched only by a *wording* rule counts as unmapped here, which
    is not a contradiction. Those rules offer a chip and fill nothing in -- see
    :attr:`finance.models.SuggestionRule.LOOKUP_MODES` -- so the box is still
    one the Treasurer answers by hand, and that is exactly what this list is
    for. The chip is a convenience; a mapping is an answer.
    """
    rules = [rule for rule in (active_suggestion_rules() if rules is None else rules)
             if rule.is_lookup]
    missing = {}
    for txn in transactions:
        value = (txn.worktag('spend_category') or '').strip()
        if not value or any(rule.matches(txn) for rule in rules):
            continue
        missing[value] = missing.get(value, 0) + 1
    return sorted(missing.items(), key=lambda kv: (-kv[1], kv[0]))


# ---------------------------------------------------------------------------
# Fund
# ---------------------------------------------------------------------------

def suggest_fund_source(txn, funding_request=None, reference=''):
    """
    Which pot of money this came out of -- or, for money in, went into.

    In descending order of evidence:

    1. **A funding request number in the memo.** Every SGA number names a
       funding request -- budgets and mandatory transfers have none -- so the
       memo quoting one says this is award money, whichever award it is. The
       fund is whichever bucket is marked as drawing on a request. That holds
       even when lnldb has no request by that number: the fund is still known,
       and the funding request line beside it is the question left open, which
       the queue asks out loud.
    2. **The Tracking worktag**, which Workday exports from FY27 on and which
       names the pot in words: "SGA Budget", "Student Org Legacy Funds". Read
       through each fund's list in the admin.
    3. **The Fund worktag**, through the code list on each :class:`FundSource`.
       Which Workday code means which LNL bucket is WPI's numbering and LNL's
       bookkeeping convention, so it is typed into the admin rather than
       compiled in here. A fund with no codes configured is never chosen this
       way -- which matters, because 810-FD is the agency fund *all* of LNL's
       spending comes out of and identifies nothing at all.
    4. **The account's own money**: the carry-forward fund held in the account
       the line is on, so Legacy on 226-AG and the mandatory transfer on 315-AG.
       A line nothing else identifies is the account spending, or receiving,
       its own money.
    5. **The default**, if a Treasurer has named one, for a line on no account
       anyone has described.

    The last two are stated rather than read, and the queue's caption says so
    in those words: they do not claim the export answered. Leaving the box
    blank instead was the honest thing to do while the alternative was
    inferring a fund from a worktag that says nothing; it is not when a
    Treasurer has written the fallback down in the admin. Fund is required on
    every line, so a blank box was a typing job repeated down the whole queue.

    ``reference`` is the request number the memo quotes, matched or not;
    ``funding_request`` is lnldb's request by that number, when there is one.
    """
    reference = reference or (funding_request.reference if funding_request else '')
    if reference:
        source = FundSource.objects.filter(requires_funding_request=True,
                                           is_active=True).first()
        if source is None:
            # No fund is configured to draw on a request, so there is nothing
            # right to offer -- and falling through would be actively wrong:
            # the memo has just said this is award money, and the passes below
            # would answer with the standing budget.
            return None
        if funding_request is not None:
            reason = 'Memo quotes %s' % funding_request.reference
        else:
            reason = 'Memo quotes %s, an SGA funding request number' % reference
        return Suggestion(source.pk, HIGH, reason, str(source), source=MEMO)

    tracking = txn.worktag('tracking')
    source = fund_source_for_tracking(tracking)
    if source is not None:
        return Suggestion(source.pk, HIGH, 'Workday Tracking "%s"' % tracking, str(source),
                          source=EXPORT)

    fund = txn.worktag('fund')
    source = fund_source_for_workday_fund(fund)
    if source is not None:
        return Suggestion(source.pk, HIGH, 'Workday fund "%s"' % fund, str(source),
                          source=EXPORT)

    account = txn.partition_code_label
    own = own_fund_for_account(account)
    if own is not None:
        return Suggestion(own.pk, MEDIUM,
                          "%s's own money — nothing in the export says otherwise" % account,
                          str(own), source=DEFAULT)

    fallback = default_fund_source()
    if fallback is None:
        return None
    return Suggestion(fallback.pk, MEDIUM,
                      "LNL's stated default — nothing in the export says otherwise",
                      str(fallback), source=DEFAULT)


# ---------------------------------------------------------------------------
# Project tags
# ---------------------------------------------------------------------------

def active_project_tags():
    """ The candidate pool for :func:`suggest_project_tag`, loaded once. """
    return list(ProjectTag.objects.filter(archived=False))


def suggest_project_tag(txn, tags=None):
    """
    Match a project tag code appearing in the memo or Workday Program worktag.

    ``tags`` lets a caller rendering many rows load the pool once instead of
    re-querying it per transaction.
    """
    haystack = " ".join(filter(None, [txn.memo or '', txn.worktag('program'),
                                      txn.worktag('activity')])).upper()
    if not haystack:
        return None
    for tag in (active_project_tags() if tags is None else tags):
        if tag.code and re.search(r'\b%s\b' % re.escape(tag.code.upper()), haystack):
            # The code is LNL's own and appears verbatim in a column Workday
            # exports, so this is a lookup rather than a reading of prose.
            return Suggestion(tag.pk, HIGH,
                              'Project code %s appears in the export' % tag.code,
                              str(tag), source=EXPORT)
    return None


# ---------------------------------------------------------------------------
# Linking an event
# ---------------------------------------------------------------------------

#: How Workday writes an Internal Service Delivery that bills event work.
#: LNL invoices departments and student orgs through ISDs, and the memo is
#: written to a house format: the words "Lens and Lights services for" and then
#: the event, spelled the way it is spelled in lnldb because whoever raised the
#: ISD copied it from there. Real examples, unedited::
#:
#:     Lens and Lights services for Pan Asian Festival D26
#:     Lens and Lights Services for Live at the CC Window (Apr 27) D26
#:     LNL Services for C26 CS Social Movies
#:
#: Whoever raises the ISD sometimes skips the preamble and writes the event
#: alone -- "BRASA Carnival C26", "VOX Into the Woods A25". That shape is
#: handled too, but only on a document Workday itself calls an Internal Service
#: Delivery, and only when the name matches an event exactly. See
#: :func:`event_name_from_transaction`.
ISD_MEMO_PREFIX = re.compile(
    r'^\s*(?:lens\s+and\s+lights|lnl|l\s*&\s*l)\s+services?\s+for\s+',
    re.IGNORECASE)

#: What :attr:`WorkdayTransaction.document_type` reads for an ISD.
ISD_DOCUMENT_TYPE = 'internal service delivery'

#: A WPI term code, which the memo carries and the event name does not: the
#: seven-week terms A-E, plus CM for Commencement. It turns up at either end of
#: the name and occasionally in the middle ("RRC E26 Rental"), so it is removed
#: wherever it appears rather than trimmed off one end.
WPI_TERM_CODE = re.compile(r'\b(?:CM|[A-E])\d{2}\b', re.IGNORECASE)


def event_name_from_memo(text):
    """
    The event name a prefixed ISD memo is billing for, or ``''``.

    Only memos in the ISD house format yield anything; see
    :data:`ISD_MEMO_PREFIX`. Everything else -- journal entries quoting an SGA
    request, expense lines, prose somebody typed freehand -- returns empty.

    Use :func:`event_name_from_transaction` unless you specifically want the
    prefixed form: it also covers the bare-name shape, which needs the document
    type to be safe.
    """
    if not text:
        return ''
    match = ISD_MEMO_PREFIX.match(text)
    if not match:
        return ''
    return _collapse(WPI_TERM_CODE.sub(' ', text[match.end():]))


def event_name_from_transaction(txn):
    """
    The event name a bank line names, in either ISD memo shape, or ``''``.

    Two shapes turn up in practice, and they need different amounts of care:

    1. The house format, ``"Lens and Lights services for <event> <term>"``. The
       preamble is itself the evidence that what follows is an event, so this
       is read off any line that carries it.

    2. The event alone, ``"BRASA Carnival C26"``. There is nothing in the text
       to distinguish that from any other short memo -- "VOX Q225 Theatre
       Software" is the same shape and is not an event -- so it is only read
       off a document Workday calls an Internal Service Delivery, which is LNL
       invoicing somebody and is therefore about work LNL did.

    Neither shape is trusted on its own. Both hand back a name that
    :func:`suggest_linked_event` still has to match exactly against the events
    table, and that exact match is what makes shape 2 safe: a memo naming
    software matches no event and fills nothing in.
    """
    prefixed = event_name_from_memo(txn.memo)
    if prefixed:
        return prefixed
    if (txn.document_type or '').strip().lower() != ISD_DOCUMENT_TYPE:
        return ''
    return _collapse(WPI_TERM_CODE.sub(' ', txn.memo or ''))


def suggest_linked_event(txn):
    """
    The event an ISD memo names, matched against lnldb by name.

    The memo is not evidence *about* which event this is; it is somebody
    writing down which event this is, at the time they raised the invoice.
    Matching it is reading their answer, the same as reading a funding request
    number out of an expense memo.

    Matching is exact on the name, case-insensitively. Nothing fuzzy: a filled
    box is the one nobody re-reads, so a near-miss that silently attributes
    thousands of dollars of revenue to the wrong show is far worse than an
    empty box the Treasurer fills in by hand. When the same event name has run
    in several years, the one nearest the accounting date wins and the reason
    names its date so the year can be checked at a glance.

    Returns a :class:`Suggestion` or ``None``.
    """
    from events.models import BaseEvent

    if txn.net_amount <= 0:
        return None

    name = event_name_from_transaction(txn)
    if not name:
        return None

    matches = list(BaseEvent.objects.filter(
        event_name__iexact=name, cancelled=False, test_event=False,
    ).select_related('billing_org')[:10])
    if not matches:
        return None

    # An annual event has one row per year. The memo carries a term code, but
    # it has already been stripped to get a clean name, and the accounting date
    # is the better signal anyway: an ISD is raised within weeks of the show.
    event = min(matches, key=lambda e: abs((e.datetime_start.date()
                                            - txn.accounting_date).days))
    return Suggestion(
        event.pk, HIGH,
        'Memo names this event (%s)' % date_format(event.datetime_start, 'M j, Y'),
        str(event), source=EXPORT)


# -- the same question asked of a cost ----------------------------------------
#
# A sub-rental hired for one show is that show's cost, and the memo usually
# says which show -- but not in a house format. Rental invoices are written by
# whoever placed the order, so the event turns up in brackets ("DT projector
# rental (Drag Show D25)"), as the whole description ("Equipment rental for
# Touch of Africa event") or folded into prose ("WPI Pan Asian Festival
# lighting and sound rental"). The first two can be matched exactly; the third
# can only be guessed at.

#: How far from the accounting date an exactly-named event may sit, when the
#: memo carries no term code to say when it was. Wide, because an invoice can
#: land months after the show, and safe to be wide because the name has to
#: match outright.
EXPENSE_EVENT_LOOKUP_DAYS = 180

#: Roughly when each WPI term runs, as the first and last month of the calendar
#: year its code names: ``D25`` is March to May **2025**, ``A25`` August to
#: October 2025. The year matters more than the months. The Theatre department
#: bills projector hire in batches, so ``DT projector rental (Drag Show D25)``
#: arrives in October 2025 for the spring show -- and nearest-to-the-charge
#: would pick the *next* spring's Drag Show instead.
WPI_TERM_MONTHS = {'A': (8, 10), 'B': (10, 12), 'C': (1, 3), 'D': (3, 5), 'E': (5, 8),
                   'CM': (5, 6)}

#: Slack either side of a term, for the shows that straddle a boundary -- NSO
#: runs in the week before A-term starts.
WPI_TERM_SLACK_DAYS = 21

#: The window a *guessed* event has to fall in: rentals are invoiced after the
#: show far more often than before it, and a guess needs every narrowing it can
#: get.
EXPENSE_EVENT_GUESS_BEFORE_DAYS = 60
EXPENSE_EVENT_GUESS_AFTER_DAYS = 30

#: Within this fraction of the line, the rentals billed on an event count as
#: the same money -- LNL hired the gear and passed its cost straight through.
EXPENSE_EVENT_RENTAL_TOLERANCE = Decimal('0.10')

#: Words a rental memo shares with half the events in lnldb, so finding one in
#: both says nothing about which show it was.
EVENT_NAME_STOPWORDS = frozenset((
    'and', 'for', 'the', 'with', 'from', 'wpi', 'lnl', 'lens', 'lights', 'light',
    'services', 'service', 'rental', 'rentals', 'rent', 'hire', 'equipment', 'gear',
    'lighting', 'sound', 'audio', 'video', 'stage', 'staging', 'projector',
    'projection', 'invoice', 'event', 'events', 'show', 'expenses', 'expense',
))


def _event_label(event):
    """ How a suggested event reads on a chip: the name, and when it ran. """
    return '%s · %s' % (event.event_name, date_format(event.datetime_start, 'M j, Y'))


def term_window(text):
    """
    ``(first day, last day)`` of the WPI term a piece of text names, or ``None``.

    The first term code found wins, widened by :data:`WPI_TERM_SLACK_DAYS` on
    each side. See :data:`WPI_TERM_MONTHS` for why the code is read rather than
    thrown away.
    """
    match = WPI_TERM_CODE.search(text or '')
    if not match:
        return None
    code = match.group(0).upper()
    letter, year = (code[:2], code[2:]) if code.startswith('CM') else (code[:1], code[1:])
    first, last = WPI_TERM_MONTHS[letter]
    year = 2000 + int(year)
    slack = datetime.timedelta(days=WPI_TERM_SLACK_DAYS)
    return (datetime.date(year, first, 1) - slack,
            datetime.date(year, last, calendar.monthrange(year, last)[1]) + slack)


def event_names_in_expense_memo(txn):
    """
    Every piece of an expense memo that might be an event's name, as written.

    Bracketed segments first, because that is where an event is most often
    parked; then the house-format description; then the memo whole. Each is
    offered with its term code stripped, as :func:`event_name_from_memo` does,
    and as written, because lnldb names some shows with the term and some
    without -- ``Goat Talent C26`` sits beside ``Pan Asian Festival``.
    """
    memo = txn.journal_line_memo or txn.memo or ''
    pieces = re.findall(r'\(([^()]+)\)', memo)
    pieces.append(parse_memo(memo).description)
    pieces.append(memo)
    out = []
    for piece in pieces:
        for name in (_collapse(WPI_TERM_CODE.sub(' ', piece or '')), _collapse(piece)):
            if len(name) >= 3 and name.lower() not in (n.lower() for n in out):
                out.append(name)
    return out


def _distinctive_words(text):
    """
    The words in ``text`` worth matching an event name on.

    A trailing two-digit year comes off ("NSO25" is NSO), term codes go
    entirely, and anything on :data:`EVENT_NAME_STOPWORDS` or shorter than three
    letters is dropped.
    """
    words = set()
    for word in re.findall(r'[a-z0-9]+', WPI_TERM_CODE.sub(' ', text or '').lower()):
        word = re.sub(r'^([a-z]+)\d{2}$', r'\1', word)
        if len(word) >= 3 and word not in EVENT_NAME_STOPWORDS:
            words.add(word)
    return words


def _rentals_total(event):
    """ What the event billed its client for hired-in gear, before LNL's fee. """
    return sum((money(rental.totalcost) for rental in event.rentals.all()), ZERO)


def suggest_expense_event(txn, spend_category=None):
    """
    The event a cost was incurred for, when the memo says so.

    Two answers, and they are not the same kind of thing:

    * **An exact name.** A bracketed segment, the description, or the memo
      whole matching an event's name outright, case-insensitively and without
      the term code. That is somebody writing down which show the money was for,
      so it fills the box in, the same as an ISD memo does for revenue.
    * **A resemblance.** On a line that looks like an event cost -- filed to the
      pass-through category, or a memo that says "rental" -- the events either
      side of the date whose names share a distinctive word with the memo. One
      chip at most, and only when one event leads outright: the queue used to
      offer five scored guesses under the revenue box, and five guesses is a
      puzzle rather than a shortcut. Gear the event billed its client for at
      about this price breaks a tie, because a pass-through is exactly that.

    ``spend_category`` is the category suggestion already worked out for this
    line, if any; it decides whether guessing is worth doing at all.

    Returns a :class:`Suggestion` or ``None``.
    """
    from events.models import BaseEvent

    from finance.models import event_passthrough_category

    if txn.net_amount >= 0:
        return None

    memo = txn.journal_line_memo or txn.memo or ''
    # A term code in the memo says when the show was, which beats any window
    # drawn round the date the money moved. See WPI_TERM_MONTHS.
    term = term_window(memo)

    names = event_names_in_expense_memo(txn)
    if names:
        reach = datetime.timedelta(days=EXPENSE_EVENT_LOOKUP_DAYS)
        named = Q()
        for name in names:
            named |= Q(event_name__iexact=name)
        matches = list(BaseEvent.objects.filter(
            named, cancelled=False, test_event=False,
            datetime_start__date__range=term or (txn.accounting_date - reach,
                                                 txn.accounting_date + reach))[:10])
        if matches:
            event = min(matches, key=lambda e: abs((e.datetime_start.date()
                                                    - txn.accounting_date).days))
            return Suggestion(
                event.pk, HIGH,
                'Memo names this event (%s)' % date_format(event.datetime_start, 'M j, Y'),
                _event_label(event), source=MEMO)

    passthrough = event_passthrough_category()
    looks_like_event_cost = (
        'rental' in memo.lower()
        or (passthrough is not None and spend_category is not None
            and spend_category.value == passthrough.pk))
    wanted = _distinctive_words(memo)
    if not looks_like_event_cost or not wanted:
        return None

    window = term or (
        txn.accounting_date - datetime.timedelta(days=EXPENSE_EVENT_GUESS_BEFORE_DAYS),
        txn.accounting_date + datetime.timedelta(days=EXPENSE_EVENT_GUESS_AFTER_DAYS))
    candidates = (BaseEvent.objects
                  .filter(cancelled=False, test_event=False,
                          datetime_start__date__range=window)
                  .prefetch_related('rentals'))

    cost = -money(txn.net_amount)
    scored = []
    for event in candidates:
        shared = wanted & _distinctive_words(event.event_name)
        if not shared:
            continue
        score = Decimal(len(shared))
        billed = _rentals_total(event)
        if billed:
            score += Decimal('0.5')
            if abs(billed - cost) <= cost * EXPENSE_EVENT_RENTAL_TOLERANCE:
                score += 1
        distance = abs((event.datetime_start.date() - txn.accounting_date).days)
        scored.append((score, -distance, event, shared))
    if not scored:
        return None

    scored.sort(key=lambda row: (row[0], row[1]), reverse=True)
    best = scored[0]
    # A tie on the evidence is a question, not an answer. Being nearer in date
    # is not evidence of which show it was, so it orders the list but never
    # breaks a tie on its own.
    if len(scored) > 1 and scored[1][0] == best[0]:
        return None

    score, _, event, shared = best
    return Suggestion(
        event.pk, MEDIUM,
        'Memo shares "%s" with this event (%s) -- check it'
        % ('", "'.join(sorted(shared)), date_format(event.datetime_start, 'M j, Y')),
        _event_label(event), source=GUESS)


# ---------------------------------------------------------------------------
# Refunds
#
# Workday does not say a line is a refund. What it does is emit the reversal
# the same way it emitted the charge -- same memo, same spend category, same
# payee -- with the sign turned round, and that is a good deal more than a
# resemblance: it is the original line, quoted back.
# ---------------------------------------------------------------------------

def _payee_of(txn):
    """ Who a bank line actually names, or ``''`` where it names nobody. """
    return (txn.supplier or txn.employee or '').strip().lower()


def _payees_agree(one, other):
    """
    Whether two bank lines name the same counterparty.

    An Internal Service Delivery names neither side -- both are WPI -- so a
    line with no payee at all does not disagree with anything. Its memo is
    carrying the identity instead, and the memo has already had to match
    exactly to get this far.
    """
    left, right = _payee_of(one), _payee_of(other)
    if not left or not right:
        return True
    return left == right


def _same_text(one, other):
    """ Two export fields, compared the way a person reads them. """
    return _collapse(one).lower() == _collapse(other).lower()


def _uncredited(queryset):
    """ Purchases not already given back in full, which cannot take a refund. """
    return queryset.annotate(_credited=Coalesce(
        Sum('refunds__amount'), Value(Decimal('0.00')),
        output_field=DecimalField(max_digits=12, decimal_places=2))
    ).exclude(_credited__gte=F('amount') * Value(-1))


def suggest_refund_target(txn):
    """
    The purchase a credit gives back, when the export quotes it back to us.

    A reversal in Workday is the original line re-emitted with the sign turned
    round: the same Journal Line Memo, the same Workday spend category, the
    same supplier, the same amount. Four fields agreeing exactly is not a
    resemblance between two purchases, it is one purchase described twice, and
    treating it as anything less was making the Treasurer hunt an earlier row
    out of a dropdown to say what the file had already said.

    So this fills the box in, and the row says what it matched on. Two things
    it will not do:

    * fill it in on a partial agreement -- a credit for part of an order, a
      restocking fee, a vendor who bills the same wording every month at a
      different price. Only a person can tell which purchase those belong to,
      and filing a refund against the wrong one quietly hands the money back
      to a funding request line nobody spent it from;
    * fill it in when *two* earlier purchases reverse this line equally well,
      which happens when LNL buys the same thing twice. Nothing distinguishes
      them, so choosing one would be answering a question rather than reading
      an answer -- and if the two were charged to different awards, the wrong
      one gets its money back.

    The picker -- :func:`suggest_refund_targets` -- is still there for both.
    """
    reversals = _exact_reversals(txn, limit=2)
    if len(reversals) != 1:
        return None
    entry = reversals[0]
    return Suggestion(
        entry.pk, HIGH,
        'Same memo, spend category, payee and amount as this purchase on %s, with the '
        'sign turned round' % date_format(entry.effective_date, 'M j'),
        entry.picker_label, source=EXPORT)


def _exact_reversals(txn, limit=8):
    """
    Entries this credit reverses line for line. Newest first.

    Memo equality is done in SQL because it is the field that narrows hardest;
    the spend category lives inside a JSON blob and the payee has two possible
    columns, so both are compared in Python over the handful of rows that
    survive.
    """
    from finance.models import ParsedTransaction

    memo = _collapse(txn.memo)
    if txn.net_amount <= 0 or not memo:
        return []

    candidates = _uncredited(
        ParsedTransaction.objects
        .filter(parent_transaction__isnull=False,
                parent_transaction__memo__iexact=memo,
                amount=-money(txn.net_amount),
                effective_date__lte=txn.accounting_date)
        .exclude(parent_transaction=txn)
        .select_related('parent_transaction')
        .order_by('-effective_date', '-pk'))

    found = []
    for entry in candidates[:50]:
        original = entry.parent_transaction
        if not _payees_agree(original, txn):
            continue
        if not _same_text(original.worktag('spend_category'), txn.worktag('spend_category')):
            continue
        found.append(entry)
        if len(found) >= limit:
            break
    return found


def suggest_refund_targets(txn, limit=8):
    """
    Everything this credit might be giving back, best first, for the picker.

    Two pools, in order: the lines that reverse this one exactly (see
    :func:`_exact_reversals`), then earlier purchases from the same payee. The
    second pool is a genuine shortlist rather than an answer -- a partial
    credit or a restocking fee has nothing in it that identifies which purchase
    it belongs to -- so it is offered and never applied.
    """
    from finance.models import ParsedTransaction

    if txn.net_amount <= 0:
        return []

    found = _exact_reversals(txn, limit=limit)
    seen = {entry.pk for entry in found}
    if len(found) >= limit or not txn.payee:
        return found

    same_payee = _uncredited(
        ParsedTransaction.objects
        .filter(Q(parent_transaction__supplier__iexact=txn.payee) |
                Q(parent_transaction__employee__iexact=txn.payee),
                amount__lt=0,
                effective_date__lte=txn.accounting_date)
        .select_related('parent_transaction')
        .order_by('-effective_date', '-pk'))

    for entry in same_payee[:limit * 2]:
        if entry.pk in seen:
            continue
        found.append(entry)
        if len(found) >= limit:
            break
    return found


# ---------------------------------------------------------------------------
# The whole answer for one line
# ---------------------------------------------------------------------------

#: Fields ``suggest_all`` may return a :class:`Suggestion` for. The form walks
#: this rather than a list of its own, so adding a suggester here is enough to
#: have it pre-fill.
SUGGESTED_FIELDS = ('spend_category', 'fund_source', 'fr_line_target',
                    'project_tag', 'linked_event', 'refund_of', 'revenue_source',
                    'funding_request')

#: The form field each of those maps to. Spend category is the odd one out
#: because LNL's category and Workday's share a name but are different things,
#: and revenue source because the model calls it a non-event revenue type.
FIELD_NAMES = {
    'spend_category': 'lnl_spend_category',
    'fund_source': 'fund_source',
    'fr_line_target': 'fr_line_target',
    'project_tag': 'project_tag',
    'linked_event': 'linked_event',
    'refund_of': 'refund_of',
    'revenue_source': 'non_event_revenue_type',
    'funding_request': 'funding_request',
}


def suggest_all(txn, tags=None, rules=None):
    """
    Everything the ingestion queue needs for one bank line, in one call.

    The memo is parsed once here and handed down, because three of the
    suggesters below read it and it is the same sentence every time.

    ``tags`` and ``rules`` let the queue load the project list and the rule
    table once for the whole page instead of per row.
    """
    fields = memo_fields(txn)
    sga_transfer = is_sga_transfer(txn, fields)

    if txn.net_amount > 0:
        return _suggest_revenue(txn, fields, sga_transfer, tags)

    if sga_transfer:
        return _suggest_sga_return(txn, fields, tags)

    # Looked up once: the request drives the fund, the FR line and, through the
    # line, the spend category.
    funding_request, fr_line = suggest_funding_request(txn, fields=fields)

    # A number the memo quotes that lnldb has never heard of. Worth saying out
    # loud: either the request has not been entered yet or the memo is wrong,
    # and both are things to fix before this line is filed anywhere. When the
    # same number exists under another body's letter, that request is offered
    # as the likely typo.
    unmatched = fields.reference if (fields.reference and funding_request is None) else ''
    near_miss = near_miss_funding_request(unmatched) if unmatched else None

    spend_category = suggest_spend_category(txn, rules=rules, fr_line=fr_line, fields=fields)
    linked_event = suggest_expense_event(txn, spend_category=spend_category)

    return {
        'kind': 'expense',
        'memo': fields,
        'description': suggest_description(txn),
        'spend_category': spend_category,
        'fund_source': suggest_fund_source(txn, funding_request=funding_request,
                                           reference=fields.reference),
        'fr_line_target': (suggest_fr_line(funding_request, fr_line, fields)
                           or suggest_near_miss_line(unmatched, near_miss, fields)),
        'matched_request': funding_request,
        'near_miss': near_miss,
        'unknown_request': unknown_request(fields) if unmatched and near_miss is None else None,
        'project_tag': suggest_project_tag(txn, tags=tags),
        'linked_event': linked_event,
        'needs_event': _needs_event(spend_category, linked_event),
        'warning': _unmatched_reference_warning(unmatched, near_miss),
    }


def _suggest_revenue(txn, fields, sga_transfer, tags):
    """
    The revenue half of :func:`suggest_all`.

    Money coming in is one of four things, and the suggestions say which:

    * a purchase credited back, when the export quotes the purchase;
    * event billing, when an Internal Service Delivery names the show;
    * SGA paying for a funding request, when an SGA journal entry quotes it --
      source, request and fund all follow from the number;
    * some other kind of income, when Workday names the fund it went into.

    An ISD that names no show lnldb has is still event billing, so the row says
    the event is missing rather than leaving it to be noticed on the P&L.
    """
    refund = suggest_refund_target(txn)
    linked_event = suggest_linked_event(txn)
    # Only SGA's own journal entry makes a quoted request number mean "this is
    # a reimbursement". A supplier's credit quotes the request too, and is a
    # refund; its fund comes from the purchase it gives back to.
    fund = suggest_fund_source(txn, reference=fields.reference if sga_transfer else '')

    payment = request = near_miss = None
    if sga_transfer:
        payment, request, near_miss = suggest_sga_payment(txn, fields)
    unmatched = fields.reference if (sga_transfer and request is None) else ''

    multibill = None if refund is not None else suggest_multibill(txn, linked_event)
    is_isd = (txn.document_type or '').strip().lower() == ISD_DOCUMENT_TYPE
    event_named = linked_event is not None and linked_event.is_lookup

    return {
        'kind': 'revenue',
        'memo': fields,
        'description': suggest_description(txn),
        'linked_event': linked_event,
        'refund_of': refund,
        'fund_source': fund,
        # Event billing has no source of its own: the event is the answer.
        'revenue_source': (None if event_named
                           else suggest_revenue_source(txn, fields, fund, sga_transfer)),
        'funding_request': payment,
        'matched_request': request,
        'near_miss': near_miss,
        'unknown_request': unknown_request(fields) if unmatched and near_miss is None else None,
        'multibill': multibill,
        'project_tag': suggest_project_tag(txn, tags=tags),
        # LNL billing that names no event lnldb has. The P&L cannot see money
        # that is not linked to its show.
        'needs_event': bool(is_isd and refund is None and multibill is None
                            and not event_named),
        'warning': _unmatched_reference_warning(unmatched, near_miss, revenue=True),
    }


def _suggest_sga_return(txn, fields, tags):
    """
    The expense half of :func:`suggest_all`, for money SGA takes back.

    SGA reclaiming a payment -- a reimbursement it made twice -- is a journal
    entry out of the account quoting the request. It is not LNL spending, so
    no spend category, event or funding request line is offered: the request
    itself is the answer, and the fund is the one that draws on requests.
    """
    payment, request, near_miss = suggest_sga_payment(txn, fields)
    unmatched = fields.reference if request is None else ''
    return {
        'kind': 'expense',
        'memo': fields,
        'description': suggest_description(txn),
        'spend_category': None,
        'fund_source': suggest_fund_source(txn, funding_request=request,
                                           reference=fields.reference),
        'fr_line_target': None,
        'funding_request': payment,
        'matched_request': request,
        'near_miss': near_miss,
        'unknown_request': unknown_request(fields) if unmatched and near_miss is None else None,
        'sga_return': True,
        'project_tag': suggest_project_tag(txn, tags=tags),
        'linked_event': None,
        'needs_event': False,
        'warning': _unmatched_reference_warning(unmatched, near_miss, revenue=True),
    }


def _unmatched_reference_warning(reference, near_miss, revenue=False):
    """
    What the queue row says about a request number lnldb does not have.

    ``revenue`` is for SGA's own payments, which name the request itself rather
    than one of its lines.
    """
    if not reference:
        return ''
    what = 'that request' if revenue else "that request's line"
    if near_miss is not None:
        return ('The memo quotes %s, which is not in lnldb, but %s (%s) has the same number. '
                "If one of the letters is a typo, pick %s; if not, enter %s."
                % (reference, near_miss.reference, near_miss.name, what, reference))
    return ('The memo quotes funding request %s, which is not in lnldb. Enter the request, '
            'or route this line by hand.' % reference)


def _needs_event(spend_category, linked_event):
    """
    Whether a cost is filed as passed through to an event without naming one.

    The pass-through category exists to say "this was one show's cost", so a
    line headed there with no event filled in is a line whose most useful
    answer is still missing -- and the event P&L cannot see it.
    """
    from finance.models import event_passthrough_category

    passthrough = event_passthrough_category()
    if passthrough is None or spend_category is None:
        return False
    if spend_category.value != passthrough.pk:
        return False
    return linked_event is None or not linked_event.is_lookup


def lookups_for_form(suggestions):
    """
    ``{form field: Suggestion}`` for the answers a form may fill in.

    This is the whole of what the reconciliation form is allowed to pre-select
    -- see the module docstring for why a guess is deliberately not here.
    """
    out = {}
    for key in SUGGESTED_FIELDS:
        suggestion = suggestions.get(key)
        if suggestion is not None and suggestion.is_lookup:
            out[FIELD_NAMES[key]] = suggestion
    return out


# ---------------------------------------------------------------------------
# Matching an encumbrance to the bank line that finally settles it
# ---------------------------------------------------------------------------

#: How far either side of the accounting date an encumbrance may sit and still
#: be offered. Wide on the earlier side because that is the whole point of an
#: encumbrance -- gear ordered in June can clear in September -- and narrow on
#: the later side, where the only honest case is someone logging the purchase a
#: few days after it already went through.
ENCUMBRANCE_LOOKBACK_DAYS = 365
ENCUMBRANCE_LOOKAHEAD_DAYS = 30

#: Within this fraction of the bank amount, an encumbrance is close enough to
#: be worth warning about on the row itself. Everything inside the date window
#: is still offered in the picker -- a badly estimated match is still a match,
#: and only a person can tell -- but a $900 reservation and a $12 charge should
#: not put a warning on each other, or the warning stops being read.
ENCUMBRANCE_CLOSE_ENOUGH = Decimal('0.25')


def encumbrance_match_score(entry, txn):
    """
    How well one pending encumbrance fits a bank line. Lower sorts first.

    Deliberately **not** symmetric about the line's amount, because the two
    directions mean opposite things. A reservation smaller than the charge has
    failed to cover it and something else will have to; a reservation larger
    than the charge is the ordinary shape of the whole feature -- one
    encumbrance written for a job that Workday delivers as ten invoice lines --
    and penalising it by the difference would bury a $1,000 reservation under
    every $80 stray on an $80 line, which is exactly the case a Treasurer opens
    this picker to find.

    So the signals, in the order a person weighs them:

    1. **What it fails to cover**, ignoring a shortfall small enough that the
       reservation will simply stretch over it -- see
       :func:`finance.views.ingest.draw_from_encumbrance`, which does the
       stretching, and :data:`ENCUMBRANCE_CLOSE_ENOUGH`, which bounds it.
    2. **Whether the payee is named** in what somebody typed.
    3. **How much would be left over**, so the tightest sufficient reservation
       is offered ahead of a larger one that would also do.
    4. **How far apart the dates are**, last: an encumbrance is written weeks
       before the charge by definition, so this separates near-ties and nothing
       more.
    """
    target = abs(money(txn.net_amount))
    reserved = abs(money(entry.amount))
    if not target:                                          # pragma: no cover
        return (1.0, 1, 1.0, 0)

    uncovered = max(target - reserved, ZERO)
    # A shortfall this small is the estimate being an estimate, and the draw
    # will cover the line anyway, so it is not held against the match.
    if uncovered <= target * ENCUMBRANCE_CLOSE_ENOUGH:
        uncovered = ZERO
    surplus = max(reserved - target, ZERO)

    payee = (txn.payee or '').strip().lower()
    haystack = ' '.join(filter(None, (entry.description, entry.audit_explanation))).lower()
    names_payee = bool(payee) and payee in haystack

    days = abs((entry.effective_date - txn.accounting_date).days)
    return (float(uncovered / target), 0 if names_payee else 1,
            float(surplus / target), days)


def suggest_encumbrance_matches(txn, limit=8):
    """
    Pending encumbrances that this bank line might be the arrival of.

    An encumbrance is money reserved before the purchase reaches Workday, so
    the line that eventually settles it has to be recognised by resemblance:
    there is no shared identifier, and there cannot be one -- the encumbrance
    was written before Workday had ever heard of the charge.

    Deliberately a shortlist, not an answer. Nothing here is auto-applied and
    nothing is pre-selected: getting this wrong files a purchase against the
    wrong budget line and marks a genuine commitment as spent, and neither is
    visible afterwards. The filters are only what would be *wrong* to offer
    (revenue, already-matched, absurd dates); everything else is ranking.
    """
    from finance.models import ParsedTransaction, TransactionStatus

    # Revenue never settles an encumbrance: you cannot reserve money coming in.
    if txn.net_amount >= 0:
        return []

    earliest = txn.accounting_date - datetime.timedelta(days=ENCUMBRANCE_LOOKBACK_DAYS)
    latest = txn.accounting_date + datetime.timedelta(days=ENCUMBRANCE_LOOKAHEAD_DAYS)

    candidates = (ParsedTransaction.objects
                  .filter(parent_transaction__isnull=True,
                          status=TransactionStatus.PENDING,
                          amount__lt=0,
                          effective_date__range=(earliest, latest))
                  .select_related('lnl_spend_category', 'fund_source',
                                  'fr_line_target__funding_request'))

    return sorted(candidates, key=lambda entry: encumbrance_match_score(entry, txn))[:limit]


def encumbrance_match_is_close(entry, txn):
    """
    Whether this candidate is near enough to flag the bank line on sight.

    The picker offers everything in the window; this decides what the row says
    before anyone opens it. See :data:`ENCUMBRANCE_CLOSE_ENOUGH`.
    """
    target = abs(money(txn.net_amount))
    if not target:                                          # pragma: no cover
        return False
    return abs(abs(money(entry.amount)) - target) / target <= ENCUMBRANCE_CLOSE_ENOUGH


def encumbrance_match_label(entry, txn):
    """
    One encumbrance as it reads in the picker.

    The gap against the bank line is on the label because it is the thing that
    decides whether this is the right row, and working it out in your head from
    two numbers on opposite sides of a dropdown is exactly the sort of small
    arithmetic that gets skipped.
    """
    reserved = abs(money(entry.amount))
    actual = abs(money(txn.net_amount))
    difference = actual - reserved
    if not difference:
        gap = "exact match"
    else:
        gap = "%s %s" % (money(abs(difference)), "over" if difference > 0 else "under")
    return "%s — $%s reserved %s · %s" % (
        entry.description or "(no description)", reserved,
        date_format(entry.effective_date, 'M j, Y'), gap)
