===========================================
Reserve Money Before a Purchase (Treasurer)
===========================================

A purchase can take weeks to reach Workday. Until it does, the money looks unspent, and a funding request looks like it
has more left than it really does. An **encumbrance** reserves the money now: it counts as spent on the funding request,
on the `Balances` tab and in the forecast, until the real Workday line arrives and you match the two up.

Log one whenever you commit to spending money that won't show up in Workday for a while -- an order placed, a rental
booked for a show, an invoice on its way.

.. caution::
    **Permission Required:** Edit subledger

    Officers can log purchases. If you do not see `Log a purchase` on the `Queue` tab, your role does not allow it.

-----

Log a Purchase
--------------

#. On the `Queue` tab click `Log a purchase`, or choose `Finance` > `Log a Purchase` in the navigation bar.
#. Fill in the form:

   - **Amount to encumber** -- what you expect it to cost. Type it as a positive number.
   - **Date** -- roughly when the money will go out.
   - **Description** and **What is this for?** -- both required. Nobody else will know later.
   - **Fund** and **Spend Category** -- as you would file the purchase. For a funding request, also choose the
     **Funding request line**.
   - **Incurred for event** -- for gear hired in for a show. Booking a rental is exactly when you know which show it is
     for, so it is worth filling in here.
   - **Project** and a **receipt or quote**, if you have them.

#. Click `Encumber funds`.

The encumbrance shows in the `Ledger` with the type *Encumbrance*, and as *reserved* beside its fund on the `Balances`
tab.


When the Charge Arrives
-----------------------

When the matching line is imported, its row in the queue is tagged `Maybe encumbered`, and `Already encumbered?` above
the row's boxes lists the open encumbrances that could be it, each with what was reserved, when, and how far it is from
the real amount.

#. Choose the right one. Nothing is chosen for you, because matching the wrong one charges the wrong budget line.
#. Click `Match & settle`.

The line takes its fund, category, event and funding request line from the encumbrance -- you don't fill anything in
again -- and its date becomes the date the money actually went out.

.. warning::
    **Don't file the line the ordinary way** while its encumbrance is open. That records the purchase twice: once as
    reserved and once as spent, and the funding request looks short by the reserved amount.

**If the amounts differ:**

- **The charge is smaller** than what was reserved: the line takes what it needs and the rest stays reserved, ready for
  the next charge. A rental invoiced in parts works this way.
- **The charge is a little larger:** the encumbrance stretches to cover it and closes.
- **The charge is a lot larger:** the encumbrance covers only what it reserved, and the rest of the line stays in the
  queue for you to file separately.


One Encumbrance, Many Lines
---------------------------

When one order arrives as many Workday lines, tick each of their rows in the queue, choose the encumbrance in the bar at
the bottom, and click `Draw selected`. The lines are matched oldest first until the encumbrance runs out, and the page
lists which were covered in full, which only in part, and which it didn't reach.


Change or Cancel an Encumbrance
-------------------------------

Find it in the `Ledger` -- search for its description, or choose the `Pending` status -- and open it to change any
detail. If the
purchase is cancelled, delete it from the same page and the money stops counting as reserved.

Matching a line to the wrong encumbrance can't be undone from the queue, because undoing would also throw away the
encumbrance. Open the entry from the `Ledger` and correct it instead.

`Last Modified: October 2, 2026`
