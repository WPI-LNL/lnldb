"""
Bring a database that was seeded earlier onto the current spend-category list.

``0002_seed_reference_data`` is the starting position for a *new* install, and
Django runs it exactly once -- it is written down in ``django_migrations`` and
never looked at again. So editing that file changes what the next fresh
database gets and nothing else: an install set up before the Treasurer revised
the list still offers "New Stuff", "Spotify" and "Booth Expenses", and no
amount of rewriting 0002 will reach it. That is what this migration is for.

It deliberately breaks the rule the rest of the seeding follows. Everywhere
else, seeding is ``get_or_create`` so that a migration can never overwrite an
admin edit; here the whole point is to overwrite, because the thirteen rows
below *are* the edit -- LNL's revised chart of spending, which the Treasurer
asked for by name. The narrow scope is what keeps that safe: only the slugs the
current seed names are rewritten, only the slugs in :data:`MERGED_INTO` are
retired, and a category this install added that appears in neither list is left
exactly where it is.

Three things happen, in an order that matters:

1. The current list is applied, which creates the genuinely new rows (the two
   Equipment lines, Club Operations, Films Rights and Shipping, and the two
   Event lines) and renames the survivors -- "Repairs" becomes "Maintenance and
   Repair", "Safety" becomes "Safety and Inspections".

2. Every retired category hands its history to its successor. Transactions and
   funding-request lines are moved first and the empty row is dropped after,
   because the foreign key is PROTECT and deleting a category out from under
   real money is exactly what that protection is for. If something still points
   at it -- a table this migration does not know about -- the row is retired
   instead of deleted, so the migration cannot fail halfway through a
   production upgrade.

3. The suggestion rules are re-pointed. This is the part with teeth: without
   it, "Supplies - Office" would still be filed under Consumables by a rule
   left over from the old list while the current seed sends it to Club
   Operations, and the two would sit at the same priority arguing.

Reversing is a no-op, and says so honestly below.
"""
from importlib import import_module

from django.db import migrations
from django.db.models import ProtectedError

#: The current seed, read rather than retyped.
#:
#: Migrations are normally frozen snapshots, and copying the thirteen rows and
#: seventy-odd rules in here would be the conventional move. Reading them from
#: 0002 is better on the one thing that matters: the two files can never
#: disagree about what the list is. On a fresh database 0002 has already
#: created everything below, so this migration finds nothing to do and the
#: coupling costs nothing; on an old one it is precisely the catching-up that
#: is wanted.
_seed = import_module('finance.migrations.0002_seed_reference_data')

#: Where each retired category's history goes, and why.
#:
#: Most of these are the Treasurer's own words: Club Operations was defined as
#: "printing, marketing, recruiting, internal events, gifts, travel, office
#: supplies, etc", which absorbs five of the old rows outright, and Films Rights
#: and Shipping folds in what used to be its own Shipping line. The rest follow
#: from the new list being coarser than the old one -- two subscriptions become
#: Software and Subscriptions, and a named inspection becomes Safety and
#: Inspections, which covers it by name.
MERGED_INTO = [
    ('new_stuff', 'equipment_noncapital',
     'Where gear bought outright went. Capital purchases are now their own line and '
     'have to be picked deliberately, which is the point of splitting them.'),
    ('radio', 'equipment_noncapital', 'Radios and headsets are gear.'),
    ('booth', 'film_rights',
     'The running costs of the projection booth, which is the film operation and is '
     'now accounted for as one.'),
    ('shipping', 'film_rights', 'The new category says so in its name.'),
    ('printing', 'club_operations', 'Named in the definition of Club Operations.'),
    ('marketing', 'club_operations', 'Named in the definition of Club Operations.'),
    ('gifts', 'club_operations', 'Named in the definition of Club Operations.'),
    ('internal_events', 'club_operations', 'Named in the definition of Club Operations.'),
    ('other', 'club_operations',
     'The old catch-all. Club Operations is the new one -- running the club rather '
     'than running a show.'),
    ('spotify', 'software', 'A subscription.'),
    ('slack', 'software', 'A subscription.'),
    ('chain_motor', 'safety',
     'Safety and Inspections covers the scheduled rigging inspections by name.'),
    ('event_expense', 'event_subrental',
     'It was the row expenses got filed under when they named an event; Event - '
     'Sub-Rental is that row now, and carries the pass-through flag.'),
]


