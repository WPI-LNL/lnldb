===========================================
Bill Several Events at Once (Treasurer)
===========================================

A **multi-bill** covers several events with one invoice and one payment -- a term of films, a run of shows for one
department. It has its own page, where you can see what it comes to and why, email the client, and mark it paid.

.. caution::
    **Permission Required:** Bill event

    Officers can create and change multi-bills. Find them under `Finance` > `Billing` > `All multi-bills`.

-----

Create a Multi-bill
-------------------

#. On the multi-bills list click `New multi-bill`. Or, on the Billing page's *Ready to bill* tab, tick the events and
   click `Make a multi-bill of the ticked events`, or click `Make a multi-bill of these` beside a client's events; the
   form then opens with them ticked (see :doc:`billing`).
#. Tick the events it covers. The list shows reviewed events that are marked to be billed in bulk and have no bill yet.
   Click `Also show events not marked to be billed in bulk` to see the rest. An event already on another multi-bill is
   never listed, so it cannot be billed twice.
#. **Bill to** is the client who pays. Leave it blank to bill the client most of the events are for.
#. Give it a **Name**, such as *Fall films*, and a **Description** if it helps. Both show on the invoice, and the name
   is in the email's subject. With no name, it is called something like *3 events for SocComm*.
#. Tick **Add each event's invoice** if the client should get each event's itemized invoice as well (see
   `The Invoice`_).
#. Click `Create`, or `Create and email the client` to go straight to the email.

There is no total to type. The bill comes to what each event would be billed on its own, plus any charges you add.

**Events for different clients.** Events booked under different clients can share a bill -- for example films booked
partly under "LNL" and partly under "LNL + SocComm Films". When the events you tick are for different clients, the form
lists them and asks you to tick a box to bill them together. The bill goes to the client under **Bill to**.


Add Charges to the Whole Bill
-----------------------------

On the bill's page, click `Add a charge`. There are three kinds:

==========================  ===========================================================================================
Kind                        What to fill in
==========================  ===========================================================================================
One-off charge or credit    A description, how many, and the price of one. A negative price is a credit.
Rental                      Gear hired in for the whole run. LNL's rental fee is added on top, as it is on an event,
                            unless you untick it. The fee's rate is fixed when you add it.
Percentage fee or discount  A percentage of what the events come to: ``10`` for a 10% fee, ``-10`` for a 10% discount.
==========================  ===========================================================================================

Fees, discounts and rental fees are rounded down to the cent, the same way an event's own are. Each charge has `Change`
and `Remove` beside it, and the total updates as you go.


Change a Multi-bill
-------------------

Until it is paid, click `Edit` on its page to tick or untick events, change who it is billed to, or rename it. The total
follows.

**If an event's price changes after you billed it**, the bill's page says so: *The saved total is ... but the events and
charges now come to ...*. Click `Update the total` to take up the new figure. Finance matches incoming payments against
the saved total, so update it before you send the invoice again.

Once a bill is paid, nothing about it can change until you mark it unpaid. Once any event on it is closed, it cannot
be changed at all.

**After its ISD is recorded**, the `Edit` and `Add a charge` pages warn you that changing what the bill comes to leaves
the ISD in Workday charging the old figure. If you change it anyway, the bill's page says what the ISD charges beside
what the bill now comes to. Change the ISD in Workday, then record the new amount with `Change ISD`.


The Invoice
-----------

Click `Invoice PDF` on the bill's page, or `PDF` on the list. The invoice is laid out like an event's 2025 invoice:
the bill's name and description, who it is billed to, its events with their dates and prices, its own charges, and the
grand total.

- A percentage fee or discount is listed under the events, since it is a percentage of what they come to.
- Rentals are listed with LNL's rental fee, as on an event. One-offs are listed under *Additional Fees*. A credit shows
  as a negative amount, such as *-$25.00*.
- When the events are for different clients, each event's client is shown beside it.
- An SGA-funded event is marked, with a note that SGA-funded events are charged only for rentals and additional fees.

**Add each event's invoice.** Tick `Add each event's invoice` when you create or edit the bill, and each event's own
itemized invoice follows the bill's, earliest event first, in the same file. The download and every email get the same
file. An event priced before the 2025 pricelists gets its old-style invoice. Each event's invoice is saved on the event
every time it is made, as it is when you bill an event on its own.


Email the Client
----------------

Click `Email client` on the bill's page or the multi-bills list, at any time. The subject and message are written out
for you -- the events, the total, and a request to reply with the worktag to charge -- and you can edit them before
sending. The invoice is attached, named after the bill (such as *fall-films-bill.pdf*). Every email sent is listed on
the bill's page.


The Worktag and the ISD
-----------------------

A multi-bill has no form for the client, so the worktag always comes back by email. Click `Enter worktag` on the bill's
page, or on its row on the Billing page, and type it in. The form starts with the worktag on file for the client from
their last bill, if there is one: confirm it with them.

Then create the ISD in Workday and click `Record ISD` with the number Workday gives it. That marks every event on the
bill entered into Workday. The bill's page shows the worktag and the ISD once they are recorded. See
:doc:`billing` for the whole sequence.


Mark It Paid
------------

Usually you don't need to. When its payment arrives, the finance queue recognises the ISD number recorded on the bill
and offers to split the payment across its events. The split page has a ticked box to mark the bill paid on the day
the money arrived: save the split, and it is done. See :doc:`billing`.

Otherwise, click `Mark paid...` on the bill's page or the list.

- If the payments linked to its events cover the bill, the date is filled in with the day the last of the money
  reached Workday.
- Otherwise the date is today. Change it to the day the money arrived, and say **how it was paid**, such as *check
  from SAO*. That is required, because no payment in the ledger shows it.

`Mark unpaid` undoes it.

.. seealso::
    :doc:`events` explains how a payment for a multi-bill is split across its events in the finance queue.

`Last Modified: October 19, 2026`
