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
    one; see :attr:`finance.models.FundSource.is_default`.

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
import datetime
import re
from decimal import Decimal

from django.db.models import DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils.formats import date_format

from finance.models import (ZERO, FundSource, ProjectTag, SuggestionRule,
                            default_fund_source, fund_source_for_workday_fund,
                            normalise_term, spend_category_named, money)

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
#: One letter for the term the request was heard in, the fiscal year, then the
#: number within that year.
FR_REFERENCE = re.compile(r'\b([A-Za-z])\.(\d{2})\.(\d+)\b')


def funding_request_references(text):
    """ Every SGA request number mentioned in a piece of text, normalised. """
    return ['%s.%s.%s' % (letter.upper(), year, number)
            for letter, year, number in FR_REFERENCE.findall(text or '')]


def normalise_reference(value):
    """
    Strip whitespace and upper-case a request number so it can be compared.

    Treasurers write the same reference as "F.26.6", "f.26.6" and "F. 26. 6";
    all three have to match the one stored on the funding request.
    """
    return re.sub(r'\s+', '', (value or '')).upper()


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

def suggest_fund_source(txn, funding_request=None, unmatched_reference=None):
    """
    Which pot of money paid for this, in descending order of evidence.

    1. **A funding request number in the memo.** That money is a specific SGA
       award, so the fund is whichever bucket is marked as requiring a request
       line.
    2. **The Fund worktag**, through the code list on each :class:`FundSource`.
       Which Workday code means which LNL bucket is WPI's numbering and LNL's
       bookkeeping convention, so it is typed into the admin rather than
       compiled in here. A fund with no codes configured is never chosen this
       way -- which matters, because 810-FD is the agency fund *all* of LNL's
       spending comes out of and identifies nothing at all.
    3. **The default**, if a Treasurer has named one. What is left after the
       two passes above is a line that quotes no award and carries no fund code
       anyone has mapped, and which bucket *that* is, is LNL's bookkeeping
       convention rather than anything this module can work out -- so it is a
       flag on the fund row, set from the admin. This is stated rather than
       read, and the queue's caption says so in those words: it does not claim
       the export answered.

    That third pass is a deliberate change of mind. Leaving the fund blank was
    the honest thing to do while the alternative was inferring it from a
    worktag that says nothing; it is not the honest thing to do when a
    Treasurer can write the fallback down once in the admin. Fund is required
    on every expense, so a blank box was a typing job repeated down the whole
    queue, and the row that gets no attention is the row where every box needed
    filling in equally.

    ``unmatched_reference`` is the safety catch on the first pass. When a memo
    quotes a request number and lnldb has no such request, every later pass
    would be answering a different question from the one the memo asked, so
    nothing is offered and the queue says why.
    """
    if funding_request is not None:
        source = FundSource.objects.filter(requires_funding_request=True,
                                           is_active=True).first()
        if source is None:
            # No fund is configured to draw on a request, so there is nothing
            # right to offer -- and falling through would be actively wrong:
            # the memo has just said this is award money, and the passes below
            # would answer with the standing budget.
            return None
        return Suggestion(source.pk, HIGH,
                          'Memo quotes %s' % funding_request.reference, str(source),
                          source=MEMO)

    if unmatched_reference:
        return None

    fund = txn.worktag('fund')
    source = fund_source_for_workday_fund(fund)
    if source is not None:
        return Suggestion(source.pk, HIGH, 'Workday fund "%s"' % fund, str(source),
                          source=EXPORT)

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
                    'project_tag', 'linked_event', 'refund_of')

#: The form field each of those maps to. Spend category is the odd one out
#: because LNL's category and Workday's share a name but are different things.
FIELD_NAMES = {
    'spend_category': 'lnl_spend_category',
    'fund_source': 'fund_source',
    'fr_line_target': 'fr_line_target',
    'project_tag': 'project_tag',
    'linked_event': 'linked_event',
    'refund_of': 'refund_of',
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

    if txn.net_amount > 0:
        return {
            'kind': 'revenue',
            'memo': fields,
            'description': suggest_description(txn),
            'linked_event': suggest_linked_event(txn),
            'refund_of': suggest_refund_target(txn),
            'project_tag': suggest_project_tag(txn, tags=tags),
            'warning': '',
        }

    # Looked up once: the request drives the fund, the FR line and, through the
    # line, the spend category.
    funding_request, fr_line = suggest_funding_request(txn, fields=fields)

    # A number the memo quotes that lnldb has never heard of. Worth saying out
    # loud: either the request has not been entered yet or the memo is wrong,
    # and both are things to fix before this line is filed anywhere.
    unmatched = fields.reference if (fields.reference and funding_request is None) else ''

    return {
        'kind': 'expense',
        'memo': fields,
        'description': suggest_description(txn),
        'spend_category': suggest_spend_category(txn, rules=rules, fr_line=fr_line,
                                                 fields=fields),
        'fund_source': suggest_fund_source(txn, funding_request=funding_request,
                                           unmatched_reference=unmatched),
        'fr_line_target': suggest_fr_line(funding_request, fr_line, fields),
        'funding_request': funding_request,
        'project_tag': suggest_project_tag(txn, tags=tags),
        'warning': ('The memo quotes funding request %s, which is not in lnldb. Enter the '
                    'request, or route this line by hand.' % unmatched) if unmatched else '',
    }


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
