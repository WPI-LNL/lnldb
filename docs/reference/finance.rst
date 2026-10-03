Finance
=======

The financial subledger: a "smart bridge" between Workday (which knows how much
money LNL has) and lnldb (which knows *why*).

The module never invents financial data. It ingests Workday journal exports
verbatim, then lets the Treasurer attach internal meaning to each line by
linking it to what lnldb already holds -- events, funding requests and project
tags -- and to the fund whose money it was.

Start here
----------

This page is for whoever looks after the finance app: usually the webmaster,
and any Treasurer who wants to know *why* a figure is what it is. This first
part is the map -- what the app is for, how money moves through it, the words
it uses, which page does what and where the code for each piece lives. Every
part after it takes one area in depth and explains the decisions inside it,
many of which were made after the obvious approach went wrong on real data.

For the steps rather than the reasons -- importing an export, working the
queue, closing a year -- see the Treasurer's guide, starting at
:doc:`/help/finance/overview`.

What the app is for
~~~~~~~~~~~~~~~~~~~

LNL's money sits in two WPI accounts in Workday: **226-AG**, the club account
Event Production works from, and **315-AG**, which SGA funds directly for
Projection. Workday is the system of record. It knows to the cent what each
account holds and every line that moved it, but it cannot answer what a
Treasurer gets asked:

* How much of the money is LNL's own, and how much is SGA's?
* What does SGA still owe on each funding request, and which client has not
  paid?
* Did the show with the $26,000 video wall make money or lose it?
* What will be left on June 30, and can LNL afford a new console?

lnldb already knows the events, the clients, the bills and the funding
requests. The finance app joins the two: it imports Workday's lines exactly as
exported, the Treasurer says what each one was for, and every figure is worked
out from those two things.

How money moves through it
~~~~~~~~~~~~~~~~~~~~~~~~~~

::

    Workday: Find Journal Lines for one account, exported as .xlsx or .csv
        |
        |  Queue > Import an export                  finance.importers
        v
    Bank lines (WorkdayTransaction) -- dated before the books start? --> History
        |  never edited after import                 read for the forecast,
        |                                            never filed
        v
    The queue: every line not yet filed in full     finance.views.ingest
        |  boxes arrive filled in wherever the        finance.suggestions
        |  export states the answer; a person
        |  checks them and presses Allocate
        v
    Entries (ParsedTransaction): how much, which fund, which spend category
    or event, which funding request, which project
        |
        +--> Ledger, Projects, Funding    every entry, filtered and summed
        +--> Balances                     what each fund holds   finance.balances
        +--> Events                       what each show made    finance.calculators
        +--> Dashboard, Reports                                  finance.calculators
        |                                                        finance.reports
        +--> Forecast                     plus history, booked   finance.history
                                          shows and planned      finance.forecast
                                          purchases

Three rules hold everywhere, and most of the design follows from them.

**Workday's lines are never edited.** A bank line is written by the importer
and by nothing else, and the model refuses updates and deletes. If a line is
wrong, it is wrong in Workday. What LNL decides about a line lives in its
entries, which can be changed or undone freely.

**Nothing that can be worked out is stored.** Fund balances, what SGA owes,
each event's margin, the reports and the forecast are all worked out from the
lines and entries whenever a page asks. A June purchase imported in August
corrects last year's closing balance, this year's opening and the forecast at
once. The only figures anybody types are ones nothing else knows: what Workday
said an account held on a day, an opening split, a transfer between funds, a
purchase being planned.

**Nothing is filed without a person.** The queue fills in every box the export
answers, and says which column each answer came from, but a person presses the
button. A guess is only ever offered as a chip to click; see *Lookups and
guesses*.

Words used throughout
~~~~~~~~~~~~~~~~~~~~~

========================  ============================================  ===============================
Word                      Means                                         In the code
========================  ============================================  ===============================
Bank line, Workday line   One row of a Workday export: a date, an       ``WorkdayTransaction``
                          amount, a memo and the worktags
Entry, slice, allocation  LNL's account of all or part of a bank line:  ``ParsedTransaction``
                          what the money paid for or came from. One
                          line can carry several
Filing, allocating,       Writing entries against a line until they     ``views.ingest.reconcile``
reconciling               add up to it exactly
Settled                   A line's entries are complete. Officers       ``WorkdayTransaction.settle``
                          settle in the same click as filing
The queue                 Every line from the books start on that is    ``WorkdayTransactionQuerySet``
                          not filed in full                             ``.unreconciled``
Encumbrance               Money reserved for a purchase Workday has     A ``ParsedTransaction`` with no
                          not shown yet, drawn down when it does        ``parent_transaction``
Refund                    Money back for a purchase. It un-spends       ``refund_of``
                          rather than earning
Account, org code         226-AG or 315-AG, read from Workday's         ``PartitionCode``
                          Student Organization worktag
Partition                 Event Production or Projection: which         ``is_projection``
                          activity an entry was for, whichever
                          account paid
Fund                      Whose money it is, inside an account:         ``FundSource``,
                          Legacy, SGA Budget, SGA Funding Request,      ``FundBehaviour``
                          SGA Mandatory Transfer
Own money                 The fund an account carries forward:          ``account_own_funds``
                          Legacy in 226-AG, the mandatory transfer in
                          315-AG
Funding request (FR)      An SGA award for a purpose, numbered like     ``FundingRequest``,
                          F.26.86, with lines LNL spends against. SGA   ``FRLineItem``
                          pays the spending back afterwards
Revenue source            What income that is not event billing was:    ``RevenueSource``
                          an SGA payment, a gift, a sale
Spend category            LNL's own category for spending               ``SpendCategory``
Pass-through, sub-rental  Gear hired in for one show, whose cost        ``SpendCategory``
                          belongs to that event                         ``.is_event_passthrough``
Project tag               An optional grouping across categories, in a  ``ProjectTag``
                          tree
Books start               The first day the ledger counts               ``books_start_date``
History                   Lines from before the books start, imported   ``finance.history``,
                          for the forecast and never filed              ``.before_books``
Workday balance           What Workday said an account held at the end  ``BalanceCheckpoint``
                          of a day
Transfer                  Money moved between two funds in one          ``FundTransfer``
                          account. No cash moves
Closing a year            Recording June 30's balances and squaring     ``FiscalYearClose``
                          what cannot carry forward. Locks nothing
Lookup, guess             An answer the export states, which fills the  ``Suggestion.source``
                          box; our own reading, offered as a chip
ISD                       Internal Service Delivery: WPI billing WPI.   ``WorkdayTransaction``
                          LNL's event bills arrive as ISDs              ``.document_type``
Multi-bill                One bill covering several events              ``events.models.MultiBilling``
Fiscal year               July to June, named for the year it ends:     ``fiscal_year_for``
                          FY26 is July 2025 to June 2026
Minimum reserve           The least LNL's own money should hold         ``FinanceSettings``
                                                                        ``.minimum_reserve``
Typical year              What the most recent whole years did, month   ``forecast.TypicalYear``
                          by month
========================  ============================================  ===============================

The pages
~~~~~~~~~

Every page is under ``/db/finance/``. Looking needs ``view_subledger`` (the
*Funding* tab needs ``view_fundingrequest``, which is granted with it); the last
column is what changing anything there needs. The site's *Finance* menu links
to the dashboard, the ledger, projects, funding requests, the queue and *Log a
purchase*; every page is a tab across the top of the others.

===========  ==============  ===============================================  ==========================
Tab          URL             What it is for                                   To change anything
===========  ==============  ===============================================  ==========================
Dashboard    (the root)      The year at a glance; see *Dashboard metrics*
Ledger       ``ledger/``     Every entry: filtered, sorted, edited in bulk,   ``edit_subledger``
                             downloaded as CSV
Queue        ``queue/``      Importing exports, filing each new line,         ``edit_subledger``;
                             logging a purchase before it happens             importing needs
                                                                              ``import_workdaytransaction``
Events       ``events/``     What each show made or lost, and *Mark bill      ``edit_subledger`` and
                             paid*                                            ``events.bill_event``
Balances     ``balances/``   What each fund holds; Workday balances,          ``edit_subledger``; closing
                             transfers, opening balances, closing a year      needs ``close_fiscalyear``
Projects     ``projects/``   Spending by project tag                          ``manage_projecttag``
Funding      ``funding/``    Funding requests: what SGA owes, and each        ``manage_fundingrequest``
                             request's lines and burndown
