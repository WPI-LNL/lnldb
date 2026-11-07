===================
Reports (Treasurer)
===================

The `Reports` tab lays the finance app's figures out to print, hand to the board, or open in a spreadsheet. Every
report prints cleanly from the browser and downloads as a CSV file.

.. caution::
    **Permission Required:** View subledger

    Anyone who can see the finance pages can open the reports. The *Funding Request Report Form*'s and the *Budget
    Report Form*'s PDFs have the receipts in them, so downloading them also needs permission to view receipts, which
    Officers have.

-----

The Reports
-----------

======================================  ==================  ===========================================================
Report                                  Covers              Use it for
======================================  ==================  ===========================================================
Income and spending                     a fiscal year, or   What came in, by client type and source, and what went out,
                                        any dates           by spend category, beside the same dates a year earlier.
                                                            The starting point for a budget request. Can be narrowed
                                                            to one fund.
Fund balances                           a fiscal year       Each fund's opening balance, what moved, its closing
                                                            balance and its encumbrances, account by account, adding
                                                            up to Workday's cash. Also what bills not yet paid still
                                                            owe, and what Legacy will have free once they are paid.
Events                                  a fiscal year, or   Every event's billing, payments, costs and margin, grouped
                                        any dates           by type of client, with costs SGA paid for shown apart.
Owed to LNL                             today               What SGA owes on each funding request and each client owes
                                                            on each bill, and for how long: 0-30, 31-60, 61-90 and over
                                                            90 days. Each bill shows its stage, and the
                                                            :doc:`Billing page <billing>` shows the same days.
Student organizations and departments   a fiscal year, or   The value of LNL's work for each kind of client at full
                                        any dates           rates, whether billed or not, service by service -- the
                                                            *external wear percentage*.
Event activity                          terms or years      What LNL is doing more or less of, term over term or year
                                                            over year: who for, which services and which clients.
Funding Request Report Form             one funding         What SGA asks for before it pays a funding request back:
                                        request             every purchase charged to it, line by line, with its
                                                            receipt. Downloads as the PDF to submit. See below.
Budget Report Form                      one budget          SGA's proof of spending for the year's budget: a payment
                                                            request for each line item, with SGA money and group
                                                            funds, the date and the undergraduates who benefited.
                                                            One PDF a line, or all of them in a zip. See below.
======================================  ==================  ===========================================================

Below the reports, the tab also links to the **Ledger** download.


Choosing What a Report Covers
-----------------------------

Most reports use the **fiscal year** and the **side** (Event Production, Projection or both) chosen in the filter bar.
While a year is still running, the report covers it up to today and calls it, for example, "FY27 to date".

Reports that can cover any dates have **From** and **To** boxes on the report page. Leave them blank for the whole
fiscal year.

*Event activity* has its own choices on the page: whether to compare terms or years, and whether to count events or add
up what the work was worth. *Student organizations and departments* and *Event activity* are worked out from the events
app, not the ledger, so they include every approved show that ran, whether or not anyone was billed.


Print, Save as PDF, or Download
-------------------------------

- **Print**: use the browser's own `Print`. The page is laid out for paper, with a header saying what the report is,
  what it covers and when it was printed.
- **PDF**: print, and choose *Save as PDF* as the printer.
- **Spreadsheet**: click `CSV` on the Reports tab, or the download link on the report. The file opens in Excel with one
  row per line of the report. Amounts are plain numbers with a minus sign below zero, so columns add up. A figure that
  is not known yet, or doesn't apply, is an empty cell.

The **Ledger** downloads too: filter it however you like, and the download has every entry those filters select, with
every column.


The Funding Request Report Form
-------------------------------

SGA pays a funding request back only after you submit a *Funding Request Report Form*: a breakdown of everything spent
on the request, with a copy of the receipt, invoice or ISD for each purchase. SGA won't fund an item without proof of
purchase. This report puts the breakdown and the receipts together for you from the ledger.

#. Open it from the request's own page (`Report form`), or from the `Reports` tab and pick the request.
#. Read the warnings at the top and fix what you can. Purchases with no receipt are shown in red: click one to open
   its entry and attach the receipt. The report also warns about a receipt that may be a quote, a receipt the PDF
   can't take (an iPhone ``.HEIC`` photo, say), spending on the request still waiting in the queue, and a request
   with no SGA number or approval date.
