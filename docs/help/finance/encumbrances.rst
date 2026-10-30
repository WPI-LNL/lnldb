============================================
Encumber Money Before a Purchase (Treasurer)
============================================

A purchase can take weeks to reach Workday. Until it does, the money looks unspent, and a funding request looks like it
has more left than it really does. An **encumbrance** sets the money aside now: it counts as spent on the funding request,
on the `Balances` tab, until the real Workday line arrives and you match the two up.

Log one whenever you commit to spending money that won't show up in Workday for a while -- an order placed, a rental
booked for a show, an invoice on its way.

.. caution::
    **Permission Required:** Edit subledger

    Officers can add encumbrances. If you do not see `Add Encumbrance` on the `Queue` tab, your role does not allow it.

-----

Add an Encumbrance
------------------

#. On the `Queue` tab click `Add Encumbrance`, or choose `Finance` > `Add Encumbrance` in the navigation bar.
#. Fill in the top of the form:

   - **Description** -- what the purchase is. Nobody else will know later.
   - **Date** -- roughly when the money will go out.
   - **Receipt or quote**, if you have one.

#. Fill in a line for each fund the purchase is charged to. Most purchases need only one. Click `Add a line` for more.

   - **Amount** -- what you expect that part to cost. Type it as a positive number.
   - **Description** -- leave it blank to use the one at the top, or say what this part is.
   - **Fund** and **Spend Category** -- as you would settle the purchase. For a funding request, also choose the
     **FR Line**; pick the request in the box above it first to list only its lines. See :doc:`funding-requests`.
   - **Incurred for event** -- for gear hired in for a show. Booking a rental is exactly when you know which show it is
     for, so it is worth filling in here.
   - **Project**, if it has one, and **Projection** for Projection spending.

#. Click `Encumber funds`.

Each line shows in the `Ledger` with the type *Encumbrance*, and in the *Encumbered* column beside its fund on the
`Balances` tab.


When the Charge Arrives
-----------------------

When the matching line is imported, its row in the queue is tagged `Maybe encumbered`, and `Already encumbered?` above
the row's boxes lists the open encumbrances that could be it, each with what was encumbered, when, and how far it is from
the real amount. An encumbrance with several lines is listed whole, with its lines indented under it.

#. Choose the right one. Nothing is chosen for you, because matching the wrong one charges the wrong budget line.

   - Choose the **whole encumbrance** when this one Workday line is the whole purchase. Each of your lines takes its own
     amount, in the order you wrote them, so the line is divided between the funds the way your lines were. If the
     charge is smaller, the lines it doesn't reach stay encumbered; if it is a little larger, the last line takes the
     difference.
   - Choose **one of its lines** when Workday charged that part on its own.

#. Click `Match & settle`.

The line takes its fund, category, event and funding request line from the encumbrance -- you don't fill anything in
again -- and its date becomes the date the money actually went out. Its description becomes the Workday memo, as on any
other settled line; the encumbrance keeps its own description for whatever is still encumbered.

.. warning::
    **Don't settle the line the ordinary way** while its encumbrance is open. That records the purchase twice: once as
    encumbered and once as spent, and the funding request looks short by the encumbered amount.

**If the amounts differ:**

- **The charge is smaller** than what was encumbered: the line takes what it needs and the rest stays encumbered, ready for
  the next charge. A rental invoiced in parts works this way.
- **The charge is a little larger** (up to a third more): the encumbrance stretches to cover it and closes. The extra
  is charged to the same fund and funding request line as the encumbrance.
- **The charge is a lot larger:** the encumbrance covers only what it was for, and the rest of the line stays in the
  queue for you to settle separately.

Whenever the charge is larger than what was encumbered, by any amount, you get a warning saying how much more it was and
where the extra went, so you can check it was meant.


One Encumbrance, Many Workday Lines
-----------------------------------

When one order arrives as many Workday lines, tick each of their rows in the queue, choose the encumbrance (or, for one
with several lines, the line) in the bar at the bottom, and click `Draw selected`. The lines are matched oldest first
until the encumbrance runs out, and the page lists which were covered in full, which only in part, and which it didn't
reach. The last line it reaches can stretch the encumbrance a little, as a single match does. Whenever the lines need
more than was encumbered, the page warns you.


Change or Cancel an Encumbrance
-------------------------------

Find it in the `Ledger` -- search for its description, or choose the `Pending` status -- and open it. The entry page
links to the encumbrance, where you can change its details, add or remove lines, or click `Delete` if the purchase is
cancelled; the money then stops counting as encumbered. Lines already matched to Workday are kept.

To undo a match, click `Undo` on the row before it disappears, or, later, open the Workday line and click
`Undo settling`. The line goes back to the queue, and the money goes back on the encumbrance as it was before you matched
it, at what was encumbered rather than what was charged. A warning says that both happened, so check the encumbrance is
still wanted.

`Last Modified: October 30, 2026`