def _apply_current_list(apps):
    """
    Make the named rows match the current seed, creating any that are missing.

    The name is the one field held back when another row already answers to it.
    That only happens on an install where someone has renamed a category by
    hand into a name the new list wants for a different slug; refusing to
    rename beats crashing on a unique constraint, and leaves an obvious
    duplicate for the admin to sort out rather than a failed upgrade.
    """
    SpendCategory = apps.get_model('finance', 'SpendCategory')
    for slug, name, color, order, passthrough, description in _seed.SPEND_CATEGORIES:
        row = SpendCategory.objects.filter(slug=slug).first()
        if row is None:
            SpendCategory.objects.create(
                slug=slug, name=name, color=color, sort_order=order,
                is_event_passthrough=passthrough, description=description)
            continue
        if not SpendCategory.objects.filter(name=name).exclude(pk=row.pk).exists():
            row.name = name
        row.color = color
        row.sort_order = order
        row.is_event_passthrough = passthrough
        row.description = description
        row.is_active = True
        row.save()


def _merge_retired(apps):
    """
    Move each retired category's history onto its successor, then drop the row.

    Nothing is deleted while it still holds anything: the transactions and the
    funding-request lines are re-pointed first, and only then is the empty row
    removed -- which also takes its suggestion rules with it, since those
    cascade and every one of them is about to be replaced anyway.

    :class:`~django.db.models.ProtectedError` is raised by the delete collector
    before any SQL runs, so catching it leaves the transaction clean. It means
    something outside the two tables below still references the category, in
    which case retiring it is the honest outcome: it stops being offered for
    new records and stays readable on the old ones.
    """
    SpendCategory = apps.get_model('finance', 'SpendCategory')
    ParsedTransaction = apps.get_model('finance', 'ParsedTransaction')
    FRLineItem = apps.get_model('finance', 'FRLineItem')

    for old_slug, new_slug, _reason in MERGED_INTO:
        old = SpendCategory.objects.filter(slug=old_slug).first()
        new = SpendCategory.objects.filter(slug=new_slug).first()
        if old is None or new is None or old.pk == new.pk:
            continue
        ParsedTransaction.objects.filter(lnl_spend_category=old).update(lnl_spend_category=new)
        FRLineItem.objects.filter(lnl_spend_category=old).update(lnl_spend_category=new)
        try:
            old.delete()
        except ProtectedError:
            SpendCategory.objects.filter(pk=old.pk).update(is_active=False)


def _apply_current_rules(apps):
    """
    Re-point the suggestion table at the categories that now exist.

    A rule is identified by what it reads -- the field and the pattern -- so a
    rule matching the same thing as one in the current seed but filing it
    somewhere else is not a second opinion, it is the old list still talking.
    Those are deleted, because leaving them means two rules at the same
    priority disagreeing about where "Supplies - Office" goes and the answer
    depending on which one the queryset happens to return first.

    Rules this install added that the seed says nothing about are left alone:
    they read something the seed does not, so they are an admin edit rather
    than a contradiction.
    """
    SpendCategory = apps.get_model('finance', 'SpendCategory')
    SuggestionRule = apps.get_model('finance', 'SuggestionRule')
    categories = {row.slug: row for row in SpendCategory.objects.all()}

    for field, mode, pattern, slug, confidence, priority, notes in _seed.SUGGESTION_RULES:
        category = categories.get(slug)
        if category is None:
            continue
        SuggestionRule.objects.filter(match_field=field, pattern=pattern) \
                              .exclude(spend_category=category).delete()
        SuggestionRule.objects.get_or_create(
            match_field=field, pattern=pattern, spend_category=category,
            defaults={'match_mode': mode, 'confidence': confidence,
                      'priority': priority, 'notes': notes})


def forwards(apps, schema_editor):
    """ Apply the current list, retire what it replaces, and fix the rules. """
    _apply_current_list(apps)
    _merge_retired(apps)
    _apply_current_rules(apps)


def backwards(apps, schema_editor):
    """
    Nothing to undo.

    The merge is lossy on purpose -- once a transaction that was filed under
    "Spotify" reads Software and Subscriptions, nothing on the row records
    which of the old twenty it came from, and reversing would have to guess.
    Restoring the old list without its history would be worse than leaving the
    new one in place, so this reverses cleanly by doing nothing, the same way
    0002 declines to delete categories on the way back down.
    """


class Migration(migrations.Migration):
    """ Updates an existing install to the spend categories currently seeded. """

    dependencies = [
        ('finance', '0003_fund_source_default'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
