"""
The reference data a finance install needs on day one.

Everything here was hard-coded in the application until it became clear it
changes on a schedule that has nothing to do with deploys: LNL renames a spend
category, SGA renumbers a fund, Workday invents a spend category nobody has
mapped. So it lives in tables the Treasurer maintains from the admin, and this
migration is only the starting position -- every row below can be renamed,
recoloured, reordered, retired or deleted afterwards without touching code.

The slugs are the stable part. URL filters use them (``?category=repairs``), so
renaming a category is free and changing its *slug* is the breaking edit.

Seeding is ``get_or_create`` throughout, keyed on the slug or code, so this is
safe to re-run and will never overwrite an edit made in the admin.

.. note::

   This file and ``0001_initial`` together replace the sixteen migrations the
   app was built through, which were squashed before it was ever deployed. The
   rows below are not a retyping of those migrations: they were captured from a
   database built by running all sixteen, so the end state is identical by
   construction rather than by review.
"""
from django.db import migrations

# (slug, name, colour, sort order, is_event_passthrough, description)
#
# LNL's own chart of spending, which is not WPI's and is not meant to be: it is
# the list the Treasurer reports against and the one the dashboard pie is cut
# into. Several of these deliberately gather up things Workday keeps apart --
# Club Operations is printing, marketing, recruiting, internal events, gifts,
# travel and office supplies, because none of those is worth its own slice of a
# club's year.
#
# Colours come from the Tableau 20 ramp, chosen so the categories stay
# distinguishable on the dashboard pie and remain colourblind-safe. The two
# Equipment rows and the two Event rows each take neighbouring shades of one
# hue, so a glance at the pie reads the pair as one area before it reads the
# split.
SPEND_CATEGORIES = [
    ('equipment_capital', 'Equipment - Capital', '#E15759', 0, False,
     'Gear expensive enough to be carried as an asset rather than written off in the year '
     'it was bought.'),
    ('equipment_noncapital', 'Equipment - Non Capital', '#FF9D9A', 1, False,
     'Ordinary gear purchases: everything bought outright and expensed this year.'),
    ('repairs', 'Maintenance and Repair', '#F28E2B', 2, False,
     'Putting existing gear back into service, and the servicing that keeps it there.'),
    ('consumables', 'Consumables', '#4E79A7', 3, False,
     'Stock that gets used up: tape, gel, batteries, cable ties, lamps.'),
    ('food', 'Food', '#F1CE63', 4, False, ''),
    ('software', 'Software and Subscriptions', '#59A14F', 5, False,
     'Licences and anything billed on a recurring basis.'),
    ('film_rights', 'Films Rights and Shipping', '#B07AA1', 6, False,
     'The cost of running a film: the rights, getting the print here and back again, and '
     'the popcorn and posters that go with it.'),
    ('merch', 'Merch', '#FABFD2', 7, False, 'Crew apparel and anything sold or given away.'),
    ('club_operations', 'Club Operations', '#79706E', 8, False,
     'Running the club rather than running a show: printing, marketing, recruiting, '
     'internal events, gifts, travel, office supplies and the like.'),
    ('safety', 'Safety and Inspections', '#86BCB6', 9, False,
     'Keeping people safe and proving it: PPE, first aid, and the chain motor and rigging '
     'inspections that have to happen on a schedule.'),
    ('adjustments', 'Adjustments', '#8CD17D', 10, False,
     'Only for mis-billed lines and for making the books balance. Nothing was really '
     'bought, so anything filed here is a correction of something that was.'),
    ('event_subrental', 'Event - Sub-Rental', '#76B7B2', 11, True,
     'Gear hired in for one show and charged straight on to that show. Filled in '
     'automatically when an expense names the event it was incurred for, because the '
     'linked event already says everything a category could.'),
    ('event_other', 'Event - Other', '#A0CBE8', 12, False,
     'A non-rental cost passed straight through to a client -- incurred for one event and '
     'billed on to it unchanged.'),
]

