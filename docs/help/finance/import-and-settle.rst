===========================================
Import and Settle Workday Lines (Treasurer)
===========================================

Once a month, bring Workday's latest lines into the finance app and say what each one was for. The app fills in most of
each line for you; your job is mostly to read and confirm.

.. caution::
    **Permission Required:** Import Workday transactions, Edit subledger, Settle Workday lines

    Importing needs permission to import Workday transactions, and settling lines needs permission to edit the subledger and settle Workday lines.
    Officers have both. If you do not see `Import an export` on the `Queue` tab, your role does not allow importing.

-----

Export from Workday
-------------------

In Workday, run **Find Journal Lines** for the account -- 226-AG, and 315-AG for Projection -- and export the result to
Excel or CSV. Either format works, and so does a file that still has Workday's report title above the table.

The date range doesn't need to be exact. Lines that were already imported are recognised and skipped, so an export that
overlaps last month's is safe. If in doubt, export the whole fiscal year so far.


Import the File
---------------

#. Open the `Queue` tab and click `Import an export`.
#. Drop the file onto the box, or click `browse for a file`, then click `Import`. Tick `Preview only` if you just want to
   look at what is in the file.
#. **Check the confirmation page before going on.** It says how many new lines the file will add to the queue, their
   dates, and their net total, and lists the first few. It also counts lines already imported, lines it couldn't read,
   and lines that look a lot like one already in the ledger. If the count or the dates look wrong -- last month's file,
   or the wrong account -- click `Cancel` and nothing is saved.
#. Click `Import`. The new lines appear in the queue.

.. note::
    Every line you import goes into the queue and is settled by you, however old it is. An export that goes back
    further than anything already imported moves the books back to the start of its first fiscal year, and the
    confirmation page says so before anything is saved. It also lists the opening balances and the "owed by SGA when
    the books started" figures that were entered for the old start: nothing changes them for you, so look at each one
    again once the older lines are settled.

If the import warns that **no spend category rule covers** a Workday category, every line with that category will need
its category picked by hand until a rule is added. One rule fixes it for good; see :doc:`settings`.


Work the Queue
--------------

The queue lists every line that hasn't been settled yet, newest first, twenty-five to a page. Each row shows the date, who
was paid or who paid LNL, Workday's memo and the amount, followed by boxes to fill in.

Filled-in boxes and suggestions
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**A box that is already filled in** has a small caption underneath saying where the answer came from: Workday's spend
category, the ledger account, a funding request number in the memo, an event named in the memo, and so on. These come
from what Workday or the memo actually says, so they are usually right -- but read them before you settle the line.

**A coloured chip** under an empty box is a suggestion: the app's best guess. Click it to fill the box in, or ignore
it. Guesses are never filled in for you.

`More` opens the fields most lines don't need (the project, the event a cost was for, the Event Production / Projection
tick box, and a few rarer ones). It opens by itself on a row that needs something in there.

Money going out
^^^^^^^^^^^^^^^

- **Fund** -- whose money paid for it. Usually `Legacy` (on 315-AG, `SGA Mandatory Transfer`). If the memo quotes a
  funding request number, it will say `SGA Funding Request`.
- **Spend Category** -- what it was for. When the memo quotes a funding request, the category comes from that request
  (the line it names, or the one category all its lines were awarded for), never from Workday's category. Picking a
  funding request line replaces any category the app filled in.
- **Funding request** and **Funding request line** -- only shown when the fund is `SGA Funding Request`. If the memo
  quotes a request number that is in the app, the request is always filled in, even when the memo doesn't say which
  line. The line list then shows only that request's lines. The line is filled in too when the memo names it, or when
  the memo's words match one line's name (for example "10 foot" against `10ft Truss`). That caption ends in "check
  it". Choosing `Any request` lists every line again. See :doc:`funding-requests`.
- **Incurred for event** (under `More`) -- for gear hired in for one show, or any other cost that belongs to a single
  event. See :doc:`events`.
- **Project** (under `More`) -- if the spending belongs to a project.

Money coming in
^^^^^^^^^^^^^^^

Money coming in is one of three things:

