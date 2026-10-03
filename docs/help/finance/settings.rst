==========================================
Categories, Rules and Settings (Treasurer)
==========================================

Most of what the finance app knows about LNL -- its spend categories, its funds, which Workday codes mean what, the
minimum reserve -- is kept in tables you can change yourself, without asking the webmaster for a new version of the
site. They are all in the Django admin.

.. caution::
    **Permission Required:** Admin access

    Changing these needs access to the Django admin, with permission to change the finance tables. If you can't open
    them, ask the webmaster.

-----

Where to Find Them
------------------

Open the admin and scroll to the **Financial Subledger** section. The tables you are most likely to need:

==================================  ===================================================================================
Table                               What it holds
==================================  ===================================================================================
Finance Configuration               The handful of settings below.
LNL Spend Categories                LNL's own spending categories.
Spend Category Suggestion Rules     Which Workday code or wording fills in which spend category.
Fund Sources                        The funds -- Legacy, SGA Budget, SGA Funding Request, SGA Mandatory Transfer -- and
                                    how each one behaves.
Non-Event Revenue Sources           The kinds of income that aren't event billing, and the fund each goes into.
Partition Codes                     The two accounts, 226-AG and 315-AG, and which side each starts on.
CSV Column Aliases                  Other names for Workday's columns, for when Workday renames one.
Service Colours                     The colour of each service on the dashboard's charts.
==================================  ===================================================================================

The admin also shows funding requests, Workday lines, entries, planned purchases and history corrections, but those are
better changed on the finance pages themselves. Workday lines can't be changed at all.


Finance Configuration
---------------------

==============================================  ===================================================================
Setting                                         What it does
==============================================  ===================================================================
Fiscal year starts in                           July. Change it only if WPI moves its fiscal year: every line ever
                                                recorded moves to a different year.
Student organization fund                       The Workday fund number (810) that marks a client as a student
                                                organization rather than a department.
Past years / Future years in the picker         How many fiscal years the filter bar offers.
Books start on                                  The first day the books count (July 1, 2025). Lines from before it
                                                are history. Don't change it without talking to the webmaster:
                                                every balance is worked out from it.
Minimum reserve                                 The least LNL's own money should hold. The forecast and *Can we
                                                afford it?* answer against it.
Departments' share of billing before FY27 (%)   What share of past billing came from departments. Until it is set or
                                                can be measured, the forecast leaves past billing out. See
                                                :doc:`forecast`.
==============================================  ===================================================================


Spend Categories
----------------

To **add** a category, click `Add` and give it a name and a chart colour. To **rename** one, just change its name:
everything filed under it follows.

To **retire** a category, untick `Is active`. It disappears from the dropdowns, but everything already filed under it
keeps it. A category with money filed against it can't be deleted, so nothing is ever lost.

Two tick boxes change how the app treats a category:

- **Use for costs billed to an event** -- the category a cost is given when it is filed against one show without a
  category. `Event - Sub-Rental` has it.
- **Forecast from plans only** -- for spending chosen one purchase at a time, like equipment. The forecast leaves it out
  of the typical year and counts only what is reserved or planned. Both equipment categories have it.

.. warning::
    Leave the **slug** alone. It is the name links and bookmarks use, and the admin says so on the field.


Suggestion Rules
----------------

When an import warns that **no spend category rule covers** a Workday category, add a rule and every line with that
category -- in the queue now and in every future import, and in history -- fills itself in.

#. Under `Spend Category Suggestion Rules`, click `Add`.
#. **Match field:** usually *Workday's own spend category*.
#. **Match how:** *Is exactly*.
#. **Pattern:** the Workday category exactly as the warning wrote it, for example ``Rent - Equipment``.
#. **Spend category:** the LNL category it means. Save.

**Is exactly** and **Starts with** rules are treated as facts: they fill the box in. **Contains** rules are treated as
guesses and only offer a chip, because a word in a memo is not proof of what something was. Rules matching a ledger
account by its number (*Starts with* ``71100``) catch anything more specific rules don't.


Funds, Revenue Sources and Accounts
-----------------------------------

These rarely change, and a mistake here affects every balance, so check with the webmaster first. Each fund says which
account it is **held in**, what happens to it **at year end**, whether spending from it **must name a funding request
line**, and which Workday **fund codes** or **Tracking values** mean it. Each revenue source can say which fund its
money **goes into**; the queue then fills that fund in and refuses any other.

A Workday code renamed or renumbered by WPI is fixed here, not in the code: change the code on the matching row.

`Last Modified: October 2, 2026`
