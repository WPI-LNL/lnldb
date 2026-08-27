Finance
=======

The financial subledger: a "smart bridge" between Workday (which knows how much
money LNL has) and lnldb (which knows *why*).

The module never invents financial data. It ingests Workday journal exports
verbatim, then lets the Treasurer attach internal meaning to each line by
linking it to objects lnldb already holds — Events, funding request lines and
project tags.

The two-table ledger
--------------------

Raw bank data and internal interpretation are deliberately kept in separate
tables:

``WorkdayTransaction``
    The immutable bank truth. Written only by the importer; the model
    refuses updates and deletes outright. Re-importing the same export is a
    safe no-op — see `Line identity`_ for how a line is identified, which is
    less obvious than it sounds.

``ParsedTransaction``
    A mutable *allocation slice*. Many slices may point at one bank line (the
    split-purchase case), or at none at all (an encumbrance logged before the
    bank feed catches up).

Enforced accounting rules
-------------------------

Five rules are enforced as database ``CheckConstraint``\ s, so they hold even if
application-level validation is bypassed by a bulk action, a data migration or
a shell session:

* an allocation amount is never zero;
* an encumbrance (no parent bank line) can never be ``Settled``;
* an expense or refund may not be classified as non-event revenue;
* revenue may not carry expense routing;
* a refund is always positive.

Two further rules need cross-row state and so live in ``Model.clean()`` plus a
transactional helper:

* the sum of a bank line's slices must equal its ``net_amount`` exactly before
  any slice may be marked ``Settled`` (:meth:`WorkdayTransaction.settle`);
* the partition rules, described below. The funding request's side and the
  written reason for leaving 315-AG are both re-applied in ``save()`` as well as
  ``clean()``, so they hold regardless of the code path.

The Event Production / Projection partition
-------------------------------------------

Which account paid for something and which activity it was for are different
questions, and for a while this module answered both with one field.

Two organisation codes say which account a Workday line came out of:

==========  ==================  ==============================================
Org code    Side by default     Filing it the other way
==========  ==================  ==============================================
``315-AG``  Projection          Allowed, but the entry needs a written reason
``226-AG``  Event Production    Allowed, with a warning
==========  ==================  ==============================================

They used to be locks, and that was wrong. LNL buys Projection equipment out of
the main 226-AG account whenever SGA funds it through a funding request, because
the reimbursement comes back into 226-AG. The money is 226-AG money and the
expense is a Projection expense, both at once. A lock made that entry impossible
to record, which meant the wrong one was mandatory — the worst kind of guard
rail, since it produced bad data while looking rigorous.

315-AG is different because SGA funds it directly for Projection every year, for
the things that do *not* go through funding requests. Money leaving that side is
the direction that would breach the isolation the university cares about, so
that crossing is still allowed but cannot be saved without saying why. The
asymmetry is a field, ``PartitionCode.crossing_requires_reason``, not a special
case in code, so an installation that renumbers or adds a code configures it in
the admin.

Three things decide where an entry sits, in increasing order of authority:

1. **The org code on the bank line**, which sets the starting position — the
   tick box arrives already ticked, or not.
2. **The Treasurer**, who has the final say. Crossing shows a warning wherever
   the entry appears: on the queue row, on the entry page, and as a marker in
   the ledger's partition column.
3. **The funding request**, if one is named. An award was heard as either a
   Projection request or an Event Production one, and that decision is more
   specific than which account the money happened to leave from, so choosing an
   FR line moves the entry to that side. This is applied in ``save()`` as well
   as ``clean()``, because a bulk action that silently paid a Projection award
   from the Event Production side would corrupt two burndowns at once.

.. note::

   ``is_projection`` is a plain boolean, so "Event Production" and "nobody said"
   look identical on the instance. ``ParsedTransaction`` records which it was:
   the field being passed to the constructor counts as stated, and so does a
   form that renders the tick box, via ``state_partition()``. Everything else
   takes the org code's answer. Without that distinction every slice from the
   split modal — which has no room for a column nobody usually changes — would
   quietly land on the Event Production side.

.. important::

   These codes live in Workday's **Student Organization** worktag, *not* the
   Ledger Account. A real export puts GL codes in Ledger Account
   (``71100:Supplies``, ``74100:Repairs & Maintenance``) while the org column
   reads ``226-AG Lens & Light Club``. Two separate revisions read them from
   Ledger Account; the second was the Event | Projection filter itself, which
   also hard-coded ``315-AG``, so the Projection view of the queue matched
   nothing at all.

The codes are rows in the :class:`finance.models.PartitionCode` table, each
carrying the worktag it is read from, so a renumber — or a move to a different
worktag — is an admin edit rather than a deploy. They are cached in process and
the cache is invalidated by a signal. Matching tolerates the trailing
description (``226-AG Lens & Light Club``) without matching a longer code such
as ``226-AGX``.

The Event | Projection filter treats "Event Production" as *everything that is
not* Projection, rather than ``226-AG`` only, so a line with a blank or
unfamiliar org code appears in one view rather than neither. On a bank line the
filter asks about the account, since nothing in the queue has been filed yet; on
the ledger it asks about the entry, since by then somebody has decided.

File formats
------------

The importer reads CSV and ``.xlsx`` alike. Workday will hand you either, and
which button someone happened to press should not decide whether the ledger can
read the file. :func:`finance.importers.read_table` reduces both to the same
rows-of-cells shape, and nothing downstream of it knows which one arrived.

Format is decided by the file's own bytes before its name, because browsers and
operating systems both get content types wrong and a workbook saved as ``.csv``
is a common mistake. Three things only spreadsheets do are handled there:

* Workday's export-to-Excel puts a report title and the filters used *above*
  the table, so the header row is searched for rather than assumed to be first;
