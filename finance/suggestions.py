"""
Auto-suggest routing.

Everything here is advisory: nothing is written without a human submitting the
form. What separates the two kinds of answer is where they came from.

A **lookup** is something the export already states, read through a table a
Treasurer maintains: the ledger account, Workday's own spend category, a
funding request number written into the memo, a project code. There is no
opinion in it, so the reconciliation form fills the box in and says which
column it came from.

An **inference** is our own reading of the line: a word spotted in some prose,
a resemblance we noticed. Those are offered as a chip to click and never fill
anything in by themselves.

Linking an event is a lookup rather than an inference, which is worth spelling
out because it was the other way round for a while. The ISD memo LNL bills
event work through *names the event*, so reading it is reading an answer
somebody already wrote down -- see :func:`suggest_linked_event`. What replaced
was a scorer that ranked candidate events by date proximity and billed total
and offered its best five; those were genuine guesses, and five guesses under a
box is not a shortlist, it is a puzzle.

Both carry a confidence for the UI to colour, but ``is_lookup`` is what decides
whether the Treasurer is confirming or being asked.
"""
import datetime
import re
from decimal import Decimal

from django.db.models import Q
from django.utils.formats import date_format

from finance.models import (ZERO, FundSource, ProjectTag, SuggestionRule,
                            fund_source_for_workday_fund, money)

HIGH, MEDIUM, LOW = 'high', 'medium', 'low'


def active_suggestion_rules():
    """ The rule table in priority order, category preloaded. """
    return list(SuggestionRule.objects.filter(is_active=True,
                                              spend_category__is_active=True)
                .select_related('spend_category'))


class Suggestion(object):
    """
    One proposed value for one field.

    ``is_lookup`` marks the answer as read out of the export rather than
    reasoned about, which is what entitles it to pre-fill the form. See the
    module docstring.
    """

    def __init__(self, value, confidence, reason, label='', is_lookup=False):
        """ Hold the proposed ``value`` together with why it is being proposed. """
        self.value = value
        self.confidence = confidence
        self.reason = reason
        self.label = label
        self.is_lookup = is_lookup

    def __repr__(self):
        return "<Suggestion %s (%s%s)>" % (self.value, self.confidence,
                                           ', lookup' if self.is_lookup else '')

    @property
    def css_class(self):
        """ The Bootstrap suffix for this suggestion's confidence badge. """
        return {HIGH: 'success', MEDIUM: 'info', LOW: 'default'}.get(self.confidence, 'default')


def suggest_spend_category(txn, rules=None):
    """
    Work out the LNL spend category from what Workday already recorded.

    Rules are stored, not coded: a Treasurer maps a new account or a newly
    invented Workday category from the admin without a deploy. They are tried
    in priority order and the first match wins, and the seeded order runs from
    the most specific evidence to the least:

    1. Workday's own Spend Category, matched **exactly**. It is the finest code
       in the export -- "Printing" and "Supplies - Medical" both sit under the
       ledger account 71100:Supplies, and they are not the same thing.
    2. The **ledger account**, matched on its number. Coarser, but still a code
       WPI assigned; it catches Workday categories nobody has mapped yet.
    3. Anything matched by wording, which is a guess and stays a chip.

    ``rules`` lets a caller rendering many rows load the table once.
    """
    for rule in (active_suggestion_rules() if rules is None else rules):
        if rule.matches(txn):
            return Suggestion(rule.spend_category_id, rule.confidence,
                              rule_reason(rule, txn), str(rule.spend_category),
                              is_lookup=rule.is_lookup)
    return None


def rule_reason(rule, txn):
    """ Human explanation shown on the auto-suggest badge. """
    if rule.match_field == SuggestionRule.LEDGER_ACCOUNT:
        return 'Ledger account %s' % (txn.ledger_account or rule.pattern)
    if rule.match_field == SuggestionRule.SPEND_CATEGORY:
        return 'Workday spend category "%s"' % txn.worktag('spend_category')
    if rule.match_field == SuggestionRule.SUPPLIER:
        return 'Supplier "%s"' % txn.payee
    return 'Memo mentions "%s"' % rule.pattern


