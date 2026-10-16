============================
The Billing Page (Treasurer)
============================

Every event LNL bills goes through the same steps: you bill the client, the client sends the worktag to charge, you
create the Internal Service Delivery (ISD) in Workday and record its number, the client approves it and the money
arrives, and you close the event. The Billing page lists every bill at the step it is waiting on, longest-waiting
first, with a button for what comes next.

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
                       been sent. A bill you made but never emailed is listed here   `Make a multi-bill`, or
                       too, marked *Not sent*.                                       `No bill needed`. For a bill
                                                                                     not sent: `Email client`.
No bill needed         You decided the event is not billed.                          Close the event from its page,
                                                                                     or `Undo`.
Waiting on client      The bill has been emailed, and no worktag has come back.      `Email again`, or
                                                                                     `Enter worktag` if the client
                                                                                     replied by email.
Create ISD             The client sent the worktag.                                  Create the ISD in Workday, then
                                                                                     type its number and click
                                                                                     `Record ISD`.
Waiting on approval    The ISD is in Workday, waiting for the client to approve it   `Mark paid` when the money
                       and the money to arrive.                                      arrives.
Paid                   The bill is paid, and the event is still open.                Close the event from its page.
=====================  ============================================================  ===============================

Events appear only once they are reviewed for billing, and leave once they are closed.

**Days** is how long a bill has been at its stage:

- *Ready to bill*: since the event was reviewed, or, for a bill not sent, since the bill was made.
- *No bill needed*: since you decided it.
- *Waiting on client*: since the bill was last emailed.
- *Create ISD*: since the worktag came in.
- *Waiting on approval*: since the day the ISD was created in Workday.
- *Paid*: since the day it was paid.

When the client sends the worktag through the bill's form, the day comes from the event's history. An event with no
record there, such as one changed outside the site, counts from the day the bill was last emailed.

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


No Bill Needed
--------------

Some reviewed events are never billed. Click `No bill needed` beside the event and choose why:

- **SGA-funded.** SGA pays for the show, and it had no rentals or one-off charges, which are the only things an
  SGA-funded show is charged for.
- **Billing not applicable.**
- **LNL's own event.**
- **Other.** Say why in the note.

An event marked *SGA-funded* that comes to $0 is tagged *SGA-funded, $0* on the *Ready to bill* tab. Its `No bill
needed` button is the main one, and the form opens with *SGA-funded* already chosen, saying why. Nothing is saved until
you click the button.

The event moves to the *No bill needed* tab and stays there until you close it. Click `Undo` if it should be billed
after all; it goes back to *Ready to bill*. An event with a bill cannot be marked, and an event marked *No bill needed*
cannot be billed or put on a multi-bill until you undo it. On the finance *Events* page it shows as *no bill needed*
rather than *not billed*.


The Client's Worktag
--------------------

The bill's email links to a form where the client sends the worktag and fund to charge. When they use it, the bill
moves to *Create ISD* by itself.

If the client replies by email instead, click `Enter worktag` on the *Waiting on client* tab and type what they sent.
The form starts with the worktag on file for that client from their last bill, if there is one, and says so: confirm it
with the client before you rely on it. A multi-bill has no form for the client, so its worktag is always entered this
way.


Create the ISD
--------------

The *Create ISD* tab shows everything to type into Workday, each with a `Copy` button:

- **Amount**: what the client was billed. If the price has changed since, it says *Now ...*. The ISD should charge what
  the client was billed, unless you send them a new bill first.
- **Worktag** and **fund**: what the client sent, with any comments they wrote. If you entered a worktag on the bill
  and the client then used the form with a different one, it says *Form says ...*: check with the client.
- **Requester**: the event's contact, or for a multi-bill, the client's person in charge.
- **Memo**: *Lens and Lights services for* and the event's name, or the multi-bill's name. The ingestion queue reads
  the event back out of this memo when the payment arrives, so keep it as it is.

`Bill PDF` opens the invoice. Once the ISD is in Workday, type the number Workday gives it -- such as 25090179-ISD; the
digits alone will do -- in the box on its row and click `Record ISD`. That records the ISD with the worktag, fund and
amount on the row, dated today, moves the bill to *Waiting on approval*, and stops the client changing the worktag. To
record anything different, such as another amount or an earlier day, click `Change` for the whole form.

An ISD number can be recorded only once. The page refuses one that is already on another bill.


Waiting on Approval
-------------------

Each row shows the ISD's number and the day it was created. Click `Mark paid` when the money arrives.

`Change ISD` opens the form again. Use it to correct a number, or click `Remove the ISD` there if it was entered by
mistake or cancelled in Workday: the bill goes back to *Create ISD*, and the client's form opens again.

A bill marked entered into Workday before ISD numbers were recorded shows *not recorded*. Click `Record ISD` to add its
number.

**If a bill changes after its ISD.** Changing a multi-bill's events or charges, or a bill's amount, after its ISD is
recorded warns you first that the ISD will no longer match. Afterwards the bill shows what the ISD charged beside what
the bill now comes to. Change the ISD in Workday, then record the new amount with `Change ISD`.


Multi-bills
-----------

A multi-bill is one row, under its name, with its events listed underneath. It goes through the same stages as a bill
for one event: enter the worktag the client sends back, record the ISD, then mark it paid. Its page has the same
buttons.


The Event Page
--------------

The top of an event's `Billing` tab shows a **Next step** box once the event is reviewed. It says which stage the bill
is at and gives the button for the next step, such as `Create bill`, `No bill needed`, `Enter worktag` or `Record ISD`.
The box reads the same stages as the Billing page.


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

*Events Pending Review* is still in the `Events` menu. The `Mark Entered Into Workday` button the event lists had is
gone: recording the ISD does the same, and keeps its number.

.. seealso::
    - :doc:`/help/events/create-bill` for making and emailing one event's bill.
    - :doc:`multibills` for billing several events at once.
    - :doc:`reports` for the *Owed to LNL* report, which shows each client's debt with its bill's stage.

`Last Modified: October 15, 2026`
