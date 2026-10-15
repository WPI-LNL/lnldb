============================
The Billing Page (Treasurer)
============================

Every event LNL bills goes through the same steps: you bill the client, the client sends the worktag to charge, you
create the Internal Service Delivery (ISD) in Workday, the client approves it and the money arrives, and you close the
event. The Billing page lists every bill at the step it is waiting on, longest-waiting first, with a button for what
comes next.

.. caution::
    **Permission Required:** Bill event

    Officers can use the Billing page. Find it under `Finance` > `Billing`, or click the `Billing` tab on any finance
    page.

-----

The Stages
----------

The page has one tab for each stage, with the number of bills at it.

=====================  ============================================================  ===============================
Tab                    What it means                                                 What to do
=====================  ============================================================  ===============================
Ready to bill          The VP has reviewed the event for billing, and no bill has    `Bill`, or tick events and
                       been sent. A bill you made but never emailed is listed here   `Make a multi-bill`. For a bill
                       too, marked *Not sent*.                                       not sent: `Email client`.
Waiting on client      The bill has been emailed, and the client has not yet sent    `Email again`
                       the worktag through the bill's form.
Create ISD             The client sent the worktag.                                  Create the ISD in Workday, then
                                                                                     `Mark entered into Workday`.
Waiting on approval    The ISD is in Workday, waiting for the client to approve it   `Mark paid` when the money
                       and the money to arrive.                                      arrives.
Paid                   The bill is paid, and the event is still open.                Close the event from its page.
=====================  ============================================================  ===============================

Events appear only once they are reviewed for billing, and leave once they are closed.

**Days** is how long a bill has been at its stage:

- *Ready to bill*: since the event was reviewed, or, for a bill not sent, since the bill was made.
- *Waiting on client*: since the bill was last emailed.
- *Create ISD*: since the client sent the worktag.
- *Waiting on approval*: since the event was marked entered into Workday.
- *Paid*: since the day it was paid.

The days for *Create ISD* and *Waiting on approval* come from the event's history. An event with no record there, such
as one changed outside the site, counts from the day the bill was last emailed.

**Fiscal year.** The fiscal year in the top bar shows only events that started in that year. Each tab says how many
more are in other years, because a show in June is often billed in July. Click the link to see them.

**Partition.** *Projection* shows film showings: events whose only services are Projection. A multi-bill counts as
Projection when every event on it does. *Event Production* shows everything else.


Ready to Bill
-------------

This tab has three sections:

- **Bills made but never sent.** Click `Email client` to send the bill.
- **Bill on its own.** Click `Bill` to make the event's bill, as on the event page.
- **Bill in bulk.** Events marked to be billed in bulk, grouped by client. Click `Make a multi-bill of these` to start
  a multi-bill with all of one client's events.

To put any other set of events on one bill, tick them in either section and click `Make a multi-bill of the ticked
events`. The new multi-bill opens with those events already ticked. If one of them is not marked to be billed in bulk,
the list widens to every event that can be billed, so it is still there. If the events are for different clients, the
form asks you to confirm before billing them together. See :doc:`multibills`.


Create the ISD
--------------

The *Create ISD* tab shows everything to type into Workday, each with a `Copy` button:

- **Amount**: what the client was billed. If the event's price has changed since, it says *Event now ...*. The ISD
  should charge what the client was billed, unless you send them a new bill first.
- **Worktag** and **fund**: what the client sent, with any comments they wrote.
- **Requester**: the event's contact, with their email address.
- **Memo**: *Lens and Lights services for* and the event's name. The ingestion queue reads the event back out of this
  memo when the payment arrives, so keep it as it is.

`Bill PDF` opens the event's invoice. Once the ISD is in Workday, click `Mark entered into Workday`. That moves the bill
to *Waiting on approval* and stops the client changing the worktag.


Multi-bills
-----------

A multi-bill is one row, under its name, with its events listed underneath. A multi-bill has no worktag form and no
*Entered into Workday* box, so it stays at *Waiting on client* until it is paid. Click `Mark paid` on its row or on its
page.


The Event Page
--------------

The top of an event's `Billing` tab shows a **Next step** box once the event is reviewed. It says which stage the bill
is at and gives the button for the next step, such as `Create bill`, `Email again` or `Mark entered into Workday`. The
box reads the same stages as the Billing page.


Where the Old Pages Went
------------------------

The billing pages in the `Events` menu were replaced by the Billing page. Bookmarks to them still work, and open the
matching tab. Their calendars were dropped.

=====================================  =================================================
Old page (Events menu)                 Now
=====================================  =================================================
Events to be Billed                    Billing > Ready to bill
Events to be Billed in Bulk            Billing > Ready to bill, *Bill in bulk*
Events Billed, Pending Payment         Billing > Waiting on client
Events Awaiting Workday Entry          Billing > Create ISD
Events Entered Into Workday            Billing > Waiting on approval
Events Paid                            Billing > Paid
MultiBills                             Billing > `All multi-bills`
=====================================  =================================================

*Events Pending Review* is still in the `Events` menu.

.. seealso::
    - :doc:`/help/events/create-bill` for making and emailing one event's bill.
    - :doc:`multibills` for billing several events at once.
    - :doc:`reports` for the *Owed to LNL* report, which shows each client's debt with its bill's stage.

`Last Modified: October 15, 2026`