# (slug, name, workday fund codes, requires a funding request, sort order, description)
#
# ``workday_fund_codes`` is what lets an import fill the Fund box in by itself.
# Note that SGA Budget deliberately has none: 810-FD is the agency fund the
# whole account sits in, so every LNL line carries it whoever actually paid,
# and reading it as "SGA funded this" was a coin flip presented as a fact.
FUND_SOURCES = [
    ('sga_fr', 'SGA Funding Request', '', True, 0, ''),
    ('sga_budget', 'SGA Budget', '', False, 1, ''),
    ('legacy', 'Legacy', '220, 250, 500, 120', False, 2, ''),
]

# (slug, name, sort order, description)
REVENUE_SOURCES = [
    ('sga_baseline', 'SGA Baseline', 0, ''),
    ('asset_liquidation', 'Asset Liquidation', 1, ''),
    ('alumni', 'Alumni / Donation', 2, ''),
]

# (code, is projection, crossing needs a written reason, worktag, notes)
#
# These decide which side of the Event Production / Projection partition a
# bank line starts on. A starting position only -- the Treasurer has the final
# say, except that leaving the Projection side has to be explained.
PARTITION_CODES = [
    ('226-AG', False, False, 'student_organization', 'Lens & Light Club — Event Production'),
    ('315-AG', True, True, 'student_organization', 'Projection'),
]