* a workbook may carry several sheets — a summary tab, last term's export left
  behind — so the sheets are searched for the one holding a journal;
* cells arrive already typed, so a date needs no parsing, and a number must not
  be stringified on the way past or an Operational Transaction of ``25070087``
  becomes ``25070087.0``;
* a sheet is read at the width of the cells it actually contains, not the width
  it claims — see below.

.. warning::

   **A workbook's declared size can be a lie, and openpyxl believes it.**

   Sheet XML opens with a ``<dimension ref="A1:R300"/>`` element naming the
   extent of the table. In ``read_only`` mode openpyxl trusts it and clips
   every row to that width. Workday's exporter writes one that understates the
   table, so a thirty-column export arrived one cell wide: the header row read
   simply ``Accounting Date``, and the importer rejected a perfectly good file
   with *"This doesn't look like a Workday journal export"*.

   Nothing about it looked like a truncation bug. The file opened, the sheet
   was found, the header was located, and the only symptom was an importer
   insisting a real export was not one. Excel never showed a thing, because
   Excel ignores the element and reads the cells — so the file looks correct in
   the one place anybody would check it.

   :func:`finance.importers._read_xlsx` calls ``reset_dimensions()`` on every
   sheet, which makes openpyxl work the extent out from the cells while it
   streams. It costs nothing on a workbook whose dimension was honest.

.. note::

   Only the *delimiter* is sniffed on a CSV, never the whole dialect.
   ``csv.Sniffer`` guessed ``doublequote=False`` on the real FY26 export, which
   breaks RFC-4180's ``""`` escape: a memo reading ``Planar 22" touchscreen``
   came back with a stray quote on the end. Two lines out of 314, with nothing
   on screen to suggest it.

Reading ``.xlsx`` needs ``openpyxl``, which is in ``requirements.txt``. If it
is missing the importer says so and points at CSV rather than failing obscurely.

Line identity
-------------

Nothing Workday exports identifies a journal line.

``Operational Transaction`` names the **document**, not the line: one supplier
invoice routinely covers a dozen exported rows, and every journal entry line
carries none at all. Using it as the duplicate guard discarded 131 of the 314
lines on the FY26 226-AG export and errored on 26 more.

So identity is the whole exported row —
:func:`finance.models.workday_fingerprint` hashes the date, amount,
Operational Transaction, supplier, employee, memo and the worktags listed in
:data:`finance.models.FINGERPRINT_WORKTAGS`. That list is fixed rather than
"whatever columns the file had": if Workday adds a column, existing lines must
keep the fingerprints they already have, or the next re-import would look like
a file full of new transactions.

That still leaves a genuine ambiguity, because two identical rows can be two
real charges — the same Spotify subscription billed twice in a month. It is
settled by counting rather than guessing:

    the ledger holds as many copies of a line as the fullest export has
    ever shown

Each row therefore carries a ``fingerprint_ordinal``: which occurrence of that
line it is. A file listing the charge twice imports both, as occurrences 1 and
2. Re-uploading it imports neither, because two are already on file. A later
export covering the same period plus a third charge imports exactly the third.
The arithmetic is done per file, so ordering inside the file is irrelevant, and
``UNIQUE(row_fingerprint, fingerprint_ordinal)`` enforces it in the database as
well as the importer.

.. note::

   The known limit: an export deliberately narrowed to a single line cannot add
   a *second* copy of a charge already on file — it is indistinguishable from a
   re-upload. Those rows are reported as duplicates with the held count spelled
   out. Import the wider export, or log the odd genuine case as an encumbrance.

Because a line may have no Operational Transaction at all,
:attr:`WorkdayTransaction.reference` is what the UI shows: the Operational
Transaction if there is one, else the journal number (``25090054-JE``).

Naming the counterparty needs the same care. An Internal Service Delivery is
WPI billing WPI — LNL invoicing a department, campus shipping, Chartwells
catering — so it carries neither a Supplier nor an Employee, and neither do
journal entries. That is 94 of the 314 lines on the FY26 export, every one of
which used to read "(no payee)". :attr:`WorkdayTransaction.payee` now falls
back to :attr:`~WorkdayTransaction.document_type`, taken from the Operational
Transaction's own prefix, so those lines read "Internal Service Delivery" or
"Journal Entry" and the memo carries the rest.

Costs that belong to one event
------------------------------

``linked_event`` is the one routing field that belongs to both directions. On
revenue it means "this is what the event earned"; on an expense it means "this
cost was incurred for that event". The sign of the amount already separates the
two readings, so no third field is needed.

The case that forced it is the sub-rental: LNL hires a console for one show and
the invoice is that show's cost, passed straight through, sometimes with a
rental fee on top. Until this existed, a database constraint made
``linked_event`` revenue-only and there was nowhere to record it. The constraint
now forbids only ``non_event_revenue_type`` on the expense side.

Such an expense takes its spend category automatically, from whichever
:class:`finance.models.SpendCategory` carries ``is_event_passthrough`` -- seeded
as "Event Expense". The linked event already says what the money was for, so
making the Treasurer also choose a category is a question with no useful answer;
an explicit choice is never overwritten.

Note that these expenses stay out of the revenue charts. Those read
:func:`finance.calculators.revenue_rows`, which selects on the sign, so a cost
billed to an event never reads as income from it.

Entry types
-----------

``ParsedTransaction.entry_type`` distinguishes four shapes, because "positive
means revenue" is not quite true:

===========  ===============================  ================================
Type         Condition                        Routing
===========  ===============================  ================================
Revenue      ``amount > 0``, no refund        Event, or non-event revenue type
Expense      ``amount < 0``, has a bank line  Fund, spend category, FR line
Refund       ``amount > 0`` + ``refund_of``   Expense routing (contra-expense)
Encumbrance  ``amount < 0``, no bank line     Expense routing
===========  ===============================  ================================