#. Click `PDF for SGA`. The PDF starts with the breakdown: the request's number, approval date, amount approved and
   total spent, then each line of the request with every purchase charged to it. Then come the receipts, in the
   order the breakdown numbers them, each page labelled with its receipt number.
#. Submit it on myWPI: open the *Student Government Association* page, the `Surveys` tab, then *Funding Request
   Report Form*, and attach the PDF.

**What's counted.** Every purchase charged to one of the request's lines that has reached Workday, with refunds taken
off. Money that is only encumbered isn't on the form, because SGA pays back only what has been spent.

**Where a receipt comes from.** The receipt attached to the purchase's entry. If a purchase was split across two lines
of the request, one receipt on either entry covers both. If the purchase was logged in advance as an encumbrance with
a receipt or quote attached, that file is used, and the report reminds you to check it is a receipt: a quote isn't
proof of purchase.

**Receipt files.** The PDF takes PDFs and JPEG, PNG, GIF, BMP, TIFF and WebP images, and turns phone photos the right
way up. Anything else gets a page in its place saying it is submitted as a separate file, so attach that file to
SGA's form yourself, or upload it again as a PDF or JPEG.


The Budget Report Form
----------------------

SGA wants proof of spending for **every line item** of the budget: a *payment request* for each one. **A line with no
payment request is cut from next year's budget.** For each line the form gives what the line was used for, "Expense",
how much SGA money and how much of LNL's own money (*group funds*) was spent, receipts matching those amounts, the date
the money was spent -- the last day, if it was spent over several -- and how many undergraduates benefited. SGA's
form also asks how each was paid (purchase order, invoice, P-Card and so on); the app leaves that to you.

It isn't known yet whether SGA wants one payment request per line or one per purchase, so the form gives both: each
line's totals, and every purchase under it with its own amounts, date and receipt.

#. Open it from the budget's own page (`Budget Report Form`), or from the `Reports` tab and pick the budget.
#. Read the warnings at the top. **Lines with nothing spent on them come first, in red**: SGA will cut them next year.
#. For each line, type how many **Undergraduates** benefited, then click `Save answers`.

#. Click `PDF for SGA` on a line to download that line's payment request: SGA's questions answered, its purchases,
   then its receipts, each page labelled with its number. `Every line's PDF (zip)` at the top downloads them all.
#. Submit each line's request to SGA the way SGA asks.

**Group funds** are the rest of the same Workday line charged to money that carries forward, such as Legacy: if a
$260 purchase was $200 from the budget line and $60 from Legacy, the line shows $200 of SGA money and $60 of group
funds, and the receipt should show $260.

**Receipts** come from the same places as on the Funding Request Report Form, and are numbered line by line, because
each line's PDF stands on its own. A receipt that also covers money charged to something else -- another budget line,
a funding request -- is flagged, since it won't match the amounts on the form.

The form also warns about purchases with no receipt, lines with no Request ID or no count of undergraduates, spending
past what SGA approved, spending on the budget still in the queue, and money still encumbered.


Reading a Report
----------------

- **Lines still in the queue aren't counted.** The report says how many there are; settle them first for final figures.
- **Figures are always as they stand today.** A closed year's report shows today's figures, with anything that has
  changed since the close listed at the top.
- **Costs SGA pays for aren't LNL's losses.** On the *Events* report, costs paid from a funding request or the SGA
  budget are shown separately and don't reduce an event's margin.
- **$0, ? and the dash mean different things.** $0 is nothing, **?** is not known yet -- an account's cash with no
  Workday balance, say -- and a grey dash is a figure that doesn't apply to that row. Below zero is in parentheses. See
  *Reading the Figures* in :doc:`overview`.
- **Money going out is in parentheses.** On *Income and spending*, *Money in* plus *Money out* is the Net, and on the
  *Events* report a cost is in parentheses wherever it is shown. The CSV files carry the same signs, as a minus. The
  two forms for SGA keep the figures SGA asks for, as their PDFs do.
- **Fund balances adds up across.** As on the *Balances* tab, *Money out* and *Encumbrances* are in parentheses, so
  Opening + Money in + Money out + Transfers is the Closing, and Closing + Encumbrances is what is Available.

`Last Modified: November 5, 2026`
