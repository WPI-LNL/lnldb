================================
SGA Funding Requests (Treasurer)
================================

A funding request is money SGA awards for a specific purpose. LNL spends first, and SGA pays back what was actually
spent -- never the amount awarded. The finance app tracks each request from approval to the last reimbursement: what
was awarded, what has been spent on each line, and what SGA still owes.

.. caution::
    **Permission Required:** Manage funding requests

    Entering and editing requests needs permission to manage funding requests, which Officers have. Active members can
    view them.

-----

How SGA Pays LNL
----------------

SGA funds clubs in three ways, and each goes into its own fund:

- **Funding requests** -- awarded one at a time and reimbursed after the spending. This is how LNL is funded today.
- **A budget** -- approved once a year and paid in before the spending; whatever is unspent goes back to SGA on June 30.
  LNL doesn't have one yet: SGA only offers a budget to a club that has submitted funding requests in two consecutive
  fiscal years.
- **The mandatory transfer** -- Projection's yearly allocation, paid straight into 315-AG.

**Reference numbers.** SGA numbers each request like ``F.27.16``. The letter is the body that approved it -- **A** for
the Appropriations Committee, **F** for the Financial Board, **S** for the Senate -- the middle number is the fiscal
year (27 for FY27), and the last counts up within that body's year. ``A.27.16`` and ``F.27.16`` are two different
requests.


Enter a New Request
-------------------

As soon as SGA approves a request:

#. Open the `Funding` tab and click `New request`.
#. Fill in the **Name**, the **SGA reference #** exactly as SGA wrote it, the **fiscal year**, and the dates. Tick
   **Projection request** if it was heard as a Projection request.
#. Under **Line Items**, add one line for each thing SGA approved, with the **Amount awarded**. Choose an **Expected
   category** where you can: purchases charged to the line will then get that category filled in automatically. Click
   `Add another line` for more.
#. Click `Save`.

.. tip::
    If an import brings in a line whose memo quotes a request number the app doesn't know yet, the queue row is tagged
    `Unknown request` with an `Add` link. It opens this form already filled in with the number, the name and the year.


Spending Against a Request
--------------------------

When filing a purchase paid for by a funding request, set the **Fund** to `SGA Funding Request` and choose the
**Funding request line**. Each line in the list shows its year and how much is left, for example
``FY2026 · F.26.6 Fixtures — $340.00 left``.

You often won't have to: if the Workday memo is written as ``what it was, which line, (request number)`` -- for example
``Velcro restock, consumables, (A.27.16)`` -- the queue fills in the fund, the line and the category for you.

Normally only this year's requests are listed. To charge spending to another year's request (a late invoice, say), tick
`Charge a different fiscal year` under `More`.

To reserve money on a request before the purchase reaches Workday, log it as a purchase in advance; see
:doc:`encumbrances`.


When SGA Pays LNL Back
----------------------

SGA's reimbursement arrives as a journal entry with nobody's name on it and the request number in the memo, such as
``F.26.86 Film Posters and Concessions``. The queue recognises it and fills in the source (`SGA Funding Request
Reimbursement`), the fund (`SGA Funding Request`) and the request it repays (`Reimburses request`). Check them and file
the line.

SGA often pays in the next fiscal year, and often after a request is closed. Both are fine.

**If SGA takes money back** -- for instance, after paying the same request twice -- it arrives as money going out, and
the queue recognises that too. It fills in the fund `SGA Funding Request` and, under `More`, the request in `SGA took
back money for`. It needs no spend category, because LNL didn't spend anything.


What SGA Still Owes
-------------------

The top of the `Funding` tab lists every request SGA still owes money on, from every year: what was spent in Workday,
what SGA has paid back, what it still owes, and how long the oldest unpaid spending has been waiting. Purchases that are
only reserved don't count until they are spent.

The total should match how far below zero the `SGA Funding Request` fund is on the `Balances` tab. If the two disagree,
the page says by how much; the usual cause is a starting balance entered in one place and not the other.

Each request's own page shows its lines with what was awarded, spent and left, every purchase charged to it, and every
payment SGA made for it.

**Requests from before July 2025.** If spending on a request began before the books start, enter what SGA still owed on
it then under **Owed by SGA when the books started**, or its reimbursement will make SGA look overpaid.


Closing a Request
-----------------

Once a request is finished, edit it and tick **Closed**. It disappears from the dashboard's burndown, but its history
stays, and SGA's reimbursements are still matched to it.

`Last Modified: October 2, 2026`
