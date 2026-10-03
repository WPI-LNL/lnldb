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

Choose a fiscal year in the filter bar. The top of the page says when the books start and the date of the newest
imported line: nothing after that date is counted yet, so import the latest export before relying on today's figures.

For each account there is a table with one row per fund:

- **Opening** -- what the fund held at the start of the year.
- **Came in** and **Spent** -- what was filed to it during the year. Refunds reduce what was spent.
- **Transfers** -- money moved in or out by a transfer between funds.
- **Closing** (or **Now**, for the current year) -- what it holds.
- **Reserved** -- purchases logged in advance against it. Not spent yet, but spoken for.
- **What it means** -- for example, that a negative funding request balance is money SGA owes LNL.

The **Not filed yet** row is every line still in the queue. With it, the funds always add up to the account's cash; once
the queue is empty it is zero.

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

After June 30, once June's lines are imported and filed, close the year. Click `Close FY26` (or whichever year) on the
`Balances` tab. The page has four steps:

#. **Still open** -- lines still in the queue, open encumbrances, and whether each account has a June 30 Workday
   balance that agrees with the ledger. None of these stops you closing, because Workday keeps posting into a year for
   weeks after it ends.
#. **What Workday says on June 30** -- enter each account's June 30 balance from Workday.
#. **Balances that can't just carry forward:**

   - An **overspent SGA budget** has to be covered from LNL's own money. This is ticked by default.
   - **Funding request money SGA still owes** carries into next year. If SGA has refused to pay some of it, write that
     much off to LNL's own money.
   - An **unspent SGA budget** needs nothing here: SGA takes it back with a Workday line of its own, and filing that line
     to the budget fund brings it to zero.

#. **Close** -- add any notes and click `Close FY26`.

Closing records every account's cash and fund balances as they stood, and makes the transfers you chose, dated June 30.

**Closing locks nothing.** If a late line changes the year afterwards, the `Balances` tab lists exactly what changed
since the close. If the new figures are right, click `Reopen` and close the year again to record them. Reopening takes
back the year-end transfers; the Workday balances you entered stay.

`Last Modified: October 2, 2026`