# (match field, match mode, pattern, category slug, confidence, priority, notes)
#
# The table behind the queue's spend-category suggestions. Priority orders the
# checks and the first match wins, so specific rules sit above general ones:
# "chain motor" has to be tried before "repair", and a Workday account code
# beats a word noticed in a memo.
#
# ``match_mode`` is what separates a lookup from a guess. *exact* and *starts*
# read a code Workday assigned, so the form fills the box in; *contains* and
# *word* are our reading of some prose and are only ever offered as a chip.
SUGGESTION_RULES = [
    # 1. Workday's own Spend Category, matched exactly. The finest code in the
    #    export: "Printing" and "Supplies - Medical" both sit under the ledger
    #    account 71100:Supplies and are not the same thing.
    ('spend_category', 'exact', 'Supplies', 'consumables', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Supplies - Office', 'club_operations', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Supplies - Outreach and Events', 'club_operations', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Supplies - Medical', 'safety', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Supplies - Personal Protection Equipment (PPE)', 'safety', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Audio Visual Equipment', 'equipment_noncapital', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Equipment - General', 'equipment_noncapital', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Equipment - Laboratory', 'equipment_noncapital', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Furniture & Fixtures', 'equipment_noncapital', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Hardware - Computers & Workstations', 'equipment_noncapital', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Hardware - Network & Security', 'equipment_noncapital', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Capital Equipment', 'equipment_capital', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Software', 'software', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Subscriptions & Memberships', 'software', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Maintenance - Equipment Repair', 'repairs', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Maintenance - Preventative - Equipment', 'repairs', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Hardware - Repairs & Maintenance', 'repairs', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Rent - Equipment', 'event_subrental', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Food', 'food', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Internal Service Chartwells Catering IDT', 'food', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Printing', 'club_operations', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Printing IDT', 'club_operations', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Postage & Shipping', 'film_rights', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Postage IDT', 'film_rights', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Uniform', 'merch', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Gifts', 'club_operations', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Prizes & Awards', 'club_operations', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Event Sponsorship', 'club_operations', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Hosted Events and Conferences by WPI', 'club_operations', 'high', 5, 'Workday spend category, matched exactly'),

    # 2. The ledger account, matched on its number. Coarser, but still a code
    #    WPI assigned, so it catches the Workday categories nobody has mapped.
    #    Every account seen on an expense line across FY18-FY26 appears here;
    #    one that does not leaves the Treasurer typing.
    ('ledger_account', 'starts', '70000', 'club_operations', 'high', 10, 'Interdepartmental Transfers - IDT'),
    ('ledger_account', 'starts', '71050', 'merch', 'high', 10, 'Uniform Expense'),
    ('ledger_account', 'starts', '71100', 'consumables', 'high', 10, 'Supplies'),
    ('ledger_account', 'starts', '71200', 'film_rights', 'high', 10, 'Postage & Shipping -- overwhelmingly film prints going back'),
    ('ledger_account', 'starts', '71500', 'event_subrental', 'high', 10, 'Rent - Equipment'),
    ('ledger_account', 'starts', '72000', 'software', 'high', 10, 'Subscriptions & Memberships'),
    ('ledger_account', 'starts', '73100', 'club_operations', 'high', 10, 'Travel'),
    ('ledger_account', 'starts', '73200', 'food', 'high', 10, 'Food'),
    ('ledger_account', 'starts', '73400', 'club_operations', 'high', 10, 'Entertainment and Gifts'),
    ('ledger_account', 'starts', '74100', 'repairs', 'high', 10, 'Repairs & Maintenance'),
    ('ledger_account', 'starts', '74600', 'club_operations', 'high', 10, 'Event Sponsorship'),
    ('ledger_account', 'starts', '74800', 'club_operations', 'high', 10, 'Other Expenses'),
    ('ledger_account', 'starts', '74900', 'club_operations', 'high', 10, 'Miscellaneous Fees'),
    ('ledger_account', 'starts', '75000', 'safety', 'high', 10, 'Professional Services -- LNL buys its inspections under this account'),
    ('ledger_account', 'starts', '79600', 'software', 'high', 10, 'IT Hardware & Software'),
    ('ledger_account', 'starts', '79700', 'equipment_noncapital', 'high', 10, 'Equipment Expense'),

    # 3. Wording. A guess about English rather than a code, so these are only
    #    ever offered as a chip -- see SuggestionRule.LOOKUP_MODES -- and are
    #    only reached at all when neither code pass above matched.
    ('spend_category', 'contains', 'chain motor', 'safety', 'high', 20, ''),
    ('spend_category', 'contains', 'chain hoist', 'safety', 'high', 20, ''),
    ('spend_category', 'contains', 'inspection', 'safety', 'high', 20, ''),
    ('spend_category', 'contains', 'capital', 'equipment_capital', 'high', 25, ''),
    ('spend_category', 'contains', 'repair', 'repairs', 'high', 30, ''),
    ('spend_category', 'contains', 'maintenance', 'repairs', 'high', 30, ''),
    ('spend_category', 'contains', 'software', 'software', 'high', 30, ''),
    ('spend_category', 'contains', 'subscription', 'software', 'high', 30, ''),
    ('spend_category', 'contains', 'licen', 'software', 'high', 30, ''),
    ('spend_category', 'contains', 'shipping', 'film_rights', 'high', 30, ''),
    ('spend_category', 'contains', 'freight', 'film_rights', 'high', 30, ''),
    ('spend_category', 'contains', 'postage', 'film_rights', 'high', 30, ''),
    ('spend_category', 'contains', 'rental', 'event_subrental', 'high', 30, ''),
    ('spend_category', 'contains', 'food', 'food', 'high', 30, ''),
    ('spend_category', 'contains', 'catering', 'food', 'high', 30, ''),
    ('spend_category', 'contains', 'merch', 'merch', 'high', 30, ''),
    ('spend_category', 'contains', 'apparel', 'merch', 'high', 30, ''),
    ('spend_category', 'contains', 'safety', 'safety', 'high', 30, ''),
    ('spend_category', 'contains', 'printing', 'club_operations', 'high', 35, ''),
    ('spend_category', 'contains', 'marketing', 'club_operations', 'high', 35, ''),
    ('spend_category', 'contains', 'advertis', 'club_operations', 'high', 35, ''),
    ('spend_category', 'contains', 'gift', 'club_operations', 'high', 35, ''),
    ('spend_category', 'contains', 'travel', 'club_operations', 'high', 35, ''),
    ('spend_category', 'contains', 'hardware', 'equipment_noncapital', 'high', 40, ''),
    ('spend_category', 'contains', 'equipment', 'equipment_noncapital', 'high', 45, ''),
    ('spend_category', 'contains', 'supply', 'consumables', 'high', 50, ''),
    ('spend_category', 'contains', 'supplies', 'consumables', 'high', 50, ''),
    ('spend_category', 'contains', 'consumable', 'consumables', 'high', 50, ''),
]


