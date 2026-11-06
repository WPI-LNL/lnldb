============================================
SGA Funding Requests and Budgets (Treasurer)
============================================

SGA gives LNL money line by line in two ways, and both live on the `SGA Funding` tab:

- A **funding request** is money SGA approves for a specific purpose. LNL spends first, and SGA pays back what was
  actually spent -- never the amount approved.
- A **budget** covers a whole fiscal year. SGA deposits it at the start of the year, before the spending, and takes
  back whatever is unspent at year end.

The finance app tracks each one from what LNL asked for to the last dollar: what was requested and approved on each
line, what has been spent, and what SGA still owes or has deposited.

.. caution::
    **Permission Required:** Manage funding requests

    Entering and editing requests and budgets needs permission to manage funding requests, which Officers have. Only
    Officers can see them.

-----

How SGA Pays LNL
----------------

SGA funds clubs in three ways, and each goes into its own fund:

- **Funding requests** -- approved one at a time and reimbursed after the spending. This is how LNL is funded today.
- **A budget** -- approved once a year and paid in before the spending; whatever is unspent goes back to SGA on June 30.
  SGA only offers a budget to a club that has submitted funding requests in two consecutive fiscal years. See
  `The Budget`_ below.
- **The mandatory transfer** -- Projection's yearly allocation, paid straight into 315-AG.

**Reference numbers.** SGA numbers each request like ``F.27.16``. The letter is the body that approved it -- **A** for
the Appropriations Committee, **F** for the Financial Board, **S** for the Senate, and rarely **E** for Exec -- the
middle number is the fiscal year (27 for FY27), and the last counts up within that body's year. ``A.27.16`` and ``F.27.16`` are two different requests. Sometimes SGA's system makes a mistake and the number
comes with a ``?`` instead of a letter, like ``?.27.16``. Enter it exactly that way: it is the number SGA's memos
will quote. A budget has no number of its own: each of its lines has a four-digit **Request ID** instead, like
``4521``.


Requested and Approved
----------------------

Every line of a request or a budget has two amounts:

- **Requested** -- what LNL asked SGA for.
- **Approved** -- what SGA approved. **Leave it blank until SGA decides**: the line then shows **?** and
  `Pending SGA Approval`. If SGA denies a line, **enter 0**: it shows **$0** and `Denied`. The two never look the
  same, so "not decided yet" is never mistaken for "SGA said no". On the edit form, Approved is a plain dollar box
  you type into; the tag under it says what it means as it stands (`Pending SGA Approval` while blank, `Denied` at
  0, nothing once it holds an amount).

Neither a line pending SGA approval nor one denied can have spending charged to it. Totals add up the lines SGA has
decided and say how many are still pending, for example ``$4,200.00 · 3 lines pending SGA approval``. Once spending
is charged to a line, its approved amount can't be cleared or lowered below what has been spent.


Enter a New Request
-------------------

As soon as LNL submits a request, or once SGA approves it:

#. Open the `SGA Funding` tab, click `New` at the top of the page and choose `Funding request`.
#. Fill in the **Name**, the **SGA reference #** exactly as SGA wrote it, the **fiscal year**, and the dates. Tick
   **Projection request** if it was heard as a Projection request.
#. Under **Lines**, add one line for each thing in the request, with what was **Requested** and, once SGA decides, what
   was **Approved**. Choose a **Spend category** where you can: purchases charged to the line will then get that
   category filled in automatically. Click `Add another line` for more.
#. Click `Save`.

.. tip::
    If an import brings in a line whose memo quotes a request number the app doesn't know yet, the queue row is tagged
    `Unknown request` with an `Add` link. It opens this form already filled in with the number, the name and the year.


Spending Against a Request
--------------------------

When settling a purchase paid for by a funding request, set the **Fund** to `SGA Funding Request` and choose the
**Funding request line**. The list is grouped by request: each request is a heading with its year and number, and its
lines are indented under it with how much is left on each, the same way the project list nests a project's parts::

    FY26 · F.26.6 A Term Films
        └ Fixtures — $340.00 left
        └ Film Rights — $5,000.00 left