Forecast     ``forecast/``   The forecast, *Can we afford it?*, planned       ``edit_subledger``
                             purchases and history
Reports      ``reports/``    Eight reports to print or download
===========  ==============  ===============================================  ==========================

Three more pages are reached from those: one bank line
(``transaction/<pk>/``, with its split form and undo), one entry
(``entry/<pk>/``, with its receipt and audit trail), and *Log a purchase*
(``encumbrance/new/``). Outside the app, an event's *Billing* tab shows that
event's figures, and the Django admin's *Financial Subledger* section holds
everything in *What is editable without a deploy*.

Where the code is
~~~~~~~~~~~~~~~~~

===========================================  ===========================================================
Where                                        What it holds
===========================================  ===========================================================
:mod:`finance.models`                        Every table, the accounting rules, the fiscal year and
                                             money helpers, and the cached settings
:mod:`finance.importers`                     Reading a Workday export into bank lines
:mod:`finance.suggestions`                   What the queue fills in, and what it only offers
:mod:`finance.forms`                         Every form, and the rules that remove a field rather than
                                             validate it
:mod:`finance.calculators`                   The dashboard's figures, each event's figures, and what
                                             SGA and clients owe
:mod:`finance.balances`                      Each fund's balance and each account's cash, on any day
:mod:`finance.reports`                       The reports, as data one template draws and one function
                                             writes as CSV
:mod:`finance.activity`                      What LNL's work was worth, priced from the events app
:mod:`finance.history`                       Every line, filed or not, reduced to what it was
:mod:`finance.forecast`                      The forecast, the typical year and the back-test
:mod:`finance.filters`                       The filter bar: fiscal year and partition
``finance/views/``                           One module per tab, plus ``detail`` for the line and entry
                                             pages
:mod:`finance.lookups`                       The event and project autocompletes
:mod:`finance.admin`, :mod:`finance.apps`    The admin, and the signals that drop cached settings
``finance/management/commands/``             Development tools; see *Management commands*
``finance/tests/``                           The test suite; its map is :mod:`finance.tests`
``site_tmpl/finance/``                       The templates, whose comments explain the layout choices
``static/js/``, ``static/css/finance.css``   ``queue.js``, ``routing.js``, ``split.js``,
                                             ``fr_lines.js``, ``ledger.js``, ``charts.js``,
                                             ``forecast.js``
``fixtures/groups.json``                     Who holds the finance permissions
===========================================  ===========================================================

How it was built
~~~~~~~~~~~~~~~~

The app arrived in stages, and the order explains some of its shape. The first
release was the ledger, the queue, funding requests, project tags,
encumbrances and the dashboard. Five later stages each answered one of the
Treasurer's questions:

1. **Costs that belong to one event**: linking spending to a show, and the
   *Events* page.
2. **Fund balances and the year end**: the *Balances* page, Workday balances,
   transfers and closing a year.
3. **Where income comes from and what LNL is owed**: revenue sources that
   decide the fund, SGA's payments tied to their request, multi-bills, and
   *Mark bill paid*.
4. **Reports**, and the two reports priced from the events app.
5. **History and forecasting**: older exports read as history, the *Forecast*
   tab, and the draft budget request.

==========================================  ======================================================
Migration                                   What it does
==========================================  ======================================================
``0001_initial``                            The schema, collapsed from the sixteen migrations it
                                            was developed through
``0002_seed_reference_data``                What a new install starts with: spend categories,
                                            funds, revenue sources, account codes, suggestion rules
``0003_fund_source_default``                The fund an expense falls back to when nothing names one
``0004_current_spend_categories``           Brings an earlier install onto the revised spend
                                            categories, moving entries off retired ones
``0005_fund_balances``                      How each fund behaves at June 30, Workday balances,
                                            transfers, year closes, and revenue naming a fund
``0006_revenue_sources``                    Sources that decide the fund, SGA payments naming
                                            their request, and what SGA owed when the books started
``0007_sga_budget_source_name``             Renames the budget's revenue source "SGA Budget"
``0008_forecasting``                        The minimum reserve, the departments' share, planned
                                            purchases, history corrections, and the books start
                                            written down before history arrives
==========================================  ======================================================


The ledger
----------

What the app stores, and the rules that hold whatever code path writes it.

The two-table ledger
~~~~~~~~~~~~~~~~~~~~

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

Entry types
~~~~~~~~~~~

``ParsedTransaction.entry_type`` distinguishes four shapes, because "positive
means revenue" is not quite true:

===========  ===============================  =============================================
Type         Condition                        Routing
===========  ===============================  =============================================
Revenue      ``amount > 0``, no refund        Event or revenue source; the fund it goes
                                              into; the request SGA is repaying
Expense      ``amount < 0``, has a bank line  Fund, spend category, FR line (or the request
                                              SGA took money back for); an event
Refund       ``amount > 0`` + ``refund_of``   The purchase's routing (contra-expense)
Encumbrance  ``amount < 0``, no bank line     Expense routing
===========  ===============================  =============================================

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

Enforced accounting rules
~~~~~~~~~~~~~~~~~~~~~~~~~

Six rules are enforced as database ``CheckConstraint``\ s, so they hold even if
application-level validation is bypassed by a bulk action, a data migration or
a shell session:

* an allocation amount is never zero;
* an encumbrance (no parent bank line) can never be ``Settled``;
* an expense or refund may not be classified as non-event revenue;
* revenue may not carry a spend category or a funding request line. The event,
  the fund and the SGA funding request are the routing both directions share
  (``ParsedTransaction.SHARED_FIELDS``);