A refund is a *contra-expense*, not revenue. Because expenses are stored
negative and refunds positive, a return credit restores the budget line it came
out of purely by arithmetic — no special-casing in the burndown code.

An encumbrance is money reserved for a purchase that has not happened yet, and
it read as *Expense* in the ledger's Type column until it got a word of its own.
That is not a synonym: no money has left the account, there is no bank line
behind it, and it stops being an encumbrance when the real charge is imported.
The one column whose entire job is telling rows apart was showing the two as
identical. Only the label is new — an encumbrance still carries expense routing,
still answers yes to ``is_expense``, and is still counted as spending
everywhere it was before.

Closing an encumbrance
----------------------

An encumbrance stops being one when the real charge is imported, but nothing
makes that happen by itself: the reservation was written before Workday had
ever heard of the purchase, so there is no shared identifier and there cannot
be one. The two have to be matched by a person.

The ingestion queue offers that on the bank line itself. Above the routing form
— above, because it answers a question asked earlier than "where does this go"
— a line that resembles an open reservation carries an *Already encumbered?*
picker listing the candidates, each labelled with what was reserved, when, and
how far it is from the amount that actually cleared::

    Gaff tape order — $200.00 reserved Aug 20, 2025 · 3.55 over

The ranking behind that list is deliberately **not** symmetric about the line's
amount, because the two directions mean opposite things. A reservation smaller
than the charge has failed to cover it and something else will have to; a
reservation *larger* than the charge is the ordinary shape of the whole feature,
and scoring it by the raw difference would bury a $1,000 reservation under every
$80 stray on an $80 line — the exact row the Treasurer opened the picker to find.
So :func:`~finance.suggestions.encumbrance_match_score` sorts on what a
reservation fails to cover first, ignores a shortfall small enough that the draw
will stretch over it anyway, and only then prefers the tightest sufficient
reservation. Nothing is pre-selected: matching the wrong row files a purchase
against the wrong budget line *and* marks a live commitment spent, and neither
is visible once done.

Choosing one draws that line's share out of the reservation. Two things are
decided there rather than left to the person doing it:

* **The date becomes the accounting date.** ``effective_date`` is filled in
  only when blank, so an encumbrance otherwise keeps the day it was *written*.
  A June reservation settling a July charge would sit in FY25 while its own
  bank line sits in FY26, splitting one purchase across two fiscal years on the
  ledger, the cash-flow chart and the award balance.
* **Routing is left alone.** Somebody already decided what the money was for.
  The invoice arriving is not new information about that.

Drawing down
~~~~~~~~~~~~

One reservation usually pays for more than one bank line. A single encumbrance
is written for a job and Workday then delivers it as ten invoice lines weeks
apart, so the reservation is not consumed by the first line that matches it: it
is *drawn down*, and :func:`finance.views.ingest.draw_from_encumbrance` decides
how much each line takes. Three shapes, and the arithmetic has to tell them
apart because charging the wrong one to a budget line is invisible afterwards:

============================  =========================================================
Reservation **larger**        The line takes what it needs; the reservation stays open
                              for the rest.
Line larger, **not by much**  Within :data:`~finance.suggestions.ENCUMBRANCE_CLOSE_ENOUGH`
                              the difference is estimate noise, so the reservation
                              stretches to cover the line and closes.
Line larger **by a lot**      The reservation covers only what it says. The rest of the
                              line stays in the queue to be routed on its own —
                              swallowing the difference would charge the budget line
                              money nobody reserved.
============================  =========================================================

The reservation is the row that persists. It keeps its primary key, its author
and its whole revision history across every line it pays for, and only the line
that finishes it off takes the row itself. That is what lets ten Workday lines
map to one encumbrance without the reservation's identity churning underneath
the Treasurer: it is the same row in the picker on the tenth match as on the
first, reading down towards zero. ``created_by`` on each drawn slice is the
person allocating, while the reservation keeps whoever wrote it — two different
facts, and the ledger has room for both.

Ten lines at once
~~~~~~~~~~~~~~~~~

Matching ten lines one at a time works, but it is the same repetition the bulk
bar exists to remove, with a running balance to keep in your head between
clicks. So the queue's bulk bar carries a second action beside *Reconcile
selected*: tick the rows, pick the reservation, and *Draw selected* runs the
drawdown across all of them —
:func:`finance.views.ingest.bulk_match_encumbrance`.

Oldest line first, because that is the order the money actually left and it
makes the result reproducible: the same selection and the same reservation
always produce the same allocation, whichever order the rows were ticked in. It
stops when the reservation runs out rather than stretching it, and reports all
three outcomes by name — what was covered, what was covered only partly, and
which lines it never reached. A batch that half-worked and said only
"reconciled 9 lines" is how the other half gets found a month later.

It takes no routing fields of its own, unlike the ordinary bulk reconcile: the
answer to *where does this money go* is written on the reservation already, and
asking again here would let a bulk action contradict the thing it is drawing
from.

Reconciling the line the ordinary way instead is the failure this exists to
prevent: it writes a *second* entry, so the funding request line is charged the
estimate **and** the actual, and the only symptom is a balance quietly a couple
of hundred dollars short. Hence the *Maybe encumbered* tag on any row with a
reservation of roughly the right size open against it.

Nothing here is auto-applied and nothing is pre-selected. Matching the wrong
row files a purchase against the wrong budget line *and* marks a live
commitment spent, and neither is visible once done, so
:func:`finance.suggestions.suggest_encumbrance_matches` returns a ranked
shortlist and stops there. It ranks on the amount first — the one signal a crew
member cannot be vague about — then on whether the payee appears in what they
typed, then on how close the dates are. It filters only what would be *wrong*
to offer: revenue lines, entries already on a bank line, and reservations dated
absurdly far from the charge.

