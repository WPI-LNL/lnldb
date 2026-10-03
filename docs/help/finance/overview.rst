===========================
The Finance App (Treasurer)
===========================

The finance app is where the Treasurer keeps LNL's books. Workday says how much money is in each of LNL's accounts; the
finance app records *why* -- what each purchase was for, whose money paid for it, which show it belongs to -- and from
that works out what each fund holds, what each event made or lost, what LNL is owed, and where the money is heading.

This page is the map. The other finance guides each cover one job:

- :doc:`import-and-file` -- every month
- :doc:`encumbrances` -- before a purchase shows up in Workday
- :doc:`funding-requests` -- SGA funding requests, start to finish
- :doc:`events` -- what each show made or lost, and marking bills paid
- :doc:`balances` -- fund balances, Workday balances and closing the year
- :doc:`reports` -- reports for the board and for budget requests
- :doc:`forecast` -- where the money is heading, and whether LNL can afford something
- :doc:`settings` -- categories, suggestion rules and settings

.. caution::
    **Permission Required:** View subledger

    Officers, including the Treasurer, hold every finance permission. Active members can look at the finance pages but
    cannot change anything or see receipts. If you do not see `Finance` in the navigation bar, your role does not grant
    you access.

.. seealso::
    For the reasons behind how the app works, and for webmasters looking after it, see the
    :doc:`finance reference </reference/finance>`.

-----

What It Does, and What It Doesn't
---------------------------------

**Workday is the bank.** It knows to the cent how much each account holds and every line that moved it. It does not
know which of that money is LNL's own and which is SGA's, what SGA still owes, or whether a show made money.

**The finance app explains Workday.** You import Workday's lines, and for each one you say what it was for. Everything
else -- balances, what is owed, each event's margin, reports, the forecast -- is worked out from that.

Three things are worth knowing from the start:

- **It never changes Workday.** An imported line can't be edited. If a line is wrong, it is wrong in Workday; what you
  *can* change is how it is filed.
- **It never files anything for you.** It fills in every box it can, and says where each answer came from, but nothing
  is saved until you press the button.
- **It doesn't store totals.** Every balance and report is worked out fresh each time you open the page, so a late
  line imported in August fixes June's figures automatically.


LNL's Accounts and Funds
------------------------

LNL has two Workday accounts:

- **226-AG** is the main club account. Event Production spends from it, event billing is paid into it, and SGA's
  funding request money goes through it.
- **315-AG** is Projection's account. SGA funds it directly every year.

Inside each account, the money belongs to different **funds**, and they behave differently on June 30:

=========================  ========  ==================================================================================
Fund                       Account   What happens at the end of the year
=========================  ========  ==================================================================================
Legacy                     226-AG    **Carries forward.** LNL's own money: event billing and everything else LNL earns.
SGA Budget                 226-AG    **Unspent money goes back to SGA.** Paid in before the year's spending. LNL does
                                     not have an SGA budget yet, as of October 2026.
SGA Funding Request        226-AG    **Paid back after spending.** LNL spends first and SGA reimburses what was actually
                                     spent. Until it does, SGA owes LNL the difference.
SGA Mandatory Transfer     315-AG    **Carries forward.** Projection's yearly allocation of $6,000 from SGA. This is 
                                     not a budget so it does not roll back.
=========================  ========  ==================================================================================

The fund an account carries forward -- Legacy in 226-AG -- is that account's **own money**. It is the figure that
matters most when deciding what LNL can afford.

Every entry is also on one side of the **Event Production / Projection** split. Usually that matches the account, but
not always: when SGA funds a Projection purchase through a funding request, the money comes out of 226-AG but it is
still Projection spending.


Words You'll See
----------------

**Line** (or Workday line)
    One row of a Workday export: a date, an amount, a memo, and Workday's tags.
**Entry**
    Your record of what all or part of a line was for. A line that paid for three different things gets three entries.