* a refund is always positive;
* an entry names a funding request line or the request SGA is paying for,
  never both (see *SGA's payments name the request*).

The tables added since bring four more: a fund transfer moves a positive amount
between two different funds, an account has one Workday balance per day, and a
planned purchase has a positive amount.

Three further rules depend on other rows or on a setting, so they live in
``Model.clean()``, the first with a transactional helper:

* the sum of a bank line's slices must equal its ``net_amount`` exactly before
  any slice may be marked ``Settled`` (:meth:`~finance.models.WorkdayTransaction.settle`);
* the partition rules, described below. The funding request's side and the
  written reason for leaving 315-AG are both re-applied in ``save()`` as well as
  ``clean()``, so they hold regardless of the code path;
* a line from before the books start takes no entry at all
  (:attr:`~finance.models.WorkdayTransaction.is_history`). It is history, read for the forecast
  and never filed -- see *History* -- and which lines are history depends on a
  setting, which a database constraint cannot see.

Cents, and only cents
~~~~~~~~~~~~~~~~~~~~~

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

The Event Production / Projection partition
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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

Getting Workday lines in
------------------------

How a Workday export becomes bank lines: the files it reads, how it tells a new
line from one already imported, and the confirmation in between.

File formats
~~~~~~~~~~~~

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
~~~~~~~~~~~~~

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
:attr:`~finance.models.WorkdayTransaction.reference` is what the UI shows: the Operational
Transaction if there is one, else the journal number (``25090054-JE``).

Naming the counterparty needs the same care. An Internal Service Delivery is
WPI billing WPI — LNL invoicing a department, campus shipping, Chartwells
catering — so it carries neither a Supplier nor an Employee, and neither do
journal entries. That is 94 of the 314 lines on the FY26 export, every one of
which used to read "(no payee)". :attr:`~finance.models.WorkdayTransaction.payee` now falls
back to :attr:`~finance.models.WorkdayTransaction.document_type`, taken from the Operational
Transaction's own prefix, so those lines read "Internal Service Delivery" or
"Journal Entry" and the memo carries the rest.

Two-step import
~~~~~~~~~~~~~~~

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

**History is counted apart.** A line dated before the books start is history
(see *History*) and never reaches the queue, so the confirmation counts the
lines for the queue and the lines of history separately, and an old export adds
nothing to the queue at all. If the books start has never been written down, an
import that brings history writes it down first -- where it stood before the
file arrived, in the same transaction. Otherwise an export older than
everything on file would move the books back to meet it.

Filing lines in the queue
-------------------------

The queue is where a bank line is given its meaning. These sections cover what
is filled in for the Treasurer and why, how a row is laid out, and the guard
rails, bulk actions and undo around it.

Lookups and guesses
~~~~~~~~~~~~~~~~~~~

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

For the spend category, :func:`~finance.suggestions.suggest_spend_category`
runs from the most specific evidence to the coarsest:

1. **What the funding request line was awarded for.** If the memo names a line
   and a category was recorded against it when the award was entered, the
   question has been answered once already.
2. **What the memo says.** The middle field of LNL's house format is usually a
   category by name -- ``Velcro restock, consumables, (A.27.16)`` -- and it
   outranks Workday's, because WPI's list is not LNL's: everything LNL buys
   arrives as "Supplies" or "Equipment - General" whatever it was for.
3. **Workday's own Spend Category, matched exactly.** The finest code in the
   export. "Printing", "Supplies - Office" and "Supplies - Medical" all sit
   under the ledger account ``71100:Supplies`` and are not the same thing.
4. **The ledger account, matched on its number.** Coarser, but still a code WPI
   assigned, so it covers Workday categories nobody has mapped yet.
5. **Anything matched by wording**, which is a guess and stays a chip.

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

Those are the lines the export itself answers. The fund was filled in only
where a memo quoted a request number, and that was deliberate -- see below.
Every other line now arrives with the account's own money, captioned as the
fallback it is, because a fund left blank on every row was worse than one that
says plainly it was assumed.

After an import, any Workday spend category that no rule covers is named in a
warning with a line count, because each one is a question the Treasurer would
otherwise answer by hand on every line carrying it, forever.

Fund codes are admin data
~~~~~~~~~~~~~~~~~~~~~~~~~

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
is expensive: a filled box is the one nobody re-reads. 810-FD is now mapped to
no fund, so it fills in nothing.

Only the memo and, from FY27, the *Tracking* worktag can tell the buckets
apart. When nothing on a line does, the queue fills in the account's own money
and says so in those words; see *Money coming in names a fund* below for the
full order.

When a memo quotes a request number lnldb has never heard of, the fund is still
filled in -- every SGA number is a funding request -- but the line is flagged
*Unknown request*, or *A.27.16 or F.27.16?* when the same number exists under
another body's letter. Either the award has not been entered yet or the memo is
mistaken, and both are worth fixing before the line is filed anywhere.

How a queue row is laid out
~~~~~~~~~~~~~~~~~~~~~~~~~~~

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

Guard rails
~~~~~~~~~~~

The subledger is meant to be hard to get wrong, not merely capable of being
right. Three techniques, in order of preference:

**Remove the option.** The strongest guard is a field that is not on screen.
A revenue form has no ``lnl_spend_category`` or funding request line picker;
an expense form has no ``non_event_revenue_type``; and the line picker is
hidden even on an expense unless the chosen fund draws on one. Nothing to
mis-click. The fields are *deleted* in
:meth:`finance.forms.BaseAllocationForm._apply_direction_rules` rather than
validated away, so a revenue form is structurally incapable of submitting
expense routing even with the client-side script bypassed.

Three fields survive on both sides, because each means something on both, and
each is relabelled rather than removed:

* the event -- "Linked event" on revenue, "Incurred for event" on an expense;
  see *Costs that belong to one event* below;
* the fund -- "Into fund" on revenue, "Fund" on an expense; see *Money coming
  in names a fund*;
* the SGA funding request -- "Reimburses request" on revenue, "SGA took back
  money for" on an expense; see *SGA's payments name the request*.

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

Reconciling in bulk
~~~~~~~~~~~~~~~~~~~

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

Every fund is offered, funding-request money included. Choosing a fund that
draws on a request shows a line picker beside it, as on a single row, listing
every open request's lines with the year first, because a selection can span a
July. Each row is checked against its own year, and *Other year* is the
deliberate tick for charging another year's request. A batch charged to one
award is the ordinary shape of a funding request being spent, so leaving those
funds out -- as this bar once did -- left out the batch it was most needed for.
The ledger's bulk bar still leaves them out: it has no line picker, so every
entry it touched would be left invalid.

The checkbox appears on expense rows only. A revenue row has nothing to offer
this bar, and an empty slot keeps the amounts in their column.

Undoing a reconciliation
~~~~~~~~~~~~~~~~~~~~~~~~

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
~~~~~~~~~~~~~~~~~~~~~~~~~

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

Closing an encumbrance
~~~~~~~~~~~~~~~~~~~~~~

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
^^^^^^^^^^^^

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
^^^^^^^^^^^^^^^^^

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


Costs that belong to one event
------------------------------

``linked_event`` belongs to both directions, as the fund and the SGA funding
request do. On revenue it means "this is what the event earned"; on an expense
it means "this cost was incurred for that event". The sign of the amount
already separates the two readings, so no second field is needed.

The case that forced it is the sub-rental: LNL hires a console for one show and
the invoice is that show's cost, passed straight through, sometimes with a
rental fee on top. Until this existed, a database constraint made
``linked_event`` revenue-only and there was nowhere to record it. The constraint
now forbids only ``non_event_revenue_type`` on the expense side.

Such an expense takes its spend category automatically, from whichever
:class:`finance.models.SpendCategory` carries ``is_event_passthrough`` -- seeded
as "Event - Sub-Rental", and editable on the category's admin page. The linked
event already says what the money was for, so making the Treasurer also choose
a category is a question with no useful answer; an explicit choice is never
overwritten.

Note that these expenses stay out of the revenue charts. Those read
:func:`finance.calculators.revenue_rows`, which selects on the sign, so a cost
billed to an event never reads as income from it.

Finding the event
~~~~~~~~~~~~~~~~~

A rental invoice's memo is written by whoever placed the order, not to a house
format, so the event turns up three ways: in brackets (``DT projector rental
(Drag Show D25)``), as the whole description, or folded into prose (``WPI Pan
Asian Festival lighting and sound rental``).
:func:`finance.suggestions.suggest_expense_event` treats them as the two kinds of
answer every suggestion here is one of:

* **An exact name** -- a bracketed segment, the description or the memo whole,
  matching an event outright in the term the memo names (or, with no term code,
  within six months of the charge) -- fills the box in, captioned as coming from
  the memo. It is somebody writing down which show the money was for.
* **A resemblance** is only looked for on a line that looks like an event cost
  (the pass-through category, or a memo saying "rental"), and is only ever one
  chip. Events from two months before the charge to one after are scored on the
  distinctive words their name shares with the memo, with gear the event billed
  its client for at about this price breaking a tie. The chip is offered only
  when one event leads outright: being nearer in date is not evidence of which
  show it was.

**A term code says which year.** ``D25`` is the spring-2025 D-term, and the
Theatre department bills projector hire in batches, so ``DT projector rental
(Drag Show D25)`` arrives in October 2025 -- nearer to the *next* spring's Drag
Show than to the one it paid for. Stripping the code and taking the nearest
event filled in the wrong year on the real FY26 export. So when the memo carries
a term code, :func:`finance.suggestions.term_window` turns it into that term's
months (three weeks' slack either side) and both the exact match and the guess
look only there; with no code, the exact match looks six months either side of
the charge. A show from another term is left blank rather than filled in.
Event names are matched with and without their term code, since lnldb has both
``Goat Talent C26`` and ``Pan Asian Festival``.

A line filed to the pass-through category with no event filled in is tagged
*Which event?* in the queue and its **More** fold opens, because the event is
the one thing that makes the cost count against the show.

The event can also be named on an encumbrance -- a sub-rental is booked before
its invoice exists, which is exactly when somebody knows which show it is for --
and drawing the reservation down carries it onto every bank line it pays for.

.. note::

   Two places used to lose the link. The split page rendered neither
   ``linked_event`` nor ``audit_explanation`` on expense rows, although its form
   saves both, so re-saving a split posted them blank and wiped them. The
   encumbrance form showed the picker -- it is declared on the base form -- but
   left the field out of ``Meta.fields``, so a ModelForm threw the choice away.
   ``test_detail`` now asserts that every model field the split form saves is on
   the page.

What each event made or lost
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The *Events* page, a panel on each event's Billing tab, and a dashboard list of
the events that cost more than they brought in all read
:func:`finance.calculators.event_financials`. Three of its figures are decisions
rather than arithmetic:

**The year is the year the event ran.** All of an event's entries count, in
whatever fiscal year each one landed. A late-June show is billed in July; filing
its revenue and its rental in different years would report half a show twice.
The ledger's ``?event=`` filter sets the year aside for the same reason, and
says so.

**Billed is the latest bill, not the total.** A second Billing row for one show
is nearly always the first one corrected. A multi-bill covers several shows
with one figure, so each show's share is split by what it would have cost alone
(``cost_total``), evenly if none has a price, with the last show taking the
rounding so the shares add up to the bill.

**An encumbrance is reserved, not spent.** It is shown beside the cost and left
out of the margin, which would otherwise report a loss that may never happen.

**A cost SGA pays for is not LNL's.** A cost filed to a funding request or the
SGA budget is still a cost of the event, and is shown as one, but SGA pays for
it -- after the spending or before. The margin is what came in less what LNL
paid itself, so such a cost never makes an event a loss. That matters from
FY27, when LNL bills departments only: a student organization's show is funded
through LNL's funding requests, so it has costs and no bill without having lost
anything. LNL's own money spent on an unbilled show is still a loss.

Rentals are compared separately: what the event billed its client for hired-in
gear plus LNL's rental fee, against the linked costs in the pass-through
category that LNL paid. A hire that cost more than both is flagged.

Each event also says where its bill stands and what is still owed on it. The
flags that compare lnldb's *paid* date with the ledger, and the *Mark bill
paid* button, are described under *What clients owe*.

Fund balances and the year end
------------------------------

Workday reports one balance per account: 226-AG holds this much and 315-AG
holds that. What it cannot say is how much of that figure is LNL's own money
and how much is this year's SGA budget, and at June 30 that split is the whole
question, because the two behave in opposite ways. The *Balances* page keeps
the split and proves it adds back up to Workday's figure.

How SGA pays, and what that does to a balance
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

SGA funds clubs three ways, and each fund says which way it is paid
(``FundSource.behaviour``, a hard-coded choice because the close branches on
it):

=========================  ========  ===========================================
Fund                       Held in   At year end
=========================  ========  ===========================================
Legacy                     226-AG    **Carries forward.** LNL's own money: event
                                     billing and everything else LNL earns.
SGA Budget                 226-AG    **Unspent returns to SGA.** Deposited
                                     before the year's spending. A positive
                                     balance on June 30 is owed back, and an
                                     overspend has to be covered from Legacy.
SGA Funding Request        226-AG    **Reimbursed after spending.** LNL spends
                                     first; SGA pays back what was actually
                                     spent, never the award. The balance is
                                     negative in between, and that negative is
                                     money SGA owes LNL.
SGA Mandatory Transfer     315-AG    **Carries forward.** Projection's yearly
                                     allocation, deposited automatically.
=========================  ========  ===========================================

The carry-forward fund held in an account is that account's *own money*
(:func:`~finance.models.account_own_funds`). It holds whatever the account had
when the books started, and it is what the queue fills in when nothing on a
line names another fund.

SGA reference numbers
~~~~~~~~~~~~~~~~~~~~~

SGA numbers every funding request as ``[letter].[year].[number]``. The letter
is the body that approved it, by the size of the ask: **A** for the
Appropriations Committee, **F** for the Financial Board, **S** for the Senate.
The year is the last two digits of the fiscal year, so every FY2027 request has
27 in the middle. The number counts up within each body's year, so A.27.16 and
F.27.16 are two different requests. Budgets and mandatory transfers have no
number: any SGA number in a memo means funding-request money.

A funding request's reference is held to that format, and its year has to be
the request's own. The queue only reads A, F and S out of a memo, so
"Invoice B.25.12" is not taken for a request.

**When the letters disagree.** LNL's FY27 memos quote A.27.16 while lnldb holds
F.27.16, and A.27.81 beside F.27.81. By SGA's numbering those are different
requests, so the queue never treats them as one. When a memo's number is not in
lnldb but the same year and number exist under another letter, the row is
tagged *A.27.16 or F.27.16?* and that request's line is offered as a chip, not
filled in. The fund is still filled in, because the memo has said it is
funding-request money whichever request it is. Only the Treasurer can say
which side has the typo.

Money coming in names a fund
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``fund_source`` is now on revenue as well as expenses: *Into fund* on the
queue, the split page and the entry page, required on all three. A balance
cannot be worked out without both directions. The SGA budget's deposit is what
the year's budget spending draws down, and a reimbursement lands in the
funding-request fund and brings it back towards zero. The queue fills it in:

1. a request number in SGA's journal entry means the funding-request fund (a
   reimbursement quotes the request it repays; a supplier's credit quoting one
   is a refund, and takes its fund from the purchase);
2. Workday's *Tracking* worktag, exported from FY27 on, names the fund in words
   ("SGA Budget", "Student Org Legacy Funds"), matched through each fund's
   ``workday_tracking_values``;
3. a Workday Fund code, as before;
4. the account's own money, so Legacy on 226-AG and the mandatory transfer on
   315-AG;
5. the stated default, for a line on no known account.

The spend category and funding request line stay expense-only, and the
database still refuses them on revenue. ``0005_fund_balances`` gave every
revenue entry filed before the change its account's own money. That is what the
arithmetic would have assumed anyway, and saying it outright means the ledger's
Fund filter finds those entries.

How the balances are worked out
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Nothing is stored. :mod:`finance.balances` works every figure out from the
ledger each time it is asked, so a June purchase imported in August corrects
last year's closing balance and this year's opening at once. For one account:

**The books start** on ``FinanceSettings.ledger_start_date``. Left blank, that is
the start of the fiscal year of the earliest imported line. Every line from
then on is counted. Lines from before it are history, imported for the
forecast: they are in no fund and never in the queue, but they still move the
cash, so cash worked back from a Workday balance is right on any day.

**Cash** comes from a *Workday balance* (:class:`~finance.models.BalanceCheckpoint`):
what Workday said the account held at the end of a day. The earliest one
entered is the anchor, and every other day is that figure plus or minus the
lines in between, counting backwards as well as forwards. Today's balance is
enough to work out what the account held when the books started. Each later
Workday balance is a check, and a difference means lines are missing from the
ledger or a figure was copied wrong.

**A fund's balance** is everything filed to it since the books started:
money in, less money out (net of refunds, which un-spend rather than earn),
plus or minus transfers. The account's own money also holds the opening cash.

**Unfiled** lines are a row of their own. With that row, the funds always add up
to the cash, so a half-finished queue makes the split vague rather than wrong.

**Transfers** (:class:`~finance.models.FundTransfer`) move money between two
funds inside one account. No cash moves, so Workday never sees them. Each is
one row taking an amount from one fund and giving it to another, which keeps
the account's total unchanged by construction. That is the only double-entry
idea the app needs, and it needs it only where money changes hands without a
bank line.

**Opening balances** say how the opening cash was split: for instance, that
SGA already owed $300 for spending before the books started. The page asks for
every fund held in the account except its own money, which is whatever is
left. Saving replaces the split rather than adding to it. The split counts
as the opening, not as a first-year transfer.

Encumbrances show beside each fund as *reserved*. They are not cash, and they
belong to the account their fund is held in.

Closing a year
~~~~~~~~~~~~~~

*Close FY26* on the balance page (``close_fiscalyear``) appears once a year has
ended. It has four parts:

1. **What is still open**: lines in the queue, encumbrances, and whether each
   account has a June 30 Workday balance that agrees with the ledger. None of
   these blocks the close. Workday posts into a year for weeks after it ends.
2. **Workday's June 30 balances**, recorded as Workday balances.
3. **Squaring the two balances that cannot simply carry forward.** A budget
   overspend is covered from the account's own money (ticked by default). A
   funding-request balance still awaiting SGA carries into next year, but
   any part SGA has refused can be written off to the account's own money.
   Both are year-end transfers dated June 30. An unspent budget needs no
   transfer: SGA takes it back with a Workday line of its own, and filing that
   line to the budget fund brings it to zero.
4. **The record** (:class:`~finance.models.FiscalYearClose`): every account's
   cash and fund balances as closed, with notes.

Closing locks nothing. If the year's figures later differ from the record, the
balance page lists every change. Reopening deletes the record and takes back its
year-end transfers. The Workday balances stay, because they are still what
Workday said.

.. note::

   Why no general ledger? Workday already is one: it is the double-entry
   system of record. LNL only sees its own two accounts, so the other side of
   almost every entry would be "226-AG cash", and new treasurers would have to
   learn debits and credits to record nothing new. What the subledger adds is
   what Workday cannot see: how each account's money divides between funds.
   One-row transfers, Workday balances as the trial balance, and the unfiled
   row do that without a chart of accounts.

Where income comes from, and what LNL is owed
---------------------------------------------

Money coming in is one of four things, and each is filed differently: a
purchase credited back (a refund), event billing (linked to the event), SGA
paying LNL, or some other income. The third is where a balance goes wrong most
easily, because SGA pays three kinds of money into three different funds.

The source decides the fund
~~~~~~~~~~~~~~~~~~~~~~~~~~~

A :class:`~finance.models.RevenueSource` can name the fund its money goes into
(``credits_fund``, *Goes into* in the admin). Picking the source then fills the
fund in, on the queue, the split page and the entry page, and filing the money
anywhere else is refused by name: "SGA Funding Request Reimbursement goes into
SGA Funding Request, not Legacy." A source that names no fund is the account's
own money like any other income.

===================================  ======================  ===================
Source                               Goes into               Seeded as
===================================  ======================  ===================
SGA Funding Request Reimbursement    SGA Funding Request     new in 0006
SGA Budget                           SGA Budget              was *SGA Baseline*
SGA Mandatory Transfer               SGA Mandatory Transfer  new in 0006
Asset Liquidation                    (the account's own)
Alumni / Donation                    (the account's own)
===================================  ======================  ===================

*SGA Baseline* was the annual budget under its older name. It had nothing filed
against it, and ``0006_revenue_sources`` renamed it, keeping the
``sga_baseline`` slug so links survive. The migration changes only what still
matches the original seed, so a row a Treasurer had already renamed or
reordered keeps their version. An install that ran an earlier 0006 calls it
"SGA Budget Deposit"; ``0007_sga_budget_source_name`` gives it the name SGA
uses, under the same rule.

SGA's payments name the request
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Spending against a funding request names one of its *lines*. SGA paying for
that spending names the *request* (``ParsedTransaction.funding_request``, *SGA
funding request*). There are two cases:

* **A reimbursement** coming in. Any money into a fund that draws on funding
  requests has to name the request it repays. Without that, it is money in the
  fund that no request can be credited with.
* **Money SGA takes back**, going out. The FY26 export opens with one: "SGA FR
  F.25.33 was doubled paid to 226-AG", -$15,000. It is filed on the expense
  side, because money left the account, but it is not LNL spending anything.
  So it names the request instead of a line, and needs no spend category.

An entry names a line or a request, never both, and a database constraint says
so. Otherwise a reimbursement would also count as a draw on the award.
Encumbrances cannot name a request: SGA pays for spending that has happened.

**How the queue recognises SGA.** SGA moves money with a journal entry that
names nobody, no supplier and no employee, and whose memo quotes the request:
"F.26.86 Film Posters and Concessions". That shape is the whole test
(:func:`~finance.suggestions.is_sga_transfer`). A supplier's credit quotes the
request too ("Solder wick, Consumables, (A.27.16)"), but it is a refund, so it
is never offered as a reimbursement. For an SGA journal entry the queue fills
in the source, the fund and the request together, and closed requests count,
because SGA often pays after a request is closed. A request number lnldb does
not have gets the *Unknown request* tag and an *Add F.26.195* link. The link
opens a new request pre-filled with the number, the name written after it, and
the fiscal year the number gives, then returns to the queue row. The near-miss
rule for a wrong letter applies here as it does to spending.

A deposit Workday tracks to a fund that exactly one source pays into is
offered that source; a deposit tracked "SGA Budget" is the budget deposit. A
fund the queue assumed because it is the account's own money says nothing
about where the money came from, so it is not read this way.

What SGA owes
~~~~~~~~~~~~~

SGA reimburses spending that has happened, and only what was actually spent,
so what it owes on a request (:attr:`~finance.models.FundingRequest.awaiting_sga`)
is:

  owed when the books started + spending that has reached Workday, net of refunds
  - what SGA has paid, net of anything it took back

Encumbrances are left out, because nothing has been spent yet for SGA to pay
for. *Owed by SGA when the books started* (``owed_at_books_start``) is for a
request whose spending began before the ledger did. Without it, a reimbursement
for that earlier spending would make SGA look overpaid. It can be negative:
before the books started, SGA had paid F.25.33 twice, so it held -$15,000, and
taking the money back brings it to zero.

Payments are taken to settle the oldest spending first, so what is still owed
ages from the oldest charge SGA has not yet paid for
(:meth:`~finance.models.FundingRequest.unreimbursed_since`).

The *Funding Requests* page opens with every request SGA owes on, across every
year, since SGA routinely pays an FY26 request in FY27. It checks the total
against the balance page: the fund that draws on funding requests should be
exactly that far below zero. When the two disagree, the page says by how much.
That is nearly always an opening balance entered on one side only, or a
year-end write-off, which moves the fund but not the request. Each request's
own page lists SGA's payments for it.

What clients owe
~~~~~~~~~~~~~~~~

Each event's figures (see *What each event made or lost*) include where its
bill stands: not billed, billed with nothing received, part received, received
in full, or received with no bill in lnldb. The amount still owed is shown
with how many days it has been since the bill went out. Two flags check
lnldb's own *paid* date against the ledger:

* **Paid in full, bill not marked paid.** The payment filed against the event
  covers the bill, and the events app still has it unpaid. *Mark bill paid*,
  on the event P&L and the event's Billing tab, sets the bill's paid date to
  the day the last of the payment reached Workday. It never happens
  automatically. It needs ``finance.edit_subledger`` and the events app's own
  ``bill_event``, because it is that app's record being changed. A multi-bill
  is marked paid once the payments for every show on it cover it.
* **Marked paid, no payment filed.** lnldb says the bill was paid, and nothing
  is linked to the event. The payment is probably still in the queue. Shows
  that ran before the books start are not flagged, because their payments were
  never imported.

**One payment for several shows.** When a deposit is exactly the amount of a
multi-bill, the queue offers to split it. That happens when the memo names one
of the bill's shows, or, as a guess, when exactly one multi-bill sent in the
previous year has that amount. The split page then lays out one row per show,
each with its share, which is the same share the event P&L uses. The rows are
unsaved until the Treasurer checks them and saves.

Dashboard metrics
-----------------

:mod:`finance.calculators` backs the dashboard widgets. Every function takes the
same ``(fiscal_year, is_projection)`` pair the global filter bar produces, so
each widget answers the same question about the same slice of the ledger.

The page reads from the top: the year's headline figures (revenue, expenses,
the net and what is still in the queue); money in against money out by month;
spending by category; departments against student organizations; the service
mix; revenue by source; event billing kept; revenue by client; project
spending; what each fund holds today; where LNL's own money is heading; what is
owed to LNL; the events that cost more than they brought in; and the funding
request burndown. Three of those are about now, whatever year is chosen: what
each fund holds (:mod:`finance.balances`), where the money is heading
(:func:`finance.forecast.project`, see *Forecasting*), and what is owed.

A few deliberate choices are worth knowing when reading the numbers:

**Money in vs money out** sums revenue and expenses separately per month rather
than netting them, so a month with heavy activity in both directions doesn't
flatten to nothing. Months with no activity still appear, as gaps are
themselves informative.

**Client type** is never entered by hand — it is inherited from each event's
billing organisation. Non-event revenue (SGA's payments, alumni gifts) has no
client and is excluded rather than silently bucketed as "Unknown".

**Revenue by source** is event billing against each kind of non-event income.
Money SGA took back is netted off the reimbursement source, with a note saying
how much, because it undoes income rather than being spending.

**Event billing, kept** sets every cost filed to the pass-through category
against event billing. A $26,000 video wall billed to a client goes straight
back out to the rental house, and counting it as income makes LNL look like a
much bigger business than it is. Pass-through costs with no event linked still
count, since a missing link should not make a cost vanish from the figure. A
hire SGA paid for, on a funding request, does not: no billing paid for it.

**New and returning clients** asks the events app, not the ledger, whether LNL
worked a show for each paying client in an earlier fiscal year, because the
events app goes back much further. It needs a fiscal year to be selected.

**Owed to LNL** is today's figure whatever year is selected: what SGA owes on
funding requests, and what clients owe on bills sent since the books started.

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

Reports to print and hand over
------------------------------

The *Reports* tab lays the figures out to print and to hand over. Each report is
a pure function in :mod:`finance.reports` that returns a
:class:`~finance.reports.Report`: headline figures, one or more tables, and the
notes a reader needs before trusting them. One template draws every report and
:func:`~finance.reports.as_csv` writes any of them out, so the page, the
printout and the download cannot disagree about a figure. A printed report
carries a header saying what it is, what it covers and when it was printed;
saving it as a PDF is the browser's own *Print*, for which the page is laid
out.

======================  ======================  ==========================================
Report                  Covers                  What it answers
======================  ======================  ==========================================
Income and spending     a fiscal year, or any   What came in, by client type and source,
                        dates                   and what went out, by spend category,
                                                beside the same dates a year earlier
Fund balances           a fiscal year           Each fund's opening, movements, closing
                                                and reserved money, account by account,
                                                totalled to Workday's cash
Events                  a fiscal year, or any   Every event's billing, payments, costs
                        dates                   and margin, grouped by who the client was
Owed to LNL             today                   What SGA owes on each request and each
                                                client on each bill, and for how long
Student organizations   a fiscal year, or any   The value of LNL's work for each kind of
and departments         dates                   client at full rates, service by service,
                                                and the external wear percentage
Event activity          terms or years, up to   Who the work was for, which services,
                        the year chosen         tiers and add-ons, and which clients, term
                                                over term or year over year
Forecast                today, to the end of    Where LNL's own money is heading, month
                        next fiscal year        by month; see *Forecasting* below
Draft budget request    next fiscal year        Each spend category's line for an SGA
                                                budget request, from three whole years
======================  ======================  ==========================================

**The period.** The filter bar's fiscal year, cut off at today while it is still
running, which the report calls "FY27 to date". The two reports that can cover
any dates take ``?from=`` and ``?to=`` (``YYYY-MM-DD``); dates given wrongly fall
back to the year and say so. The Event Production / Projection switch applies
to every report except *Fund balances*, for the reason the balance page gives.

**Year over year.** *Income and spending* sets each line beside the same dates a
year earlier, and the change. While a year is still running it adds the whole
of the year before, which is the column a first budget request starts from.
LNL has no SGA budget yet: SGA makes a club eligible for one only after it has
submitted funding requests in two consecutive fiscal years. When it has one,
the budget is in effect an annual funding request paid in advance -- lines by
spend category, approved once a year -- and tracking spending against it
belongs with the funding requests rather than in a report of its own. A
comparison that ends before the books start is left out, not drawn as a column
of zeros and a "change" equal to this year; one that starts before them says
so. Lines still in the queue are not counted, and the report says how many
there are.

**A closed year** is reported as it stands today, the way the balance page shows
it, with every figure that has changed since the year was closed listed above
the tables.

**The CSV** is one header row and one line per table row, with a first
*Section* column when a report has more than one table, so a whole report
filters and pivots as one sheet. Money is a plain number with a minus sign and
dates are ISO, so a column sums. The file starts with a byte-order mark, without
which Excel reads it as Windows-1252 and an en dash arrives as three
characters.

**The ledger** downloads as well. ``?format=csv`` on the ledger gives every row
its filters select -- not only the page on screen -- with every column, whether
it is showing or not. The Reports tab links to it, and to *History* (see
*Forecasting*), below the reports.

What the work was worth
~~~~~~~~~~~~~~~~~~~~~~~

*Student organizations and departments* and *Event activity* read the events
app, not the ledger. From FY27 LNL bills departments only, so a student
organization's show brings in nothing and the ledger cannot see it at all --
but it is the same work, on the same gear. These two reports price every
approved show that has run, at its own price list, whether or not anybody was
billed. Cancelled and test events, and shows still to come, are left out. The
Event Production / Projection switch does not apply; films count under the
Projection service.

**Service value** is what the events app would charge for LNL's own services and
extras, after its discounts and fees: ``Event2019.lnl_services_subtotal``, and
for a 2012 event its total less one-off charges. Hired-in gear and one-off
charges are left out, because neither is LNL's work or LNL's gear. Pricing one
show through the model costs a query for every service on it, so
:mod:`finance.activity` loads every price once and works the same figures out
in memory; ``finance.tests.test_activity`` checks it against the model for
every pricing path. A show's discounts and fees are shared out across the
services and extras they apply to, rounded so that each service, each
category and each show adds up to the cent.

**Who the work was for** is the client type the rest of the app uses: Workday
fund 810, on the event or else its client, is a student organization, and any
other fund is a department or an outside client billed at full rates. A show
with no fund on either cannot be placed. It is listed, but left out of the
percentage below.

**The external wear percentage** is the share of the value of LNL's work -- and
so of the wear on its gear -- that went to clients billed at full rates:

  departments and external / (student organizations + departments and external)

It is worked out for the whole period and for each service. When some shows
cannot be placed, the report says how far they could move it, both ways.

**Terms.** WPI's terms move by a few days each year, so each one starts on a
fixed day in the break before it: C on January 1, D on March 10, E (summer) on
May 20, A on August 15 (so new student orientation is A term), and B on
October 15. *Event activity* shows every term of the chosen fiscal year and the
year before, or the chosen year and the four before it. Columns from before the
first event on file are dropped. Its last column is the change from the same
dates a year earlier, so a term half over is compared with the same half of the
year before. Each cell counts events or adds up their service value. Under
services it counts the events that used each one; under service tiers and
add-ons, how many were booked; and for hired-in gear, how many items were
hired, or what they cost.

Forecasting
-----------

The *Forecast* tab carries today's balances forward, month by month, to the end
of next fiscal year, and says whether LNL's own money stays above the minimum
reserve on the way. Like the balances it starts from, it is worked out on every
page load and never stored, and every projected movement says where it came
from. Its four pages are the forecast itself, *Can we afford it?*, the planned
purchases list, and *History*, which is what the forecast learns from.

History
~~~~~~~

A forecast needs years to learn from, and the books start in FY26. Older Workday
exports import through the queue's ordinary upload, and every line dated before
the books start is **history**: kept for the forecast, outside every balance,
and never filed. :meth:`~finance.models.WorkdayTransactionQuerySet.in_ledger`
is what the queue, the dashboard, the year-end checklist and the reports read,
so history is never work for anybody; a history line cannot take a slice, and
its own page shows how it is read instead of the split form.

Left blank, the books start where the earliest line does, so importing FY19
would move the books back six years and put six years of lines in the queue.
Migration ``0008_forecasting`` writes the start down on an install that has
lines, and an import that brings in older lines writes it down first if
nobody has. The confirmation page counts the lines for the queue and the lines
of history separately. Cash is the one figure history still counts: worked back
from a Workday balance through every line imported, it gives the cash each past
year ended on, which the History page shows -- a year that never adds up to the
next balance Workday reported has lines missing.

A history line is **read** rather than filed (:mod:`finance.history`):

1. **SGA funding**: anything on the SGA account (74600), or shaped like SGA's
   own journal entries, paying in or taking back.
2. **Client billing**: money in on a billing account (70050, and before FY20
   70000), or on an Internal Service Delivery.
3. **Other**: money in from no supplier and no person -- a transfer between
   LNL's accounts, a gift.
4. **Spending**: money out, and money back from whoever was paid, in the
   category the queue's *lookups* give -- the memo naming a category, Workday's
   spend category, the ledger account. Wording rules are guesses and are not
   used: a line nothing looks up is "not worked out". A memo quoting an SGA
   request number makes it a funding request's spending, which SGA pays back.

A reading is an estimate and is labelled as one. The Treasurer can correct any
line -- what it was, its category, or leaving a one-off out of the forecast --
with a :class:`~finance.models.HistoryOverride`, and the forecast follows at
once. A line in the books that is still in the queue is read the same way until
it is filed. The History page also lists the Workday categories no lookup reads,
since one rule in the admin settles each of them here and in the queue.

A typical year
~~~~~~~~~~~~~~

:class:`~finance.forecast.TypicalYear` is built from the **three most recent
whole years** -- a year counts once its lines cover nine months, so FY18's
single day of conversion entries does not. LNL's billing nearly quadrupled
between FY19 and FY26, so a median over every year since would describe the
business it used to be.

Each part of the year -- billing, the gear hired in for shows, and each running
cost category -- is the **median** of those years' totals, spread over the
calendar the way those years spread it between them. The median, so one odd
year (a $15,000 chain-motor repair) does not set the pattern; the spread, so
orientation's billing lands in August. No growth is assumed: next year looks
like a typical recent one. Left out of a typical year:

* SGA's money, which pays for particular things, and spending SGA pays for;
* transfers and gifts;
* **equipment**, and any other category marked *forecast from plans only* --
  it is chosen one purchase at a time, so only what is reserved or planned
  counts;
* lines the Treasurer left out.

**Billing before FY27.** From FY27 LNL bills departments only (see
:data:`~finance.models.DEPARTMENTS_ONLY_FROM`), so a year of billing from before
then overstates what the same work brings in now, and history cannot say who
paid. Billing from those years -- and the gear hired in for them -- counts at the
**departments' share**: the figure set in Finance Configuration, or else the
share billing filed against events shows, once at least half of the billing
since the books started is filed against an event whose client is on file.
Until either exists, billing is left out of the typical year altogether, and
the forecast says so above everything else: a forecast that leaves out income
errs on the side of not overspending.

The projection
~~~~~~~~~~~~~~

:func:`~finance.forecast.project` starts from the balance page's figures for
today and adds six parts, each of which can be switched off on the page to see
what it contributes:

=====================  ===================================================================
Part                   What it adds
=====================  ===================================================================
Reserved purchases     Each encumbrance, on its date
Owed to LNL            What SGA owes on each funding request, after SGA's usual wait;
                       each unpaid bill, the client's usual wait after the show
Booked events          Approved shows still to come that nobody has billed. A
                       department's show brings in its quote and pays for its hired
                       gear on the day. From FY27 a student organization's show brings
                       in nothing and its gear is a funding request's spending, paid
                       back by SGA. A show with no client on file pays for its gear
A typical year         Billing, hired gear and running costs, month by month
Planned purchases      The Treasurer's list, and any "what if" being asked
Year end               A budget's unspent balance going back to SGA on June 30
=====================  ===================================================================

The **waits** -- SGA's repayment, measured from the last spending on a request
before each payment, and a client's, from the show to the payment -- are the
medians in the ledger once it holds two of each, and thirty days until then.
A wait already over lands on the first day of the forecast.

Nothing counts twice. A month brings in whichever is more, what is dated for it
(booked shows, bills owed) or what a typical month does; hired gear the same.
A reserved or planned purchase in a running-cost category is part of that
category's year, so the rest of that year shrinks by it.

The forecast starts the day after the last Workday line imported, not today:
until the export catches up, the days in between are the typical year's. The
figure that matters is **LNL's own money** -- the account's own fund (Legacy)
and anything not filed yet. A funding request's money is SGA's, so running it
down moves the account's cash, which the chart and the table show too, but never
the verdict. Projection's account is forecast the same way once a Workday
balance is entered for it.

**The range** is the forecast re-run with each of the three years in place of
the typical one -- the dotted lines on the chart -- taking in the typical path,
which, being a median part by part, need not fall between them.

**The verdict** is *yes* when LNL's own money stays above the reserve in every
month even if the rest of the forecast goes like the weakest of the three years;
*tight* when only a typical year keeps it there; *no* when not even that does.
**Room to spend** is the smallest gap between the reserve and LNL's own money
in any month from today on: spending today lowers every month after it.

Can we afford it, and planned purchases
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

*Can we afford it?* runs the forecast twice, without a purchase and with it, and
gives the verdict, the low point, each June 30 and the room to spend side by
side. It is asked by ``GET``, so an answer is a link to send to somebody. One
click adds it to the **planned purchases** list, a
:class:`~finance.models.PlannedPurchase` per thing LNL means to buy. The
forecast counts the planned and approved ones on their dates; marking one
*bought or reserved* stops it counting once the ledger has it as an encumbrance
or a Workday line.

How well it does
~~~~~~~~~~~~~~~~

:func:`~finance.forecast.back_test` asks the past: on today's day of the year in
each past year with two whole years before it, what a typical year made from
those years said the rest of the year would add to LNL's own money, beside what
it did, and the median miss. LNL's years swing widely -- billing has grown
several-fold, and some years hire in far more gear than others -- so the miss
is large, and the page says how large. That is why it leads with the range
rather than the line.

A first budget request
~~~~~~~~~~~~~~~~~~~~~~

The *Draft budget request* report (:func:`~finance.reports.budget_draft`) lays
out next fiscal year's SGA budget request: for each spend category on each side
of the partition, the last three whole years' spending net of refunds, this year
so far, their median, and that median rounded up to the next $50 to propose.
Spending SGA paid for through funding requests is included, because with a
budget that is what the budget pays for. The equipment categories are one line:
a line read from Workday cannot tell a capital purchase from the rest.

What is editable without a deploy
---------------------------------

Vocabularies are rows, not ``TextChoices``, and all of them are maintained from
the Django admin:

===================  ==========================================================
Table                Holds
===================  ==========================================================
``SpendCategory``    LNL's own expense categories, each with the colour it is
                     drawn in on the dashboard, and whether the forecast counts
                     it only from planned purchases
``FundSource``       SGA Funding Request, SGA Budget, Legacy, SGA Mandatory
                     Transfer — whether the fund must name a funding request
                     line, which account holds it, how it behaves at year end,
                     and the Workday Fund codes and Tracking values that mean
                     it
``RevenueSource``    Non-event revenue types: SGA's three kinds of payment,
                     gifts, sales -- and the fund each one goes into, if it
                     decides one
``PartitionCode``    The org codes, which side each one starts on, whether
                     leaving that side needs a written reason, and the worktag
                     the code is read from
``SuggestionRule``   "Spend Category is exactly *Printing* → Printing",
                     "ledger account starts 74100 → Repairs" — what fills the
                     reconciliation form in. Exact and starts-with matches are
                     treated as lookups and answer the box; *contains* is
                     treated as a guess and is only offered
``FinanceSettings``  One row: the month the fiscal year starts, the Workday
                     fund that means "student organisation", how many years
                     the filter bar offers, the day the books start, the
                     minimum reserve, and the departments' share of billing
                     before FY27
``ServiceColor``     The colour of each service category on the service-mix
                     chart, keyed to the events app's own ``Category`` row so a
                     rename does not lose it
``ColumnAlias``      Extra spellings of Workday CSV columns, for when Workday
                     relabels one
===================  ==========================================================

Two more tables hold the Treasurer's own input rather than a vocabulary, and
are edited on the *Forecast* tab: ``PlannedPurchase``, what LNL means to buy,
and ``HistoryOverride``, a correction to how a line from before the books start
is read. Both are in the admin too, for looking at.

Each vocabulary row has a ``slug`` alongside its name. URL filters use the slug
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
``FundBehaviour``
    Carries forward, returns to SGA, or reimbursed after spending. The funds are
    rows; what SGA does with money at June 30 is one of three things, and the
    balance page and the year-end close branch on which.
``HistoryKind``, and the SGA and billing ledger accounts in :mod:`finance.history`
    What a line nobody filed can be. Each kind is projected its own way, and
    the accounts are how an old line is recognised as one -- WPI's chart of
    accounts, which a forecast reading six years of exports cannot do without.
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

Permissions
-----------

``view_subledger``
    Read-only access to every page, including the forecast, the history and
    every report. General members get this.
``view_fundingrequest``
    Read-only access to the funding request list and detail pages. Django
    creates this one automatically; it is granted alongside ``view_subledger``,
    since those pages are part of the same read-only tour.
``view_subledger_receipts``
    See the receipt attached to an entry. Separate from ``view_subledger``
    because a receipt is a scan of somebody's purchase, which is a narrower
    thing to hand out than a ledger row.
``edit_subledger``
    Create and edit allocation slices, run bulk actions, log encumbrances,
    plan purchases and correct how a line of history is read.
    *Mark bill paid* also needs the events app's ``bill_event``, which
    Officers hold.
``settle_subledger``
    Mark reconciled transactions as Settled.
``import_workdaytransaction``
    Upload Workday journal exports.
``manage_projecttag`` / ``manage_fundingrequest``
    Maintain the project tree and funding requests.
``close_fiscalyear``
    Close a finished fiscal year, which records its balances and makes its
    year-end transfers, and reopen one. Recording Workday balances and
    transfers between funds needs only ``edit_subledger``.

Who holds them
~~~~~~~~~~~~~~

Declaring a permission on a model creates the row; it does not put it in
anybody's hands. The grants live in ``fixtures/groups.json``, which is what
``manage.py loaddata fixtures/*.json`` applies when a database is built:

===================  =========================================================
Group                Finance permissions
===================  =========================================================
Officer              All nine. The Treasurer is an Officer, and this is the
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

Looking after the app
---------------------

For the webmaster: setting the app up, changing it safely, and what is known to
be unfinished.

Setting up a new install
~~~~~~~~~~~~~~~~~~~~~~~~

1. ``python manage.py migrate`` creates the tables and seeds the reference data
   -- spend categories, funds, revenue sources, the two account codes and the
   suggestion rules. All of it can be edited in the admin afterwards.
2. Load ``fixtures/groups.json`` with the other fixtures. It is what gives
   Officers the finance permissions; see *Who holds them*.
3. In the admin, open *Financial Subledger* > *Finance Configuration* and check
   the month the fiscal year starts, the student organization fund (810), the
   minimum reserve, and the departments' share of billing before FY27 if
   anyone knows it.
4. **Import the current fiscal year first.** While *Books start on* is blank,
   the books start on the first day of the fiscal year of the earliest line on
   file, so on an empty install the first export decides it. Importing FY19
   first would start the books in FY19 and put six years of lines in the
   queue. Either import the current year first, or set *Books start on* before
   importing anything.
5. On the *Balances* tab, record a Workday balance for each account -- today's
   is enough -- and, if an account held SGA money when the books started, its
   opening split.
6. Import older exports for the forecast to learn from. They arrive as history;
   see *History*.

Working on a copy
~~~~~~~~~~~~~~~~~

The database is the Treasurer's real work, and an import or a migration is
awkward to take back. Try anything new against a copy. ``DATABASE_URL`` points
the app at another database, and on a development machine the default is
``runtime/lnldb.db``::

    cp runtime/lnldb.db /tmp/lnldb-copy.db
    DATABASE_URL=sqlite:////tmp/lnldb-copy.db python manage.py migrate
    DATABASE_URL=sqlite:////tmp/lnldb-copy.db python manage.py runserver

Back the real database up before migrating it.

Changing reference data
~~~~~~~~~~~~~~~~~~~~~~~

A Treasurer changes the vocabularies in the admin; see *What is editable without
a deploy*. Changing what an install starts with is a developer's job, and it is
two jobs, because ``0002_seed_reference_data`` has already run on every existing
install and Django never runs a migration twice:

1. Edit the seed, so a new database starts right.
2. Write a new data migration that brings an existing database to the same
   place. Rename what survives; create what is new; move entries and funding
   request lines off a retired row before deleting it, since the foreign keys
   are ``PROTECT``; and repoint any suggestion rule the change contradicts.

**A green test run says nothing about whether such a change reached a real
install**, because the suite builds a fresh database from the seed every time.
The seeding migrations change only what still matches what they seeded, so a
Treasurer's own edits survive: ``0006_revenue_sources`` and
``0007_sga_budget_source_name`` show the pattern. ``0004_current_spend_categories``
overwrites on purpose, because the Treasurer asked for a new list, and its
docstring explains how it keeps that safe.

Adding to the app
~~~~~~~~~~~~~~~~~

**A setting read on a hot path** is cached in module state. Register its model
in :meth:`finance.apps.FinanceConfig.ready` or an admin edit will appear to do
nothing until the next restart.

**A permission** does nothing until a group holds it. Add it to the Officer
group in ``fixtures/groups.json`` and to the assertion in
``finance/tests/test_rollups.py``; see *Who holds them*.

**A report** is a function in :mod:`finance.reports` that returns a
:class:`~finance.reports.Report`. Add it to :data:`~finance.reports.REPORTS`
(its slug, title, summary, and what period it takes) and to the dispatch in
:func:`finance.views.reports.report`. The page, the printout and the CSV come
with it.

**A field the queue fills in** goes through :mod:`finance.suggestions`, and has
to decide whether it is a lookup or a guess; see *Lookups and guesses*.

**A column in a Workday export** that Workday renames needs a *CSV Column Alias*
in the admin, not code. A column nobody has seen before is kept on the line as a
worktag, and the import says so.

Management commands
~~~~~~~~~~~~~~~~~~~

Three commands in ``finance/management/commands/``, all for development and
repair rather than daily use. Each one's docstring has the details.

``seed_test_events``
    Creates searchable test events, including one named after each billing memo
    already imported, so the event picker can be tried on a fresh checkout.
    ``--clear`` removes them.
``import_real_events``
    Imports real event names from the production site's public API, to measure
    how often a billing memo names an event that exists.
``repair_misaligned_imports``
    Finds lines an old version of the CSV reader imported with their columns
    shifted, and retires them. It changes nothing without ``--apply``.

Known limits and open questions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* **The departments' share of billing before FY27 is not known.** History says
  which event a bill was for, not who paid it, so until the share is set in
  *Finance Configuration*, or enough FY26 billing is filed against events to
  measure it, the forecast leaves past billing out and says so.
* **LNL has no SGA budget yet**, so nothing compares a budget with what was
  spent. When it has one, model it as a funding request whose money arrives
  first rather than as new tables; see *Reports to print and hand over*.
* **Workday's Tracking worktag is not always right.** It names the fund from
  FY27 on and the queue reads it as a lookup, but at least one FY27 line is
  tracked "SGA Budget" although LNL has no budget. A person still checks every
  row.
* **The events app holds no bills from before FY25**, so pricing can only be
  compared with billing from then on.
* **315-AG has no forecast** until a Workday balance is entered for it.
* **The forecast's assumptions are choices, not facts**: a typical year from
  the three most recent whole years, equipment only from plans, and waits of
  thirty days until the ledger can measure them. Each is explained under
  *Forecasting*, and each is a constant at the top of :mod:`finance.forecast`.

Building these docs
~~~~~~~~~~~~~~~~~~~

The reference sections below are generated from the code's docstrings, so a
docstring is documentation and is worth keeping accurate. To build the site
locally::

    python -m sphinx -b html docs docs/_build/html


Tests
-----

``python manage.py test finance`` runs 1,395 tests across twenty-five modules. The
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

Code reference
--------------

Generated from the docstrings. The sections above say why; these say what each
function and class does.

Models
~~~~~~
.. automodule:: finance.models
    :members:
    :undoc-members:

-----

Importer
~~~~~~~~
.. automodule:: finance.importers
    :members:
    :undoc-members:

-----

Auto-suggest
~~~~~~~~~~~~
.. automodule:: finance.suggestions
    :members:
    :undoc-members:

-----

Calculators
~~~~~~~~~~~
.. automodule:: finance.calculators
    :members:
    :undoc-members:

-----

Balances
~~~~~~~~
.. automodule:: finance.balances
    :members:
    :undoc-members:

-----

Reports
~~~~~~~
.. automodule:: finance.reports
    :members:
    :undoc-members:

-----

Activity
~~~~~~~~
.. automodule:: finance.activity
    :members:
    :undoc-members:

-----

History
~~~~~~~
.. automodule:: finance.history
    :members:
    :undoc-members:

-----

Forecast
~~~~~~~~
.. automodule:: finance.forecast
    :members:
    :undoc-members:

-----

Filters
~~~~~~~
.. automodule:: finance.filters
    :members:
    :undoc-members:

-----

Views
~~~~~
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

.. automodule:: finance.views.events
    :members:
    :undoc-members:

.. automodule:: finance.views.balances
    :members:
    :undoc-members:

.. automodule:: finance.views.reports
    :members:
    :undoc-members:

.. automodule:: finance.views.forecast
    :members:
    :undoc-members:

-----

Forms
~~~~~
.. automodule:: finance.forms
    :members:
    :undoc-members:

-----

Autocomplete channels
~~~~~~~~~~~~~~~~~~~~~
.. automodule:: finance.lookups
    :members:
    :undoc-members:

-----

Template tags and filters
~~~~~~~~~~~~~~~~~~~~~~~~~
.. automodule:: finance.templatetags.finance_extras
    :members:
    :undoc-members:

-----

Admin
~~~~~
.. automodule:: finance.admin
    :members:
    :undoc-members:

-----

App configuration
~~~~~~~~~~~~~~~~~
.. automodule:: finance.apps
    :members:
    :undoc-members:

-----

Test suite
~~~~~~~~~~
.. automodule:: finance.tests
    :members:
