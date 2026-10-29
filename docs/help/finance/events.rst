========================================
What Each Event Made or Lost (Treasurer)
========================================

The `Events` tab answers the question that comes up after every big show: *did we come out ahead?* For each event it
sets what was billed and received against what the show cost LNL -- above all the gear hired in for it -- and flags the
ones that lost money or haven't been paid.

It only knows what you tell it. A cost counts against a show once it is linked to that show, so the job is mostly
making sure hired gear and payments are linked to the right event.

.. caution::
    **Permission Required:** View subledger

    Anyone who can see the finance pages can see the `Events` tab. Marking a bill paid needs permission to edit the
    subledger and to bill events, which Officers have.

-----

Link a Cost to Its Show
-----------------------

When you settle a line for gear hired in for one show -- a console, a video wall, a projector -- open `More` on the queue
row and choose the show under **Incurred for event**. If you leave the spend category blank, it becomes
`Event - Sub-Rental` by itself.

Often it is done for you. If the memo names the show exactly -- in brackets, like ``DT projector rental (Drag Show D25)``,
or as the whole memo -- the event is filled in. A term code such as ``D25`` tells it which year's show. If the memo only
resembles one show's name, that show is offered as a chip to click instead.

A row with the category `Event - Sub-Rental` but no event is tagged `Which event?`, because without the event the cost
can't count against the show.

**Book it early.** A rental is usually booked well before the invoice arrives, and that's when you know which show it is
for. Log it as a purchase in advance with `Incurred for event` filled in, and the event carries over to the real
charge when you match it. See :doc:`encumbrances`.

**One invoice, two shows.** Split the line, with one row per show, each with its own event. See
:doc:`import-and-settle`.


Link a Payment to Its Show
--------------------------

A department's payment arrives as an Internal Service Delivery whose memo names the show, for example
``Lens and Lights services for Pan Asian Festival D26``. The queue fills in `Link to Event` from it.

**One payment for several shows.** A payment for a bill that covered several shows (a multi-bill) is linked to the
bill: pick it under `or Multi-bill`, in place of an event. The queue fills it in when the bill's ISD number is recorded,
or when the memo names one of its shows and the payment is exactly the bill's amount. When the amount alone matches one
multi-bill, it is offered as a suggestion to click. The payment stays one entry, and each show is credited with its
share, worked out from what each would have cost on its own: the same share the bill is split by on this tab.

To give each show an entry of its own instead, click the row's `Or split across its 3 events` tag. The split page lays
out each show's share. Check the shares and save. Either way, each show's figures come out the same.


The Events Tab
--------------

Choose a fiscal year in the filter bar. The tab lists every event that **ran** in that year and has anything linked to
it, worst result first, with a summary of the whole year above. Tick `Include billed events with nothing linked yet` and
click `Apply` to also see shows that were billed but have nothing linked to them.

==========================  ===========================================================================================
Column                      What it shows
==========================  ===========================================================================================
Billed                      The event's latest bill. A corrected bill replaces the earlier one rather than adding to
                            it. For a multi-bill, this show's share.
Received                    Payments linked to the event, and where the bill stands: not billed, no bill needed
                            (you decided it is not billed), billed with nothing received, part received, received
                            in full, or received with no bill.
Direct costs                Costs linked to the event. Costs paid from a funding request or the SGA budget are
                            shown as *paid by SGA*. Purchases logged in advance are shown as *encumbered*.
Margin                      What came in, less the costs **LNL paid itself**. Costs SGA pays for, and encumbrances,
                            are left out.
Rentals billed / cost       What the client was billed for hired-in gear plus LNL's rental fee, against what the
                            hire actually cost. A rental billed on a multi-bill counts for each show by its share
                            of the bill.
==========================  ===========================================================================================

The button at the end of each row, showing how many entries are linked, opens them in the `Ledger`.

**The year is the year the show ran.** A late-June show is often billed and paid in July. Every entry linked to the
event counts towards it, whichever fiscal year the entry itself falls in.

**SGA-funded shows.** From FY27, a show marked *Is SGA-funded* on its event is charged only for its rentals and one-off
charges; any other show is charged in full, whoever the client is. So an SGA-funded show can have costs and a small bill,
or none, without losing money: whatever it cost that was charged to a funding request shows as paid by SGA and doesn't
count against the margin. LNL's own money spent on it still counts as a loss.

Flags
^^^^^

=======================================  ==============================================================================
Flag                                     What to check
=======================================  ==============================================================================
Cost LNL more than it brought in         The show lost LNL's own money. Was the bill right? Is a payment still in the
                                         queue?
Rental cost more than was billed for it  The hire cost more than the client was charged for it plus the rental fee.
Billed, not yet received                 The client still owes on the bill.
Received with no bill in lnldb           A payment is linked, but the events app has no bill for the show.
Paid in full, bill not marked paid       The payment covers the bill, but the bill is still unpaid. Click
                                         `Mark paid...`.
Marked paid, no payment received         The events app says the bill was paid, but no payment is linked. It is
                                         probably still in the queue.
=======================================  ==============================================================================


Mark a Bill Paid
----------------

When the payment linked to an event covers its bill, the row offers `Mark paid...`. It opens the bill's *Mark paid*
form with the day the payment reached Workday filled in; nothing changes until you submit it. A multi-bill is covered
once the payments for every show on it add up to it.

Most bills never need this: the queue offers to mark a bill paid as you settle the payment that covers it. See
:doc:`billing`.

The same button is on the event's own page, on the `Billing` tab.


On the Event's Page
-------------------

Anyone who can see the finance pages also sees a `Finance` section on each event's `Billing` tab, under the bills. It
shows billed, received, costs, encumbrances and margin, with the same flags in one box underneath. Below that is every
subledger entry linked to the event: its date, description, payee, type, status and amount. A payment for a multi-bill
shows the event's share of it, the same share the figures count. Click an entry to open it, or `Open in the subledger` to
see them all in the `Ledger`.

.. seealso::
    :doc:`/help/events/create-bill` covers creating and sending the bill itself.

`Last Modified: October 28, 2026`
