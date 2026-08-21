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
# Colours come from the Tableau 20 ramp, chosen so the categories stay
# distinguishable on the dashboard pie and remain colourblind-safe.
SPEND_CATEGORIES = [
    ('repairs', 'Repairs', '#F28E2B', 0, False, ''),
    ('consumables', 'Consumables', '#4E79A7', 1, False, ''),
    ('new_stuff', 'New Stuff', '#E15759', 2, False, ''),
    ('radio', 'Radio Things', '#499894', 3, False, ''),
    ('booth', 'Booth Expenses', '#B07AA1', 4, False, ''),
    ('shipping', 'Shipping', '#86BCB6', 5, False, ''),
    ('printing', 'Printing', '#79706E', 6, False, ''),
    ('marketing', 'Marketing', '#D37295', 7, False, ''),
    ('spotify', 'Spotify', '#59A14F', 8, False, ''),
    ('slack', 'Slack', '#D4A6C8', 9, False, ''),
    ('food', 'Food', '#F1CE63', 10, False, ''),
    ('merch', 'Merch', '#FABFD2', 11, False, ''),
    ('safety', 'Safety', '#FF9D9A', 12, False, ''),
    ('gifts', 'Gifts', '#B6992D', 13, False, ''),
    ('adjustments', 'Adjustments', '#8CD17D', 14, False, ''),
    ('chain_motor', 'Chain Motor Inspection', '#FFBE7D', 15, False, ''),
    ('internal_events', 'LNL Internal Events', '#A0CBE8', 16, False, ''),
    ('other', 'Other', '#BAB0AC', 17, False, ''),
    ('event_expense', 'Event Expense', '#76B7B2', 90, True, 'A cost incurred for one specific event and passed through to it -- sub-rentals, one-off hires. The linked event says the rest.'),
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
    ('spend_category', 'exact', 'Supplies', 'consumables', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Supplies - Office', 'consumables', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Supplies - Outreach and Events', 'consumables', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Supplies - Medical', 'safety', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Supplies - Personal Protection Equipment (PPE)', 'safety', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Audio Visual Equipment', 'new_stuff', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Equipment - General', 'new_stuff', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Equipment - Laboratory', 'new_stuff', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Furniture & Fixtures', 'new_stuff', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Hardware - Computers & Workstations', 'new_stuff', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Hardware - Network & Security', 'new_stuff', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Software', 'new_stuff', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Maintenance - Equipment Repair', 'repairs', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Maintenance - Preventative - Equipment', 'repairs', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Hardware - Repairs & Maintenance', 'repairs', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Food', 'food', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Internal Service Chartwells Catering IDT', 'food', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Printing', 'printing', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Printing IDT', 'printing', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Postage & Shipping', 'shipping', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Postage IDT', 'shipping', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Uniform', 'merch', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Gifts', 'gifts', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Prizes & Awards', 'gifts', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Event Sponsorship', 'internal_events', 'high', 5, 'Workday spend category, matched exactly'),
    ('spend_category', 'exact', 'Hosted Events and Conferences by WPI', 'internal_events', 'high', 5, 'Workday spend category, matched exactly'),
    ('ledger_account', 'starts', '71100', 'consumables', 'high', 10, 'Supplies'),
    ('ledger_account', 'starts', '71200', 'shipping', 'high', 10, 'Postage & Shipping'),
    ('ledger_account', 'starts', '72000', 'other', 'high', 10, 'Subscriptions & Memberships'),
    ('ledger_account', 'starts', '73100', 'other', 'high', 10, 'Travel'),
    ('ledger_account', 'starts', '73200', 'food', 'high', 10, 'Food'),
    ('ledger_account', 'starts', '74100', 'repairs', 'high', 10, 'Repairs & Maintenance'),
    ('ledger_account', 'starts', '74900', 'other', 'high', 10, 'Miscellaneous Fees'),
    ('ledger_account', 'starts', '79600', 'new_stuff', 'high', 10, 'IT Hardware & Software'),
    ('ledger_account', 'starts', '70000', 'other', 'high', 10, 'Interdepartmental Transfers - IDT'),
    ('ledger_account', 'starts', '71050', 'merch', 'high', 10, 'Uniform Expense'),
    ('ledger_account', 'starts', '71500', 'other', 'high', 10, 'Rent - Equipment'),
    ('ledger_account', 'starts', '73400', 'gifts', 'high', 10, 'Entertainment and Gifts'),
    ('ledger_account', 'starts', '74600', 'internal_events', 'high', 10, 'Event Sponsorship'),
    ('ledger_account', 'starts', '74800', 'other', 'high', 10, 'Other Expenses'),
    ('ledger_account', 'starts', '75000', 'other', 'high', 10, 'Professional Services'),
    ('ledger_account', 'starts', '79700', 'new_stuff', 'high', 10, 'Equipment Expense'),
    ('spend_category', 'contains', 'chain motor', 'chain_motor', 'high', 20, ''),
    ('spend_category', 'contains', 'chain hoist', 'chain_motor', 'high', 20, ''),
    ('spend_category', 'contains', 'motor inspection', 'chain_motor', 'high', 20, ''),
    ('spend_category', 'contains', 'repair', 'repairs', 'high', 30, ''),
    ('spend_category', 'contains', 'maintenance', 'repairs', 'high', 30, ''),
    ('spend_category', 'contains', 'radio', 'radio', 'high', 30, ''),
    ('spend_category', 'contains', 'headset', 'radio', 'high', 30, ''),
    ('spend_category', 'contains', 'projector', 'booth', 'high', 30, ''),
    ('spend_category', 'contains', 'shipping', 'shipping', 'high', 30, ''),
    ('spend_category', 'contains', 'freight', 'shipping', 'high', 30, ''),
    ('spend_category', 'contains', 'printing', 'printing', 'high', 30, ''),
    ('spend_category', 'contains', 'marketing', 'marketing', 'high', 30, ''),
    ('spend_category', 'contains', 'advertis', 'marketing', 'high', 30, ''),
    ('spend_category', 'contains', 'food', 'food', 'high', 30, ''),
    ('spend_category', 'contains', 'catering', 'food', 'high', 30, ''),
    ('spend_category', 'contains', 'merch', 'merch', 'high', 30, ''),
    ('spend_category', 'contains', 'apparel', 'merch', 'high', 30, ''),
    ('spend_category', 'contains', 'safety', 'safety', 'high', 30, ''),
    ('spend_category', 'contains', 'gift', 'gifts', 'high', 30, ''),
    ('spend_category', 'contains', 'capital', 'new_stuff', 'high', 40, ''),
    ('spend_category', 'contains', 'hardware', 'new_stuff', 'high', 40, ''),
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