The **Funding request** box beside it narrows the list to one request's lines, and picking a line fills it in. Choosing
`Any` lists every line again. The two boxes work the same way everywhere a line is picked: the queue, the bulk
bar, a split, an entry's own page and a purchase logged in advance.

You often won't have to: if the Workday memo is written as ``what it was, which line, (request number)`` -- for example
``Velcro restock, consumables, (A.27.16)`` -- the queue fills in the fund, the line and the category for you.

Normally only this year's requests are listed. To charge spending to another year's request (a late invoice, say), tick
`Charge a different fiscal year` under `More`.

To encumber money on a request before the purchase reaches Workday, log it as a purchase in advance; see
:doc:`encumbrances`.

Spending on the budget works the same way with the fund `SGA Budget`; see `Spending Against the Budget`_.


When SGA Pays LNL Back
----------------------

SGA's reimbursement arrives as a journal entry with nobody's name on it and the request number in the memo, such as
``F.26.86 Film Posters and Concessions``. The queue recognises it and fills in the source (`SGA Funding Request
Reimbursement`), the fund (`SGA Funding Request`) and the request it repays (`Reimburses request`). Check them and settle
the line.

SGA often pays in the next fiscal year, and often after a request is closed. Both are fine.

**Before SGA pays.** SGA reimburses a request only after you submit its *Funding Request Report Form*, with a receipt
for every purchase. Click `Report form` on the request's page: it lists every purchase with its receipt, warns about
anything missing, and downloads as the PDF to submit. See :doc:`reports`.

**If SGA takes money back** -- for instance, after paying the same request twice -- it arrives as money going out, and
the queue recognises that too. It fills in the fund `SGA Funding Request` and, under `More`, the request in `SGA took
back money for`. It needs no spend category, because LNL didn't spend anything.


What SGA Still Owes
-------------------

The top of the `SGA Funding` tab lists every request SGA still owes money on, from every year: what was spent in Workday,
what SGA has paid back, what it still owes, and how long the oldest unpaid spending has been waiting. Purchases that are
only encumbered don't count until they are spent.

The total should match how far below zero the `SGA Funding Request` fund is on the `Balances` tab. If the two disagree,
the page says by how much; the usual cause is a starting balance entered in one place and not the other.

Each request's own page shows its lines with what was requested, approved, spent and left, every purchase charged to it,
and every payment SGA made for it. A budget never appears here: SGA deposits it rather than paying it back.

A line with spending or an encumbrance charged to it can't be deleted. Charge them to another line first.

**Requests from before the books start.** If spending on a request began before the books start, enter what SGA still owed on
it then under **Owed by SGA when the books started**, or its reimbursement will make SGA look overpaid.


The Budget
----------

LNL has at most **one budget a fiscal year**. Its lines are usually many -- fifty or a hundred is normal -- so they are
nested under **categories** you make for the budget, one level deep, the way a project's parts sit under it. Each line
is Event Production or Projection on its own.

**Entering it.** Click `New` at the top of the `SGA Funding` tab and choose `Budget`.

#. The **Name** starts as ``FY27 SGA Budget`` and follows the **Fiscal Year** box as you change it. Whatever you call
   it, the name has to give the budget's own year: saving refuses ``FY26 SGA Budget`` on an FY27 budget. A year that
   already has a budget refuses a second one and links to the first.
#. Click `Add category` for each group of similar lines and type its name. Then click `+ Line` on a category to add a
   line under it. Lines that belong to no category go under **No category**, at the bottom.
#. For each line fill in:

   - **Request ID** -- the line's four digits from SGA. Workday memos quote it, in the usual format:
     ``Velcro restock, consumables, (4521)``. Two lines of one budget can't share a Request ID. A line can be saved
     without one, but the budget's page lists those lines, because a memo can't name them.
   - **Name**, **Description**, **Requested** and **Approved** -- as above.
   - **Projection** -- tick it for a Projection line. The box locks once anything is charged to the line.
   - **Spend category** -- as for a request.

