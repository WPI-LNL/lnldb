==============================================
Fund Balances and Closing the Year (Treasurer)
==============================================

Workday gives one balance per account. The `Balances` tab splits each account's balance between the funds inside it --
LNL's own money, SGA's budget, funding request money, Projection's transfer -- and proves the parts add back up to
Workday's figure. At the end of June it is also where the fiscal year is closed.

.. caution::
    **Permission Required:** Edit subledger, Close fiscal year

    Recording Workday balances, opening balances and transfers needs permission to edit the subledger. Closing and
    reopening a year needs permission to close fiscal years. Officers have both.

-----

Reading the Balances Tab
------------------------

Choose a fiscal year in the filter bar. The top of the page says the date of the newest imported line: nothing after
that date is counted yet, so import the latest export before relying on today's figures. *How to read this page* opens
a short key to the figures, and *On this page* jumps to each account.

**Money going out, and any balance below zero, is always in parentheses**, like ($1,500.00). So every figure carries its
sign, and you can add a row across or a column down. Every finance page follows the same rules (see *Reading the
Figures* in :doc:`overview`).

Every cell is one of three things:

- **$0** -- nothing. The figure is known, and it is zero.
- **?** -- not known yet. For example, an account's cash before you have recorded a Workday balance for it.
- **—** (a grey dash) -- the figure doesn't apply to that row. For example, SGA's budget and funding request start
  each year empty, so their *Opening* is a dash, unless something was left over from last year, such as a reimbursement
  SGA still owes. Hover over the dash to see why.

Each account starts with a few figures that answer the usual questions:

- **Cash in Workday** -- what the account holds, worked out from your Workday balances.
- **Legacy free to spend** (the account's own money) -- Legacy now, less its encumbrances.
- **Billed, not paid** -- what events you have billed and haven't been paid for yet still owe. See below.
- **SGA will owe LNL** -- what the funding request will be owed once its encumbered purchases are charged.
- **Event costs awaiting payment** -- costs kept out of Legacy until their events are paid for. See below.

A figure only shows when it applies. Underneath is a table with one row per fund:

- **Opening** -- what the fund held at the start of the year.
- **Came in** and **Spent** -- what went into it and out of it during the year. Spent is in parentheses, and refunds
  reduce it.
- **Transfers** -- money moved in or out by a transfer between funds, and event costs moving into Legacy once the event
  is paid for (see below).
- **Closing** (or **Now**, for the current year) -- what it holds. Opening + Came in + Spent + Transfers adds up to it.
  It is in red only when it needs you to act: Legacy overdrawn, a budget overspent, or a funding request reimbursed for
  more than was spent.
- **Encumbered** -- purchases logged in advance against it, in parentheses. Not spent yet, but spoken for.
- **After encumbrances** -- Closing plus Encumbered: what is left once the encumbered purchases are charged. A funding
  request never holds money to spend, since SGA pays after the spending, so its figure is below zero by what SGA will
  owe.
- **What it means** -- for example, that a negative funding request balance is money SGA owes LNL.

A fund with nothing in it and nothing moved this year is greyed out.

The **Not settled yet** row is every line still in the queue. With it, the funds always add up to the account's cash; once
the queue is empty it is zero.

The **Event costs awaiting payment** row holds every expense on Legacy (or another fund that carries forward) that is
linked to an event the client hasn't paid for yet. The events are listed under the table, each with its costs, and the
row links to them. A big sub-rental for a show doesn't make Legacy look short while you wait for the client to pay you
back:

- On the day the event's bill is marked paid, the cost moves into Legacy, shown under **Transfers**. The bill is marked
  paid on the day the last of its payment reached Workday, so the cost and the payment land in Legacy together.
- If you mark the event *No bill needed*, or close it without being paid, nobody will pay the cost back, so it moves into
  Legacy that day instead.
- An encumbrance linked to an event waits in the same row until the event is paid for.
- Spending on a funding request doesn't wait. The funding request's own row already shows what SGA owes.

**Billed, not paid** is filled in for you from the bills: there is nothing to log. Every bill whose event hasn't been paid
for yet counts, less any part-payment already received, including bills you haven't emailed yet. Click the figure to see
them listed under the table, longest-owed first, with the client, the date billed and the stage each bill is at. Every
event's payment goes into 226-AG, Projection showings' included, so the bills are all in 226-AG.

- Beside it, **free once paid** is what Legacy will have free when all those bills are paid: what is free now, plus what
  they still owe, less the event costs and encumbrances waiting for those same events, which move into Legacy when each
  is paid. Events with costs waiting but no bill yet aren't counted on either side.
- A bill stops counting when it is marked paid, when its event is marked *No bill needed*, or when the event is closed --
  the same day its waiting costs move into Legacy.
- For a past year, it shows what was billed and unpaid on June 30.
- The *Owed to LNL* report can show a little more: it also lists bills marked paid for less than they asked, and events
  closed with money still owed. The Balances tab counts those as never going to be paid.

The last row adds up every column for the account. Its opening and closing are the account's cash, so they need a Workday
balance; the money that came in, was spent and is encumbered is added up either way. Transfers always add up to zero,
because no money leaves the account. The account's *After encumbrances* is its cash once every encumbered purchase is
charged.

.. note::
    The Balances tab counts both sides, Event Production and Projection, whichever is chosen in the filter bar.
    Money is held in an account, whatever it was spent on.


Record a Workday Balance
------------------------

Workday's balance is the one figure the app can't work out for itself. Record it once a month, after importing:

#. Click `Record a Workday balance`.
#. Choose the **account**, the day (**As of the end of**), and the **Workday balance** for that day, copied from
   Workday.
#. Click `Save`.

The first balance you ever record is the starting point: every other day's cash is worked out from it, forwards and
backwards. Each later one is a check, listed under **Workday balances** with what the ledger says for the same day:

- **Agrees** -- all is well.
- **A difference** -- lines are missing from the ledger (import a wider export) or the balance was copied wrong.

If an account has no Workday balance yet, the page says its cash isn't known and shows only what moved. Any balance
will do -- today's is fine.


Opening Balances
----------------

The money an account held when the books started belongs to its own fund (Legacy, in 226-AG) unless you say otherwise.
If some of it was SGA's -- say SGA still owed LNL a reimbursement for spending from before the books started -- click
`Opening balances` and enter how much each fund held. Whatever you don't assign stays the account's own money. Saving
replaces the previous split, so the page always shows the current one.


Move Money Between Funds
------------------------

Sometimes money changes funds without Workday seeing anything -- for example, covering an overspent budget from LNL's
own money. Click `Move money between funds`, choose the **account**, the **date**, the fund it comes **From** and goes
**To**, the **amount** and why, and save. No cash moves, so the account's total doesn't change. Transfers are listed
at the bottom of the page and can be deleted there.


Close the Year
--------------

After June 30, once June's lines are imported and settled, close the year. Click `Close FY26` (or whichever year) on the
`Balances` tab. The page has four steps:

#. **Still open** -- lines still in the queue, open encumbrances, and whether each account has a June 30 Workday
   balance that agrees with the ledger. None of these stops you closing, because Workday keeps posting into a year for
   weeks after it ends.
#. **What Workday says on June 30** -- enter each account's June 30 balance from Workday.
#. **Balances that can't just carry forward:**

   - An **overspent SGA budget** has to be covered from LNL's own money. This is ticked by default.
   - **Funding request money SGA still owes** carries into next year. If SGA has refused to pay some of it, write that
     much off to LNL's own money.
   - An **unspent SGA budget** needs nothing here: SGA takes it back with a Workday line of its own, and settling that line
     to the budget fund brings it to zero.

#. **Close** -- add any notes and click `Close FY26`.

Closing records every account's cash and fund balances as they stood, and makes the transfers you chose, dated June 30.

**Closing locks nothing.** If a late line changes the year afterwards, the `Balances` tab lists exactly what changed
since the close. If the new figures are right, click `Reopen` and close the year again to record them. Reopening takes
back the year-end transfers; the Workday balances you entered stay.

`Last Modified: October 29, 2026`