def seed(apps, schema_editor):
    """ Create the reference rows, leaving any that already exist alone. """
    SpendCategory = apps.get_model('finance', 'SpendCategory')
    FundSource = apps.get_model('finance', 'FundSource')
    RevenueSource = apps.get_model('finance', 'RevenueSource')
    PartitionCode = apps.get_model('finance', 'PartitionCode')
    SuggestionRule = apps.get_model('finance', 'SuggestionRule')
    FinanceSettings = apps.get_model('finance', 'FinanceSettings')

    categories = {}
    for slug, name, color, order, passthrough, description in SPEND_CATEGORIES:
        categories[slug], _ = SpendCategory.objects.get_or_create(
            slug=slug, defaults={
                'name': name, 'color': color, 'sort_order': order,
                'is_event_passthrough': passthrough, 'description': description})

    for slug, name, codes, requires_fr, order, description in FUND_SOURCES:
        FundSource.objects.get_or_create(
            slug=slug, defaults={
                'name': name, 'workday_fund_codes': codes,
                'requires_funding_request': requires_fr, 'sort_order': order,
                'description': description})

    for slug, name, order, description in REVENUE_SOURCES:
        RevenueSource.objects.get_or_create(
            slug=slug, defaults={'name': name, 'sort_order': order,
                                 'description': description})

    for code, projection, needs_reason, worktag, notes in PARTITION_CODES:
        PartitionCode.objects.get_or_create(
            code=code, defaults={
                'is_projection': projection, 'crossing_requires_reason': needs_reason,
                'worktag': worktag, 'notes': notes})

    for field, mode, pattern, slug, confidence, priority, notes in SUGGESTION_RULES:
        category = categories.get(slug)
        if category is None:
            continue
        SuggestionRule.objects.get_or_create(
            match_field=field, pattern=pattern, spend_category=category,
            defaults={'match_mode': mode, 'confidence': confidence,
                      'priority': priority, 'notes': notes})

    # get_or_create, not update_or_create: on a database that already has a
    # configuration row this must not reset it to the defaults. The same rule
    # as everywhere else here -- seeding never overwrites an admin edit.
    FinanceSettings.objects.get_or_create(pk=1, defaults={
        'fiscal_year_start_month': 7,
        'student_org_workday_fund': 810,
        'fiscal_years_back': 6,
        'fiscal_years_forward': 1,
    })

    _seed_service_colors(apps)


def _seed_service_colors(apps):
    """
    Colour LNL's three long-standing service lines on the service-mix chart.

    Only for categories the events app already has. An install without them
    simply gets no rows and the chart falls back to the shared ramp, which is
    why this is a lookup rather than a create -- ``ServiceColor`` is keyed to
    the events ``Category`` row, so inventing one here would attach the colour
    to nothing.
    """
    Category = apps.get_model('events', 'Category')
    ServiceColor = apps.get_model('finance', 'ServiceColor')
    for name, color in (('Lighting', '#EDC948'),
                        ('Sound', '#4E79A7'),
                        ('Projection', '#B07AA1')):
        category = Category.objects.filter(name=name).first()
        if category is not None:
            ServiceColor.objects.get_or_create(category=category,
                                               defaults={'color': color})


def unseed(apps, schema_editor):
    """
    Remove the seeded rows on the way back down.

    Categories are left alone: by the time anyone reverses this, real money may
    be filed against them, and the foreign key is PROTECT so the delete would
    fail anyway. Dropping the tables is ``0001_initial``'s job.
    """
    apps.get_model('finance', 'SuggestionRule').objects.all().delete()
    apps.get_model('finance', 'ServiceColor').objects.all().delete()
    apps.get_model('finance', 'FinanceSettings').objects.all().delete()


class Migration(migrations.Migration):
    """ Seeds the editable vocabularies, the suggestion rules and the settings row. """

    dependencies = [
        ('finance', '0001_initial'),
        ('events', '0017_is_sga_funded_squashed_0018_pricelist_extras'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
