====================================
Generate and Send a Bill (Treasurer)
====================================

The LNLDB allows you to easily create an invoice for an event based on the event information in our database and
automatically generates an email to send to the client for gathering their Workday worktag details.

.. seealso::
    The finance app's :doc:`Billing page </help/finance/billing>` lists every event waiting to be billed, and every
    bill at the step it is waiting on, from sending it to closing the event. It replaced the billing lists in the
    `Events` menu. Once an event is reviewed, the top of its `Billing` tab shows the next step.


Generate an Invoice
-------------------

You can generate an invoice or quote for an event at any time on the event detail page. Select the `Billing` tab, then
under `Bills` click the blue `Download Invoice` or `Download Quote` button.

-----

Billing a Client
----------------

.. caution::
    **Permission Required:** Bill event

    In order to create or update bills for an event, you must have been assigned a role that gives you permission to do
    so. If you do not see the `Create Bill` button, your current role(s) may not grant you adequate permission.


Create and Send a Bill
^^^^^^^^^^^^^^^^^^^^^^

.. note::
    The event must have already been reviewed before it can be billed. If the event status is `Awaiting Review`, please
    contact the officer responsible for reviewing the event before continuing.

#. Click `Create Bill` on the event page. This button will only appear once the event has been reviewed.
#. Enter the date billed and the total amount due. These fields will be pre-filled with the current date and the total
   amount from the `Price Breakdown` in the billing tab. Be sure to double check these values and update them if
   necessary.
#. Next you will have the option to generate and send an email to the client to request their Workday worktag. If you
   do not wish to send an email at this time, click `Save and Return`. Otherwise click `Save and Make Email`.
#. If you chose to send the email, the next page will automatically generate an email for you and give you the
   opportunity to edit the message and subject line. The `User Recipients` field allows you to define specific users to
   send the email to, while the `Client Recipients` field lists any applicable exec board email aliases. Once you're
   satisfied with the setup, click `Send Email`. The bill will be added to the email automatically as an attachment.


When the Client Sends Their Worktag
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When the client fills out the payment form from the email, the treasurer's address is sent a
`Worktag Received: <event name>` email listing the funding source, worktag and any comments. The event is then ready
for you to create the Internal Service Delivery in Workday.

If the client goes back and changes what they sent, you get an `Event Workday Info Updated` email listing exactly what
changed, old value to new. The form locks once the ISD is recorded on the finance Billing page.

If the client replies with the worktag by email instead, record it yourself with `Enter worktag` on the Billing page.

The client's form is pre-filled with the funding source and worktag they used last, so a returning client usually only
has to check it and submit.


Updating a Bill
^^^^^^^^^^^^^^^

To update the details of a bill, click the `Update` button next to the bill you wish to edit. Update the amount, then
hit `Save Changes`. Clicking `Reset Form` will reset the `Amount` field. Whether the bill is paid is not changed here;
see below.


Mark a Bill as Paid
^^^^^^^^^^^^^^^^^^^

Most bills are marked paid in the finance queue, as the payment from Workday that covers them is filed. See
:doc:`/help/finance/billing`.

Otherwise, under the `Billing` tab, locate the bill and click `Mark Paid...`. The button also appears on event lists
such as the `All Events` page (`Events` > `All Events`). It opens a form asking the day the bill was paid. If no
payment filed from Workday covers the bill, it also asks how it was paid, such as a check or cash.

`Last Modified: October 16, 2026`