**Filing a line**
    Writing entries for it until they add up to the line exactly. The app also calls this *allocating* or
    *reconciling*. A filed line is **settled**.
**The queue**
    Every line that hasn't been filed yet.
**Encumbrance**
    Money reserved for a purchase that Workday hasn't shown yet. It counts as spent until the real line arrives and
    you match the two up.
**Refund**
    Money back for a purchase. It undoes the spending rather than counting as income.
**Funding request** (FR)
    An SGA award for a specific purpose, numbered like ``F.26.86``, with one or more lines to spend against.
**Spend category**
    LNL's own label for what money was spent on: Consumables, Maintenance and Repair, Event - Sub-Rental, and so on. 
    These spend categories are for internal LNL use only. Note that this can, and oftentime does, differ from the 
    categories in an FR, since the language used in FRs can be changed to make it more understandable.
**Revenue source**
    What money coming in was, when it isn't billing for an event: an SGA payment, a gift, a sale.
**Project**
    An optional label for spending that belongs to one project, across categories.
**ISD**
    An Internal Service Delivery: one WPI account billing another. LNL's bills to departments, or any other internal 
    WPI entity, are paid as ISDs.
**Workday balance**
    What Workday said an account held at the end of a day. You enter these periodically so the app can check itself.
**Books start**
    The first day the finance app keeps books for -- for LNL, July 1, 2025, the start of FY26. Lines from before then
    are **history**: imported so the forecast can learn from past years, and never filed.
**Fiscal year**
    July to June, named for the year it ends in. FY26 is July 1st 2025 to June 31st 2026.


The Pages
---------

Open `Finance` in the navigation bar, then use the tabs across the top of every finance page:

=============  ========================================================================================================
Tab            Use it to
=============  ========================================================================================================
Dashboard      See the year at a glance: money in and out, spending by category, what each fund holds, where LNL's own
               money is heading, what is owed, and the events that lost money.
Ledger         Find any entry. Filter, sort, change many at once, or download as a spreadsheet.
Queue          Import Workday exports and file each new line. Also where you log a purchase in advance.
Events         See what each show made or lost, and mark a bill paid.
Balances       See what each fund holds; record Workday balances, move money between funds, and close a year.
Projects       See spending grouped by project.
Funding        Enter SGA funding requests, and see what SGA still owes on each.
Forecast       See where LNL's own money is heading, ask "can we afford it?", list planned purchases, and look at past
               years.
Reports        Print or download reports for the board, for SGA and for budget requests.
=============  ========================================================================================================

**The filter bar** at the top of every page chooses the **fiscal year** and the side: `Event Production`, `Projection`
or both. Every page follows it, except where the page says it is about today (what each fund holds now, what is owed,
and the forecast).


Your Routine
------------

**Every month** (At a minimum every month, it is recommended to do it more frequently)

#. Export the month's lines from Workday and import them, then work the queue until it is empty. See
   :doc:`import-and-file`.
#. Record Workday's current balance for each account on the `Balances` tab. If the app's figure disagrees, something
   is missing. See :doc:`balances`.

**When you order something that won't reach Workday for a while** -- log it as a purchase in advance so the money
counts as spoken for. See :doc:`encumbrances`.

**When SGA approves a funding request** -- enter it on the `Funding` tab, with its lines. See :doc:`funding-requests`.

**After a show** -- make sure any gear hired in for it is filed against the show, check the `Events` tab, and mark the
bill paid once the payment arrives. See :doc:`events`.

**After June 30** -- once June's lines are in, close the fiscal year from the `Balances` tab. See :doc:`balances`.

**Before a big purchase** -- ask the forecast. See :doc:`forecast`.

**For a board meeting or a budget request** -- see :doc:`reports`.

.. tip::
    New to the role? Read this page, then :doc:`import-and-file`. Most of the job is the monthly import, and the queue
    fills in most of each line for you.

`Last Modified: October 2, 2026`