The queue's *Undo* is deliberately not offered after a match. Undo deletes a
row's allocations, which is the right way back out of an allocation typed a
second ago and the wrong way back out of an encumbrance logged weeks ago — it
would take the description, the reason and the reservation with it, none of
which came from the bank line. Correcting a wrong match is an edit on the
entry.


Guard rails
-----------

The subledger is meant to be hard to get wrong, not merely capable of being
right. Three techniques, in order of preference:

**Remove the option.** The strongest guard is a field that is not on screen.
A revenue form has no ``fund_source``, ``lnl_spend_category`` or funding
request picker; an expense form has no ``non_event_revenue_type``; and the
funding request picker is hidden even on an expense unless the chosen fund
draws on one. Nothing to mis-click. The fields are *deleted* in
:meth:`finance.forms.BaseAllocationForm._apply_direction_rules` rather than
validated away, so a revenue form is structurally incapable of submitting
expense routing even with the client-side script bypassed.

``linked_event`` is the one field that survives on both sides, because it
means something on both -- see *Costs that belong to one event* above. It is
relabelled rather than removed, so the expense form asks "Incurred for
event" and the revenue form asks "Linked event".

**Offer the likely, gate the unlikely.** Where something is legal but usually a
mistake, the usual case is the default and the exception costs one deliberate
tick. Charging FY25 spending to an FY26 funding request is the worked example:
the picker lists this year's requests, and *"Charge a different fiscal year"*
widens it. Submitting another year's line without that tick is refused by name
— "This is FY2026 spending but FY25 Grant is an FY2025 request." The same
thinking narrows the refund target list to the current year.

**Put the number where the decision is.** Every funding request line reads
``FY2026 · F.26.6 Fixtures — $340.00 left`` in the dropdown, so the year and
the remaining balance are in front of you at the moment you choose, rather than
on a page you would have to go and look at.

**Match what is written down, do not guess at it.** Workday memos routinely
quote the SGA request a purchase was approved under — "Truman Show Film Rights
(F.26.6)", "Rights for Apollo 13 (F.26.86)". That is the Treasurer's own
reference, recorded at the time, so
:func:`finance.suggestions.suggest_funding_request` matches it against
``FundingRequest.reference`` and offers both the fund and the request line at
high confidence. On the FY26 export, 18 lines quote a request number.

The funding request line is only offered when the request has exactly one:
nothing in "(F.26.86)" says which of several lines a purchase belongs to, and
an arbitrary pick would be worse than no pick.

.. note::

   The suggestion table used to ship with twelve "supplier contains barbizon →
   Consumables" rules and seven "memo contains tape → Consumables" ones. Those
   were guesses about what a vendor usually sells, and they have been removed —
   a suggestion that must be read carefully is not saving anyone anything.

   They cost nothing to lose: every expense line on the FY26 export gets its
   category from Workday's own accounting codes. The ``supplier`` and ``memo``
   match types remain available in the admin for a rule someone genuinely wants.

**Never ask twice for something already recorded.** Choosing a funding request
line fills in the spend category and project that line was awarded for — the
award already said what the money was for, so re-typing it per transaction is
the double data entry this module exists to remove. Only a box the page filled
in itself is ever overwritten: a value chosen by hand survives switching
between lines. The pairing is carried on the ``<option>`` by
:class:`finance.forms.FRLineSelect`.

The queue posts one row at a time over XHR rather than reloading. Reloading
discarded whatever was typed into the *other* rows on screen, and the queue is
designed to be worked a screenful at a time. Errors come back keyed by field so
they land beside the input that caused them. Without JavaScript the same forms
submit, redirect and report through the messages framework exactly as before.

Rules live at the layer that cannot be bypassed, and are then *repeated* higher
up for the error message. The fund/funding-request pairing is enforced in
``ParsedTransaction.clean()`` — so bulk actions, the admin and the shell all
obey it — and again in ``BaseAllocationForm`` so the message lands on the field
you have to change. Which fund needs a funding request line is
``FundSource.requires_funding_request``, a flag on the row, so it survives SGA
renaming things.

Bulk actions get particular attention, being the one place a single click can
be wrong hundreds of times. The ledger's bar refuses to offer a fund that would
need a per-entry FR line, skips revenue rows when asked to apply expense
routing (a database constraint would otherwise turn the whole action into a
500), leaves entries already charged to a funding request alone, and validates
every row individually before writing — anything the rest of the app would have
rejected is reported and left untouched.

Lookups and guesses
-------------------

Reconciling should be confirming rather than typing, so the reconciliation form
arrives with the boxes already answered. What may be answered, and what may only
be offered, is decided by where the answer came from.

A **lookup** is something the export already states, read through a table a
Treasurer maintains — the ledger account, Workday's own Spend Category, a request
number written into the memo, a project code, the Fund worktag. There is no
opinion in it, so the form selects it and captions the box with the column it
came from. An **inference** is our own reading of the line — a word noticed in
some prose, a resemblance somebody might not agree with. Those stay a chip to
click and never fill anything in, because a pre-selected dropdown gets accepted
without being read, and that is precisely the wrong thing to do with a guess.

Linking an event moved from the second category to the first, and the move is
worth understanding because it is the clearest example of the distinction.

There used to be a scorer that ranked candidate events by how close they ran to
the accounting date, whether the client worktag matched, and whether the billed
total came out the same, then offered its best five under the box. Every one of
those was a genuine guess, and five guesses is not a shortlist — it is a puzzle
handed to somebody who was trying to file a deposit.

What replaced it reads the memo. LNL bills event work through Internal Service
Deliveries, and those memos are written to a house format that names the event
outright::

    Lens and Lights services for Pan Asian Festival D26
    Lens and Lights Services for Live at the CC Window (Apr 27) D26
    LNL Services for C26 CS Social Movies

That is not evidence *about* which event the money is for. It is the person who
raised the invoice writing down which event the money is for, at the time, from
the same lnldb the reconciliation form is reading. Matching it is a lookup in
exactly the sense a funding request number quoted in an expense memo is, so it
fills the box in and captions it.

:func:`finance.suggestions.event_name_from_transaction` handles both shapes seen
in practice — the house format above, and the event name alone with just a term
code ("BRASA Carnival C26"). The bare form is only read off a document Workday
itself calls an Internal Service Delivery, because there is nothing in the text
to separate it from any other short memo.

The match is **exact**, case-insensitively, and nothing fuzzy is attempted. A
near-miss would attribute several thousand dollars of revenue to the wrong show,
and it would do it in a box already showing an answer — the one box nobody
re-reads. Where the same event name has run in several years, the one nearest
the accounting date wins, since an ISD is raised within weeks of the show, and
the caption names the event's date so the year can be checked at a glance. On
the FY26 export this fills in every one of the 58 ISD lines that names an
event, and leaves the journal entries and credit memos alone.

The distinction is a field on the rule, not a convention:
``SuggestionRule.match_mode`` is one of *is exactly*, *starts with*, *contains*
or *contains the whole word*, and the first two count as lookups. It used to be
implied by the column — ledger accounts matched their start, everything else
matched anywhere — which left an exact account code and a keyword spotted in
prose indistinguishable to whatever consumed the result.

Ordering runs from the finest evidence to the coarsest:

1. **Workday's own Spend Category, matched exactly.** The finest code in the
   export. "Printing", "Supplies - Office" and "Supplies - Medical" all sit
   under the ledger account ``71100:Supplies`` and are not the same thing.
2. **The ledger account, matched on its number.** Coarser, but still a code WPI
   assigned, so it covers Workday categories nobody has mapped yet.
3. **Anything matched by wording**, which is a guess and stays a chip.

Eleven fiscal years of 226-AG exports contain 2,644 lines, 17 ledger accounts
and 38 distinct Workday spend categories, and every expense line carries one.
The seeded table is therefore not an approximation of the chart of accounts — it
*is* the chart of accounts. Where LNL has no category meaning the same thing
(Rent - Equipment, Travel, Subscriptions & Memberships) no exact rule is seeded
on purpose: the ledger-account rule catches those at *Other*, and one admin row
promotes any of them to a category of their own.

The measured effect on the FY26 export, 253 expense lines:

===============================  =========  ==========================================
Field                            Filled in  From
===============================  =========  ==========================================
LNL spend category               253        203 Workday spend category, 50 ledger account
Fund source                      16         a funding request number in the memo
Project tag                      7          a project code appearing verbatim
===============================  =========  ==========================================

Fund source is filled in on only the 16 lines whose memo quotes a funding
request number, and that is deliberate — see below.

After an import, any Workday spend category that no rule covers is named in a
warning with a line count, because each one is a question the Treasurer would
otherwise answer by hand on every line carrying it, forever.

Fund codes are admin data
-------------------------

Which Workday Fund code means which LNL bucket was an ``if '810' in fund`` in
``suggestions.py``. It is WPI's numbering and LNL's bookkeeping convention, so
it is now ``FundSource.workday_fund_codes`` — a comma-separated list on each
fund. A fund with no codes configured is never chosen for you, which is how an
SGA award stays identified by its number rather than by a fund code.

**810-FD is mapped to nothing at all**, and that is the important part. It is
the agency fund the whole 226-AG account sits in, so every LNL line in eleven
years of exports carries it, whoever actually paid. Standing SGA budget,
out-of-cycle SGA award and legacy money are identical on the worktag. The
original ``if '810' in fund`` read it as "SGA budget" and the first pass at this
table copied that across unexamined, which meant the Fund source box arrived
pre-filled and high-confidence on nearly every line, on no evidence. An exact
code match fills the form in rather than offering a chip, so being wrong there
is expensive: a filled box is the one nobody re-reads. It is now blank on those
lines, which is what "we do not know" should look like.

Only the memo can tell the buckets apart, and when a memo quotes a request
number lnldb has never heard of, nothing is filled in at all — the queue flags
the line as *Unknown funding request* instead. Either the award has not been
entered yet or the memo is mistaken, and both are worth fixing before the line
is filed anywhere.

How a queue row is laid out
---------------------------

The queue is worked twenty-five rows at a time, so what appears on each row is
the whole usability question. Three rules, all of them enforced by structure
rather than by remembering:

**One field component, used everywhere.** Label, control, and at most one
caption underneath. It lives in ``finance/_queue_field.html`` and each field is
one ``{% include %}``. Writing it out per field is what produced four
near-identical twelve-line blocks that had already drifted apart -- different
label markup, captions beside the control on some fields and under it on
others, and inline ``style="margin-right:10px"`` on every wrapper.

**Fixed control widths, captions underneath.** The same field sits in the same
place on every row, and a row is the same height whether or not it has anything
to say, so the eye can run down a column instead of re-finding it each time. A
caption beside a control pushes the next field along by however many characters
the reason happened to be.

**Rarely-used fields fold away.** Fund and Spend Category are needed on every
expense; Project appears on seven of 253 lines in a year, a sub-rental is rarer,
and the partition tick box and the cross-year opt-in are rarer still. Those sit
behind *More*, so an ordinary row reads as two boxes and a button. The view
unfolds it per row whenever that line has something in there worth seeing --
a project we found, a partition that is not the ordinary one, a crossing that
has to be explained -- and ``queue.js`` unfolds it if a validation error lands
on a field inside, since an invisible error is worse than the clutter the fold
removes.