#. Click `Save`.

**Changing categories.** Rename a category by typing over its name; the new name applies to every line under it.
**Move to** on a line moves it under another category. The X on a category removes it and moves its lines to
**No category**; nothing is deleted until you save, and `Cancel` leaves everything as it was. A category can stay
empty until you add lines to it.

**The budget's page** shows what was requested, approved, spent and is left, for the whole budget and split between
Event Production and Projection. Under it:

- **SGA deposit** -- what SGA has deposited, what has been spent in Workday, what has gone back to SGA, and what is left
  in the account, in the words the `Balances` tab uses for the SGA Budget fund (`Left to spend this year`, `Goes back to
  SGA` once the year is over, or overspent).
- **Lines** -- every line indented under its category, with the category's subtotals. Click a line to see what is
  charged to it.

On the `SGA Funding` tab, the **Budget** box sits under **Funding Requests**. With the finance bar's **Partition** set
to Event Production or Projection, its figures count only that side's lines; what SGA deposited is always the whole
budget's. The dashboard's **SGA funding burndown** lists the budget after the requests, narrowed to that side's lines
the same way.


Spending Against the Budget
---------------------------

Spending paid for by the budget has to name one of its lines. Set the **Fund** to `SGA Budget`: the boxes beside it
become **Budget** and **Budget line**, and offer only the budget's lines -- the year's open budget, with each category a
heading and its lines under it, Request ID first::

    FY27 · Budget · Consumables
        └ 4521 Gaff tape — $120.00 left
        └ 4523 Gel — $300.00 left

A line pending SGA approval or denied isn't listed. The entry takes the line's side: spending on a Projection line is
Projection spending, whichever account paid. `SGA Budget` can only be charged to a budget line, `SGA Funding Request`
only to a funding request line, and no other fund to either.

**From the memo.** If the Workday memo ends with the line's Request ID -- ``Velcro restock, consumables, (4521)``, or
``Gaff tape (4521)`` -- the queue fills in the fund, the budget, the line and the line's spend category. If the middle
of the memo doesn't fit the line (``Lamps, lighting, (4521)`` on Gaff tape), the line is still filled in but the caption
says to check it. The row is tagged when the Request ID is a line SGA hasn't approved, or isn't in the budget at all,
and when the budget has been closed: reopen it to charge the line, or route the row by hand.

**From Workday's Tracking.** A line tracked as ``SGA Budget`` with no Request ID gets the fund and the budget, and the
line only when the memo's words point to exactly one line. If lnldb has no budget for that year, the row is tagged
`No FY27 budget` with an `Add budget` link.

**SGA's deposit** is a journal entry with nobody's name on it, tracked as ``SGA Budget``. The queue fills in the source
(`SGA Budget`), the fund and the budget in `Deposit for budget`. It stays on the side of the account it landed in.

**Money going back to SGA** at year end is a journal entry out of the account, tracked the same way. The queue fills in
the budget under `More`, in `Returned to SGA from budget`; it needs no spend category. Unspent money often goes back
just after June 30, so it is matched to last year's budget while that budget still has money left. In reports it
comes off the `SGA Budget` income line, as it undoes the deposit.

Both show on the budget's page under **SGA deposit**, and on the ledger, where the **SGA Line** column says `deposit
for` or `returned:` before the budget's name.

**Proof of spending.** SGA wants a payment request for every line item of the budget, and cuts a line with none from
next year's budget. Click `Budget Report Form` on the budget's page; see :doc:`reports`.


Closing a Request
-----------------

Once a request or a budget is finished, edit it and tick **Closed**. It disappears from the dashboard's burndown, but
its history stays, and SGA's payments are still matched to it. Nothing more can be charged to its lines.

**A side can't change once money depends on it.** Each entry takes its side from its request or budget line when it is
saved, so **Projection request** locks once a request has money charged to it or a payment from SGA, and a budget
line's **Projection** box locks once anything is charged to the line, encumbrances included. To correct one, move the
entries to another line first.

`Last Modified: November 6, 2026`
