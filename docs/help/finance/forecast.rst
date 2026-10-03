==============================================
Forecasting and Planning Purchases (Treasurer)
==============================================

The `Forecast` tab carries today's balances forward, month by month, to the end of next fiscal year, and says whether
LNL's own money stays above the **minimum reserve** -- the least LNL should ever hold -- on the way. Use it before any
big purchase, and when planning next year.

The tab has four pages: `Forecast`, `Can we afford it?`, `Planned purchases` and `History`.

.. caution::
    **Permission Required:** View subledger

    Anyone who can see the finance pages can read the forecast and ask whether something is affordable. Saving a
    planned purchase, or correcting a line of history, needs permission to edit the subledger.

-----

What the Forecast Is About
--------------------------

The figure that matters is **LNL's own money**: the Legacy fund, plus anything not filed yet. Funding request money is
SGA's -- spending it only means waiting for SGA to pay it back -- so it moves the account's cash but never decides
whether LNL can afford something.

The forecast adds six things to today's balance. Each is listed on the page with what it adds up to, and you can click
one to leave it out and see the difference:

=====================  ================================================================================================
Part                   What it counts
=====================  ================================================================================================
Reserved purchases     Purchases logged in advance, on their dates.
Owed to LNL            What SGA owes on each funding request, and what each client owes on their bill, arriving after
                       the usual wait.
Booked events          Approved shows still to come that haven't been billed. A department's show brings in its quote
                       and pays for its hired gear. A student organization's show brings in nothing from FY27; its gear
                       is funding request spending, paid back by SGA later.
A typical year         Billing, gear hired in for shows, and running costs, month by month, as the last three whole
                       years went.
Planned purchases      Your list of things LNL means to buy, and any "what if" you are asking.
Year end               An SGA budget's unspent balance going back to SGA on June 30.
=====================  ================================================================================================

**Equipment is not in the typical year.** It is bought one decision at a time, so it only counts once it is reserved or
planned. The **room to spend** is what's left for it.

**The waits** -- how long SGA takes to pay back a funding request, and how long a client takes to pay a bill -- are
measured from the ledger once it has two of each, and assumed to be thirty days until then. The page says which.


Reading the Forecast Page
-------------------------

**At the top:**

- **LNL's own money now.**
- **June 30** of this year and next, each with a range.
- **Lowest point** -- the month LNL's own money is projected to be lowest.
- **Room to spend** -- how much could be spent today while keeping the reserve in every month ahead.

**The verdict:**

- **Yes** -- LNL's own money stays above the reserve every month, even if the rest of the year goes like the weakest
  of the last three.
- **Tight** -- it stays above the reserve in a typical year, but not in a weak one.
- **No** -- even a typical year takes it below the reserve. The page says when.

**The chart:** blue is LNL's own money ahead, between dotted lines for the weakest and strongest of the last three
years; grey is everything in the account, what Workday said at each month end and then the forecast; red is the
reserve.

**Further down:** a month-by-month table (months below the reserve in red), every dated item one by one, the typical
year part by part with each past year beside it, the waits it assumes, and how well the method would have predicted
past years.

.. note::
    The forecast starts the day after the newest imported line. Import the latest export first, or the days in between
    are filled in from a typical year.


Can We Afford It?
-----------------

#. Open `Can we afford it?`.
#. Say **what** it is, what it **costs**, roughly **when** the money would go out, and (if you know) the **fund** and
   **spend category**. Choose `SGA Funding Request` as the fund if a funding request will pay for it.
#. Click `Ask the forecast`.

The answer is Yes, Tight or No, with the forecast run twice side by side -- **without** the purchase and **with** it:
the lowest point, the lowest in a weak year, each June 30, and the room to spend.

The page's address holds the question, so you can copy the link and send it to someone. If LNL is going ahead, click
`Add to planned purchases`.


Planned Purchases
-----------------

The `Planned purchases` page lists what LNL means to buy. The forecast counts every purchase marked **Planned** or
**Approved** on its date. Click `Plan a purchase` to add one, or open one to edit it.

Once a purchase is reserved or bought, it is in the ledger -- as an encumbrance or a Workday line -- so mark it **Bought
or reserved** here, or it will be counted twice. Mark one **Dropped** if LNL decides against it.


History
-------

A forecast needs past years to learn from, and the books only go back to July 2025. The `History` page shows every year
imported side by side: client billing, SGA funding, spending by category, other money in, and the cash each year ended
with.

**Importing past years.** Import older Workday exports through the queue exactly like a monthly one (see
:doc:`import-and-file`). Every line dated before the books start becomes **history**: it never enters the queue or any
balance, and you never file it. Instead, the app reads each line -- billing, SGA funding, spending in a category, or
other money -- using the same rules that fill in the queue. A line no rule covers is shown as *not worked out*.

**Checking the import.** The bottom row shows the cash each year ended with, worked back from the Workday balance you
recorded. If a year's figure doesn't match what Workday reported for that June 30, or looks impossible, lines are
missing from that year's export.

**Correcting a line.** Click a year to see its lines and how each was read. Click `Correct` beside one to say what it
really was or which category it belongs in, or to **leave it out** of the forecast -- a one-off such as a big repair
that a typical year shouldn't include. `Read it from the line again` undoes a correction. Corrections only change how the
forecast reads the line; Workday's line itself is never changed.

**Workday categories no rule reads** are listed at the bottom of the page. One suggestion rule for each fixes them here
and in the queue at once; see :doc:`settings`.


The Departments' Share of Past Billing
--------------------------------------

From FY27, LNL bills departments only. Before that it billed student organizations as well, so a past year's billing
overstates what the same work brings in now -- and the old Workday lines don't say who paid.

So the forecast needs to know **what share of billing before FY27 came from departments**. Until it does, it leaves past
billing out of the typical year entirely and says so in a warning at the top of the page. A forecast without that
income errs on the side of caution, but it will look much worse than reality.

There are two ways to fix it:

- **Set it.** In the admin, open `Finance Configuration` and fill in *Departments' share of billing before FY27 (%)*. See
  :doc:`settings`.
- **Let it be measured.** File FY26's billing against its events, with each event's client on file. Once at least half
  of the billing since the books started is linked that way, the share is worked out from it.


The Minimum Reserve
-------------------

The reserve is set in `Finance Configuration` (it starts at $10,000). Raising it makes every answer more cautious; the
forecast's months below it are shown in red.


A First Budget Request
----------------------

The *Draft budget request* report on the `Reports` tab sets out next fiscal year's SGA budget request: for each spend
category, the last three whole years' spending, this year so far, the middle of the three, and that figure rounded up to
the next $50 as the amount to ask for. Spending SGA already paid for through funding requests is included, because a
budget would pay for it instead. Treat it as a first draft to edit, not a request to send as it is.


How Far to Trust It
-------------------

LNL's years vary a lot -- billing has grown several times over, and some years hire in far more gear than others. The
bottom of the forecast page shows how the same method would have done in past years and its usual miss. Read the
**range**, not just the line, and use the forecast to spot trouble months ahead, not to promise a figure to the dollar.

`Last Modified: October 2, 2026`