def unmapped_spend_categories(transactions, rules=None):
    """
    Workday spend categories on these lines that no rule accounts for.

    Every unmapped value is a category the Treasurer will have to pick by hand
    on every line that carries it, so the importer reports them: one row in the
    admin retires the question permanently.
    """
    rules = active_suggestion_rules() if rules is None else rules
    missing = {}
    for txn in transactions:
        value = (txn.worktag('spend_category') or '').strip()
        if not value or any(rule.matches(txn) for rule in rules):
            continue
        missing[value] = missing.get(value, 0) + 1
    return sorted(missing.items(), key=lambda kv: (-kv[1], kv[0]))


# An SGA request number as it appears in a memo: F.26.6, A.26.115, F.25.33.
# One letter for the term the request was heard in, the fiscal year, then the
# number within that year.
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


def suggest_funding_request(txn):
    """
    Find the funding request whose number the memo quotes.

    Workday memos routinely carry the SGA request they were approved under --
    "Truman Show Film Rights (F.26.6)", "Rights for Jaws (F.26.86)". That is
    the Treasurer's own reference, written down at the time, so matching it is
    a lookup rather than a guess: far better evidence than anything a vendor's
    name could offer.

    Returns ``(funding_request, line_or_None)``. The line is only offered when
    the request has exactly one, since nothing in the memo says which of
    several it belongs to.
    """
    from finance.models import FundingRequest

    references = funding_request_references(txn.memo)
    if not references:
        return None, None

    # Compared in Python rather than SQL: references are written inconsistently
    # ("F.26.6", "F 26.6") and there are only ever a handful of open requests.
    candidates = FundingRequest.objects.filter(closed=False).prefetch_related('line_items')
    wanted = {normalise_reference(reference) for reference in references}
    for funding_request in candidates:
        if normalise_reference(funding_request.reference) in wanted:
            lines = list(funding_request.line_items.all())
            return funding_request, lines[0] if len(lines) == 1 else None
    return None, None


def suggest_fund_source(txn, funding_request=None, unmatched_reference=None):
    """
    Read the fund bucket off the memo, and off the Workday Fund worktag only
    where that worktag actually identifies a bucket.

    Two things can settle this, and neither is a guess:

    * A funding request number in the memo. That money is a specific SGA award,
      so the fund is whichever bucket is marked as requiring a request line.
    * The Fund worktag, through the code list on each :class:`FundSource`.
      Which Workday code means which LNL bucket is WPI's numbering and LNL's
      bookkeeping convention, so it is typed into the admin rather than
      compiled in here. A fund with no codes configured is never chosen.

    What the worktag cannot settle is anything about SGA. 810-FD is the agency
    fund all of LNL's spending comes out of, whoever is paying: standing budget,
    out-of-cycle award and legacy money are indistinguishable on the worktag,
    so no bucket is mapped to it and 810-FD lines are simply left blank for the
    Treasurer. Reading "SGA Budget" off a code every line carries is not a
    lookup, and pre-filling it is worse than leaving it empty, because a filled
    box is the one nobody checks.

    ``unmatched_reference`` is the safety catch for the memo half. When a memo
    quotes a request number and lnldb has no such request, guessing at some
    other bucket would be quietly wrong, so nothing is offered and the queue
    says why.
    """
    if funding_request is not None:
        source = FundSource.objects.filter(requires_funding_request=True,
                                           is_active=True).first()
        if source is not None:
            return Suggestion(source.pk, HIGH,
                              'Memo quotes %s' % funding_request.reference, str(source),
                              is_lookup=True)

    if unmatched_reference:
        return None

    fund = txn.worktag('fund')
    source = fund_source_for_workday_fund(fund)
    if source is None:
        return None
    return Suggestion(source.pk, HIGH, 'Workday fund "%s"' % fund, str(source),
                      is_lookup=True)


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
                              str(tag), is_lookup=True)
    return None


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