Two smaller things follow the same logic. Every widget gets ``form-control`` from
``BaseAllocationForm._style_widgets()``, because Django renders a bare
``<select>``, crispy adds the class itself and django-ajax-selects does its own
thing, so one row could look like three different form libraries depending on
the page. And the import drop zone is collapsed behind a button: importing
happens once a month, reconciling is what the page is for, and the drop zone was
the first thing between the Treasurer and the work.

An answered box never also nags. A field the export filled in gets a quiet
dashed caption naming the column it came from; a field we can only guess at gets
a coloured chip that fills it in when clicked. Never both -- see *Lookups and
guesses* above for which is which.

.. warning::

   A fold that only script can open is a trap rather than a tidy-up: anything
   that stops ``queue.js`` running makes those fields unreachable instead of
   merely hidden. So the fold is a class the server renders, script toggles, and
   a ``<noscript>`` rule in ``base_finance.html`` undoes -- without JavaScript
   every field is simply on screen, as it was before the fold existed.

   This is not hypothetical. The fold appeared broken the first time it shipped,
   because every finance asset was cache-busted with ``?v={{ GIT_RELEASE }}`` --
   the git SHA, which does not change between commits. Browsers kept serving the
   previous ``queue.js``, and a script that never arrives looks exactly like a
   button that does nothing. :func:`finance.templatetags.finance_extras.asset`
   now stamps the file's own modification time in development, and the release
   SHA in production, where files really do only change when a deploy does.

Two-step import
---------------

Choosing a file writes nothing. :func:`finance.views.ingest.upload` parses it
with ``dry_run``, stages the bytes in the file store and renders a confirmation
naming the count: *you are about to add 253 unreconciled lines*.
:func:`finance.views.ingest.upload_confirm` re-reads the same bytes and does the
real insert.

The count is the whole point. An import is the one action on the page that is
awkward to walk back -- every line it creates is work somebody now has to do,
and undoing it means finding and deleting them by hand. It runs once a month
against a file exported by a system nobody here controls, and the two ways it
goes wrong are picking last month's export and picking a file that is not an
export at all. Both parse perfectly, read correctly, and are obvious the moment
a number appears -- and invisible before it.

Staging exists because the file is gone by the time the question is answered: a
browser will not re-submit an ``<input type=file>`` it never kept. Staged
uploads live under ``finance/staged_imports/`` with unguessable names, and the
token is held in the session rather than in a form field, so it cannot be
replayed by anyone else. They are consumed on confirmation, deleted on cancel,
and purged after six hours by the next upload -- a confirmation left open
overnight should not quietly import itself in the morning.

Two cases skip the question, because it would be asking twice: *Preview only*,
which is already a request to look and not touch, and a file with no new lines,
where the button does nothing either way.

Reconciling in bulk
-------------------

The per-row form is the right tool when the rows differ. When they do not — a
dozen supply orders on one export, every one of them Consumables out of the
standing budget — it asks the same two questions a dozen times and gets the
same two answers a dozen times. :func:`finance.views.ingest.bulk_reconcile` is
the ledger's bulk bar pointed at the queue: select rows, answer once, apply.

Each selected line gets one slice for whatever is still unallocated on it,
which is what the single-row form does, so a part-allocated line is finished
off rather than double-counted. Every row is then validated on its own and the
failures are named — a bulk action must never be the thing that writes a row
the rest of the app would have rejected.

Three kinds of row are reported and left alone rather than forced:

* **revenue**, because "the same settings" for money coming in means "the same
  event", which is a different question with a different picker and is seldom
  true of a batch. The database refuses expense routing on revenue anyway, so
  including them would take the whole action down;
* **lines already fully allocated**, which have nothing left to slice;
* **anything the chosen settings would invalidate**, named individually.

Funds that draw on a specific funding request are not offered at all, for the
reason the ledger's bulk bar leaves them out: the FR line cannot be chosen in
bulk, so every row would come out invalid. Those are reconciled one at a time,
where the line can be named.

The checkbox appears on expense rows only. A revenue row has nothing to offer
this bar, and an empty slot keeps the amounts in their column.

Undoing a reconciliation
------------------------

The moment you notice a line was filed wrong is the moment right after you
filed it. Until :func:`finance.views.ingest.unreconcile` existed, the way back
was to leave the queue, find the line in the ledger, open each slice and delete
it through a confirmation page -- five navigations to take back one click, which
in practice meant the wrong answer stayed.

Undo deletes every slice of one bank line, settled or not; settling happens in
the same click as reconciling whenever the line balances, so an undo that
refused to touch settled slices could never undo anything. The Workday row
itself is untouched -- it is immutable bank truth, and only what LNL decided
*about* it is being withdrawn.

One case is refused rather than forced: a slice with a refund filed against it
is load-bearing, since the refund exists to reverse *that* purchase, and the
database will not orphan it. The queue says so instead of returning a 500.

In the queue the undo is offered in the row that was just allocated, for twelve
seconds, before the row is removed. The row stays in the DOM for exactly that
reason -- undoing has to put the Treasurer's own answers back in front of them,
and the only copy of those answers is the form still sitting in that row. The
transaction detail page carries the same action without a time limit, for when
it is noticed later.

What an entry has to have
-------------------------

On the entry page an expense must name its fund and its spend category. Both
are structural: the reports group by them, so a blank makes the line
uncountable.

The audit explanation and the receipt are asked for and not insisted on. They
were mandatory, and that made the page unusable for its commonest job -- fixing
a spend category chosen wrong three weeks ago meant first producing a receipt
for somebody else's purchase, or inventing a sentence about it. A line missing
its paperwork is a line to chase, not a line to lock; the entry page says
plainly when a receipt is absent, and the ledger has a Receipt column to sort
by. The encumbrance form still asks what the money is for at the point of
reserving it, which is the one moment somebody actually knows.

Cents, and only cents
---------------------

