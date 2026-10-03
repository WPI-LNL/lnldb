========================================
What Each Event Made or Lost (Treasurer)
========================================

The `Events` tab answers the question that comes up after every big show: *did we come out ahead?* For each event it
sets what was billed and received against what the show cost LNL -- above all the gear hired in for it -- and flags the
ones that lost money or haven't been paid.

It only knows what you tell it. A cost counts against a show once it is filed against that show, so the job is mostly
making sure hired gear and payments are linked to the right event.

.. caution::
    **Permission Required:** View subledger

    Anyone who can see the finance pages can see the `Events` tab. Marking a bill paid needs permission to edit the
    subledger and to bill events, which Officers have.

-----

Link a Cost to Its Show
-----------------------

When you file a line for gear hired in for one show -- a console, a video wall, a projector -- open `More` on the queue
row and choose the show under **Incurred for event**. If you leave the spend category blank, it becomes
`Event - Sub-Rental` by itself.

Often it is done for you. If the memo names the show exactly -- in brackets, like ``DT projector rental (Drag Show D25)``,
or as the whole memo -- the event is filled in. A term code such as ``D25`` tells it which year's show. If the memo only
resembles one show's name, that show is offered as a chip to click instead.

A row filed as `Event - Sub-Rental` without an event is tagged `Which event?`, because without the event the cost
can't count against the show.

**Book it early.** A rental is usually booked well before the invoice arrives, and that's when you know which show it is
for. Log it as a purchase in advance with `Incurred for event` filled in, and the event carries over to the real
charge when you match it. See :doc:`encumbrances`.

**One invoice, two shows.** Split the line, with one row per show, each with its own event. See
:doc:`import-and-file`.


Link a Payment to Its Show
--------------------------

A department's payment arrives as an Internal Service Delivery whose memo names the show, for example
``Lens and Lights services for Pan Asian Festival D26``. The queue fills in `Link to Event` from it.

**One payment for several shows.** When a payment matches a bill that covered several shows (a multi-bill), the row is
tagged `Multi-bill: split across 3 events`. Click the tag: the split page lays out each show's share, worked out from
what each would have cost on its own. Check the shares and save.


The Events Tab
--------------

Choose a fiscal year in the filter bar. The tab lists every event that **ran** in that year and has anything linked to
it, worst result first, with a summary of the whole year above. Tick `Include billed events with nothing linked yet` and
click `Apply` to also see shows that were billed but have nothing filed against them.

==========================  ===========================================================================================
Column                      What it shows
==========================  ===========================================================================================
Billed                      The event's latest bill. A corrected bill replaces the earlier one rather than adding to
                            it. For a multi-bill, this show's share.
Received                    Payments filed against the event, and where the bill stands: not billed, billed with
                            nothing received, part received, received in full, or received with no bill.
Direct costs                Costs filed against the event. Costs paid from a funding request or the SGA budget are
                            shown as *paid by SGA*. Purchases logged in advance are shown as *reserved*.
Margin                      What came in, less the costs **LNL paid itself**. Costs SGA pays for, and reserved
                            purchases, are left out.
Rentals billed / cost       What the client was billed for hired-in gear plus LNL's rental fee, against what the
                            hire actually cost.
==========================  ===========================================================================================

The button at the end of each row, showing how many entries are linked, opens them in the `Ledger`.

**The year is the year the show ran.** A late-June show is often billed and paid in July. Every entry linked to the
event counts towards it, whichever fiscal year the entry itself falls in.

**Student organizations' shows.** From FY27, LNL bills departments only. A student organization's show is paid for
through LNL's funding requests, so it can have costs and no bill without losing money. Its costs show as paid by SGA
and don't count against the margin. LNL's own money spent on an unbilled show still counts as a loss.

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
Paid in full, bill not marked paid       The payment covers the bill, but the events app still shows the bill as unpaid.
                                         Click `Mark bill paid`.
Marked paid, no payment filed            The events app says the bill was paid, but no payment is linked. It is
                                         probably still in the queue.
=======================================  ==============================================================================


Mark a Bill Paid
----------------

When the payment filed against an event covers its bill, the row offers `Mark bill paid`. Clicking it sets the bill's
paid date in the events app to the day the payment reached Workday. It never happens by itself. A multi-bill is marked
paid once the payments for every show on it cover it.

The same button is on the event's own page, on the `Billing` tab.


On the Event's Page
-------------------

Anyone who can see the finance pages also sees a small summary on each event's `Billing` tab, under the bills: billed,
received, costs, reserved purchases and margin, with the same flags and a link to the entries in the `Ledger`.

.. seealso::
    :doc:`/help/events/create-bill` covers creating and sending the bill itself.

`Last Modified: October 2, 2026`