def _collapse(text):
    """ One space between words, nothing at either end. """
    return re.sub(r'\s+', ' ', text or '').strip()


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

    This is a lookup, not an inference, and the distinction is the whole reason
    it may pre-select where :func:`suggest_events` could only ever offer. The
    memo is not evidence *about* which event this is; it is somebody writing
    down which event this is, at the time they raised the invoice. Matching it
    is reading their answer, the same as reading a funding request number out
    of an expense memo.

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
        str(event), is_lookup=True)


#: Fields ``suggest_all`` may return a :class:`Suggestion` for. The form walks
#: this rather than a list of its own, so adding a suggester here is enough to
#: have it pre-fill.
SUGGESTED_FIELDS = ('spend_category', 'fund_source', 'fr_line_target',
                    'project_tag', 'linked_event')

#: The form field each of those maps to. Spend category is the odd one out
#: because LNL's category and Workday's share a name but are different things.
FIELD_NAMES = {
    'spend_category': 'lnl_spend_category',
    'fund_source': 'fund_source',
    'fr_line_target': 'fr_line_target',
    'project_tag': 'project_tag',
    'linked_event': 'linked_event',
}


def suggest_all(txn, tags=None, rules=None):
    """
    Everything the ingestion queue needs for one bank line, in one call.

    ``tags`` and ``rules`` let the queue load the project list and the rule
    table once for the whole page instead of per row.
    """
    if txn.net_amount > 0:
        return {
            'kind': 'revenue',
            'linked_event': suggest_linked_event(txn),
            'project_tag': suggest_project_tag(txn, tags=tags),
            'warning': '',
        }
    # Looked up once: the request drives both the fund and the FR line.
    funding_request, fr_line = suggest_funding_request(txn)

    # A number the memo quotes that lnldb has never heard of. Worth saying out
    # loud: either the request has not been entered yet or the memo is wrong,
    # and both are things to fix before this line is filed anywhere.
    quoted = funding_request_references(txn.memo)
    unmatched = quoted[0] if (quoted and funding_request is None) else ''

    return {
        'kind': 'expense',
        'spend_category': suggest_spend_category(txn, rules=rules),
        'fund_source': suggest_fund_source(txn, funding_request=funding_request,
                                           unmatched_reference=unmatched),
        'fr_line_target': (
            None if fr_line is None else
            Suggestion(fr_line.pk, HIGH, 'Memo quotes %s' % funding_request.reference,
                       fr_line.picker_label, is_lookup=True)),
        'funding_request': funding_request,
        'project_tag': suggest_project_tag(txn, tags=tags),
        'warning': ('The memo quotes funding request %s, which is not in lnldb. Enter the '
                    'request, or route this line by hand.' % unmatched) if unmatched else '',
    }


def lookups_for_form(suggestions):
    """
    ``{form field: Suggestion}`` for the answers that came out of the export.

    This is the whole of what the reconciliation form is allowed to fill in --
    see the module docstring for why an inference is deliberately not here.
    """
    out = {}
    for key in SUGGESTED_FIELDS:
        suggestion = suggestions.get(key)
        if suggestion is not None and suggestion.is_lookup:
            out[FIELD_NAMES[key]] = suggestion
    return out


def suggest_refund_targets(txn, limit=8):
    """
    For a positive line that looks like a return credit, find the original
    purchase it likely reverses: same supplier, earlier, opposite sign.
    """
    from finance.models import ParsedTransaction

    if txn.net_amount <= 0 or not txn.payee:
        return []
    return list(
        ParsedTransaction.objects.filter(
            Q(parent_transaction__supplier__iexact=txn.payee) |
            Q(parent_transaction__employee__iexact=txn.payee),
            amount__lt=0,
            effective_date__lte=txn.accounting_date,
        ).select_related('parent_transaction')
        .order_by('-effective_date')[:limit]
    )


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