- **Payment for an event** -- choose the event under `Link to Event`. Department billing arrives as an Internal Service
  Delivery, and the event is usually filled in for you: from the bill its ISD number is recorded on, or else from the
  show the memo names. When the payment covers the event's bill, a ticked **Mark bill paid on** box marks the bill paid
  as you settle; untick it to leave the bill unpaid. See :doc:`billing`.
- **Other income** -- choose what it was under `or Non-Event Revenue`: an SGA reimbursement, a donation, gear sold, a cash deposit. The fund
  it goes into (`Into fund`) follows from the choice. An SGA reimbursement also names the request it repays
  (`Reimburses request`).
- **A refund** -- choose the purchase it refunds under `Refund of`. A refund needs nothing else: it takes everything from
  the purchase it reverses.

Settle the line
^^^^^^^^^^^^^^^

Click the blue `Settle` button on the row (it shows the amount being settled). The row leaves the queue, and an `Undo`
button stays in its place for a few seconds in case you clicked too soon.

Tags on a row
^^^^^^^^^^^^^

Some rows carry a tag pointing out something to check first:

===========================  ===========================================================================================
Tag                          What to do
===========================  ===========================================================================================
Maybe encumbered             You logged a purchase in advance that might be this line. Use `Already encumbered?` on the
                             row instead of settling it the ordinary way; see :doc:`encumbrances`.
Which event?                 The line's category is gear hired in for a show, but it doesn't say which show. Choose the
                             event under `More`.
Unknown request              The memo quotes an SGA funding request number that isn't in the app yet. Click
                             `Add F.26.195` (or whichever number) to enter it, pre-filled, then come back.
A.27.16 or F.27.16?          The memo's request number isn't in the app, but the same number is under another letter.
                             One of the two is probably a typo; check which, and pick the right line.
Multi-bill: split across...  One payment for a bill that covered several shows, found by the ISD number recorded on
                             it, or by its amount. Click it to lay out each show's share on the split page, check them,
                             and save. A ticked box there marks the bill paid as well.
===========================  ===========================================================================================


Split a Line That Paid for Several Things
-----------------------------------------

One card charge can cover tape, a repair and a show's rental. Click `Split` on the row (or open the line from the ledger)
to reach `Split This Purchase`. Add a row for each part with `Add a slice`, fill in each one, and click `Save split`.
Type each amount as it reads on the receipt, without a minus sign: every part runs the same way as the line. To drop a
row, tick its `Del` box. The parts must add up to the line exactly; the page tells you how much is left over. Saving
settles the line and it leaves the queue. To move money between the parts later, change the amounts and save the split
again.

A part paid from `SGA Funding Request` names the request line it was spent against in `FR Line`, with the request box
above it as on a queue row. Under them, `SGA took money back?` is only for a line where SGA took money back, which names
the whole request instead of a line.

If your role can write entries but not settle, the parts are saved as **Pending** and the line stays in the queue until someone
who can settle opens it and clicks `Mark settled`.

The same page splits one rental invoice between two shows: one row per show, each with its own `Incurred for event`.


Settle Many Lines at Once
-------------------------

When a dozen lines all get the same answer -- a run of supply orders, all Consumables from Legacy -- tick the box on each
row, choose the fund, category and (if you like) project in the bar at the bottom, and click `Settle selected`. Each
line is checked on its own, and any the settings don't suit are listed and left in the queue. Only money going out can
be settled this way.

If the fund is `SGA Funding Request`, the bar also asks for the request and its line, as a queue row does. It lists every
open request, so check the year on the request you pick from.


Fix a Mistake
-------------

- **Just now:** click `Undo` on the row before it disappears.
- **Later:** find the entry in the `Ledger`, click through to its Workday line, and click `Undo settling`. The
  line goes back to the queue with no entries, and the Workday line itself is untouched.
- **To change one detail** (a category, a project), open the entry from the `Ledger` and edit it.
- **Many entries at once:** tick them in the `Ledger` and use the bar at the bottom.

A purchase that has a refund recorded against it can't be undone until the refund is undone, since the refund points at it.


Check Against Workday
---------------------

Once the queue is empty, open the `Balances` tab and record Workday's current balance for each account. If the app's
figure disagrees, a line is missing or was imported twice. See :doc:`balances`.

`Last Modified: October 27, 2026`