Every monetary figure crosses back into whole cents through
:func:`finance.models.money` at the point it leaves the database.

This is not belt-and-braces. Everything here is stored as
``DecimalField(decimal_places=2)``, so it is tempting to assume what comes back
is already cents -- but SQLite quantizes a plain column read and *not* an
aggregate. ``Sum('amount')`` therefore returns fifteen significant digits and
the float noise with them: ``Decimal('-2808.24000000000')`` for a column that
only ever held ``-2808.24``. Subtracting two of those gives ``Decimal('0E-11')``,
which is zero, prints as ``0E-11``, and reads to a Treasurer as a bug.

Rounding at the display layer would not have fixed it, because the raw value was
never only on screen: it reached JSON payloads, form initial data and the text
of validation errors. So the quantize happens where the number is read, not
where it is printed.

Dashboard metrics
-----------------

:mod:`finance.calculators` backs the dashboard widgets. Every function takes the
same ``(fiscal_year, is_projection)`` pair the global filter bar produces, so
each widget answers the same question about the same slice of the ledger.

A few deliberate choices are worth knowing when reading the numbers:

**Money in vs money out** sums revenue and expenses separately per month rather
than netting them, so a month with heavy activity in both directions doesn't
flatten to nothing. Months with no activity still appear, as gaps are
themselves informative.

**Client type** is never entered by hand — it is inherited from each event's
billing organisation. Non-event revenue (SGA baseline, alumni gifts) has no
client and is excluded rather than silently bucketed as "Unknown".

.. warning::

   ``810-FD`` appears in two unrelated places, and conflating them is a
   mistake this module has already made once.

   Here it is read off **the client's** billing organisation: an org that
   bills through fund 810 is a student organisation rather than a university
   department. That inference is sound, and the fund number is
   :attr:`~finance.models.FinanceSettings.student_org_workday_fund` rather
   than a constant, so it can be changed when Workday renumbers.

   It says **nothing whatever about where LNL's own money came from.**
   810-FD is the agency fund the entire 226-AG account sits in, so every
   line LNL has ever spent carries it, whoever actually paid. Reading it as
   "this was funded by SGA" is wrong, and is precisely what the mapping
   described in *Fund codes are admin data* was removed for doing.

**Service mix** splits a show's revenue across its service categories in
proportion to their list prices, so a lighting-and-sound show contributes to
both instead of being filed under whichever service happens to sort first.
List price is used rather than ``ServiceInstance.cost`` because only the ratio
matters and the pricelist lookup costs a query per instance. Shows with no
recorded services are grouped as "Unspecified" rather than dropped, so the
parts always sum to total linked revenue.

**Revenue rows** are resolved once per request and shared by the client,
client-type and service widgets. The re-fetch through the polymorphic manager
in :func:`finance.calculators.revenue_rows` is deliberate: ``select_related``
across a polymorphic foreign key yields base ``BaseEvent`` instances, which
would hide ``Event2019.workday_fund`` and misclassify every client.

**Bar widths** on the client and project panels scale to the largest value so
the leader fills its track; the true share of the total is shown as the
percentage label beside it.

What is editable without a deploy
---------------------------------

Vocabularies are rows, not ``TextChoices``, and all of them are maintained from
the Django admin:

===================  ==========================================================
Table                Holds
===================  ==========================================================
``SpendCategory``    LNL's own expense categories, each with the colour it is
                     drawn in on the dashboard
``FundSource``       SGA Funding Request, SGA Budget, Legacy — and whether the
                     fund must name a funding request line
``RevenueSource``    Non-event revenue types (SGA baseline, alumni gifts...)
``PartitionCode``    The org codes, which side each one starts on, whether
                     leaving that side needs a written reason, and the worktag
                     the code is read from
``SuggestionRule``   "Spend Category is exactly *Printing* → Printing",
                     "ledger account starts 74100 → Repairs" — what fills the
                     reconciliation form in. Exact and starts-with matches are
                     treated as lookups and answer the box; *contains* is
                     treated as a guess and is only offered
``FinanceSettings``  One row: the month the fiscal year starts, the Workday
                     fund that means "student organisation", and how many years
                     the filter bar offers
``ServiceColor``     The colour of each service category on the service-mix
                     chart, keyed to the events app's own ``Category`` row so a
                     rename does not lose it
``ColumnAlias``      Extra spellings of Workday CSV columns, for when Workday
                     relabels one
===================  ==========================================================

Each row has a ``slug`` alongside its name. URL filters use the slug
(``?category=repairs``), so links and bookmarks survive a rename or a reorder;
changing a *slug* is the breaking edit, and the admin says so on the field.

Retiring is not deleting. Clearing ``is_active`` removes a row from new
dropdowns while existing records keep it; deletion is blocked by ``PROTECT``
and the admin hides the button entirely once money is filed against the row, so
a category can never take transactions with it.

Some tables carry a default in code so a fresh install works before anyone
configures anything: :data:`finance.models.DEFAULT_SERVICE_COLORS` colours the
familiar three service lines, and :data:`finance.importers.COLUMN_ALIASES`
holds the column spellings already seen. A row always wins over the default, so
the code is a starting point rather than a constraint.

Reads that sit on hot paths — the partition lock runs on every save, the fiscal
year on every row of every page — are cached in module state and dropped by a
``post_save`` signal (:mod:`finance.apps`). An admin edit that appeared to do
nothing until the next restart would be a far worse bug than the query it
saves, so any new cached table must be registered there too.

What stays in code, and why:

``TransactionStatus``
    A state machine, not a vocabulary. ``settle()``, ``clean()`` and a database
    ``CheckConstraint`` all branch on ``pending``/``settled``; a third value
    added from the admin would do nothing without code to go with it.
``ClientType`` and ``entry_type``
    Derived from the billing fund and the sign of the amount. Never stored,
    never chosen — there is nothing to configure.
:data:`finance.models.FINGERPRINT_WORKTAGS`
    Deliberately *not* editable. It defines what makes a bank line that line,
    so changing it would orphan every fingerprint on file and make the next
    import look like a ledger full of new transactions. This is the clearest
    case of something that looks like data but is not.
``LEDGER_COLUMNS``, ``SORTABLE``, the partition filter tokens
    Each entry is bound to template markup, an ORM path or a URL. A row here
    without the code beside it would render nothing.
``MEMO_SEPARATOR``, the date formats, the structural column lists
    Parser internals rather than organisational policy.

Tests
-----

``python manage.py test finance`` runs 786 tests across sixteen modules. The
module map, and what each one is responsible for, is the docstring of
:mod:`finance.tests`; the notes here are the things that are not obvious from
reading it.

**Everything that touches money asserts on exact Decimals.** A test that
accepts ``almost equal`` would pass against the very defect *Cents, and only
cents* describes, so balances are compared to ``Decimal('0.00')`` and not to
zero-ish.

**The importer is tested against real exports, not tidied ones.** The fixtures
carry the things Workday actually emits -- a UTF-8 BOM, parenthesised
negatives, thousands separators, newlines inside quoted memos, non-breaking
spaces in headers, a report title above the table, and an ``.xlsx``
``<dimension>`` element that understates the sheet. Each of those is a bug that
reached the Treasurer once.

**Guards are tested from the direction that bypasses them.** The immutability
of :class:`~finance.models.WorkdayTransaction` is asserted through
``objects.filter(...).update()`` and queryset ``delete()`` as well as through
the model, because those are the paths that do not call ``save()``. The
accounting rules are asserted against the database constraints as well as
against ``clean()``, for the same reason.

.. note::

   ``finance/tests/__init__.py`` installs one shim before any test runs, and it
   is worth knowing about because without it a whole area of this app silently
   goes unexercised.

   ``mptt.models._check_no_testing_generators`` runs on every MPTT model
   instantiation under ``manage.py test`` and builds its error label with
   ``call_file.split("/")[-2]``. A Windows path contains no ``/``, so the split
   yields a one-element list and the guard raises ``IndexError`` from the line
   that was only ever meant to name a directory -- before the test body runs.
   Setting ``MPTT_ALLOW_TESTING_GENERATORS`` does not help, because the
   IndexError happens on the line above the one that reads it.

   The shim replaces the guard with a platform-independent version that behaves
   identically otherwise. It lives in the test package rather than in
   application code because it exists solely because tests are running, and it
   can be deleted as soon as django-mptt fixes the split upstream.

Permissions
-----------

``view_subledger``
    Read-only access to every page. General members get this.
``view_fundingrequest``
    Read-only access to the funding request list and detail pages. Django
    creates this one automatically; it is granted alongside ``view_subledger``,
    since those pages are part of the same read-only tour.
``view_subledger_receipts``
    See the receipt attached to an entry. Separate from ``view_subledger``
    because a receipt is a scan of somebody's purchase, which is a narrower
    thing to hand out than a ledger row.
``edit_subledger``
    Create and edit allocation slices, run bulk actions, log encumbrances.
``settle_subledger``
    Mark reconciled transactions as Settled.
``import_workdaytransaction``
    Upload Workday journal exports.
``manage_projecttag`` / ``manage_fundingrequest``
    Maintain the project tree and funding requests.

Who holds them
~~~~~~~~~~~~~~

Declaring a permission on a model creates the row; it does not put it in
anybody's hands. The grants live in ``fixtures/groups.json``, which is what
``manage.py loaddata fixtures/*.json`` applies when a database is built:

===================  =========================================================
Group                Finance permissions
===================  =========================================================
Officer              All eight. The Treasurer is an Officer, and this is the
                     Treasurer's tool.
Active               ``view_subledger`` and ``view_fundingrequest`` only —
                     read-only, no receipts.
===================  =========================================================

Adding a permission to a model is therefore only half of adding it: until a
group holds it, the only account that can exercise it is a superuser. That is
worth stating because it fails silently and no view test can catch it — view
tests grant themselves whatever they need. ``finance/tests/test_rollups.py``
loads the fixture and asserts the Officer grant, which is the check that does
catch it.

Models
------
.. automodule:: finance.models
    :members:
    :undoc-members:

-----

Importer
--------
.. automodule:: finance.importers
    :members:
    :undoc-members:

-----

Auto-suggest
------------
.. automodule:: finance.suggestions
    :members:
    :undoc-members:

-----

Calculators
-----------
.. automodule:: finance.calculators
    :members:
    :undoc-members:

-----

Filters
-------
.. automodule:: finance.filters
    :members:
    :undoc-members:

-----

Views
-----
.. automodule:: finance.views.dashboard
    :members:
    :undoc-members:

.. automodule:: finance.views.ledger
    :members:
    :undoc-members:

.. automodule:: finance.views.ingest
    :members:
    :undoc-members:

.. automodule:: finance.views.detail
    :members:
    :undoc-members:

.. automodule:: finance.views.projects
    :members:
    :undoc-members:

-----

Forms
-----
.. automodule:: finance.forms
    :members:
    :undoc-members:

-----

Autocomplete channels
---------------------
.. automodule:: finance.lookups
    :members:
    :undoc-members:

-----

Template tags and filters
-------------------------
.. automodule:: finance.templatetags.finance_extras
    :members:
    :undoc-members:

-----

Admin
-----
.. automodule:: finance.admin
    :members:
    :undoc-members:

-----

App configuration
-----------------
.. automodule:: finance.apps
    :members:
    :undoc-members:

-----

Test suite
----------
.. automodule:: finance.tests
    :members:
