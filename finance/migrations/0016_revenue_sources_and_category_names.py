"""
A shorter list of non-event income, and two spend categories reworded.

Brings a database that already ran ``0002_seed_reference_data`` up to the list
that file now seeds. Besides SGA's three kinds of payment, non-event income is
Donations, Asset Liquidation, Cash Sale and Deposits, or Other. *Alumni /
Donation* becomes *Donations*, its slug changing with it, and the two new rows
are added. *Films Rights and Shipping* is now *Films Expenses*, and *Event -
Other* says it is for costs billed to an event.

Rows are found by slug, so a database seeded with these already is left as it
is.
"""
from django.db import migrations

REVENUE_SOURCES = [
    # (slug, name, sort order)
    ('donations', 'Donations', 3),
    ('asset_liquidation', 'Asset Liquidation', 4),
    ('cash_deposits', 'Cash Sale and Deposits', 5),
    ('other', 'Other', 6),
]


def forwards(apps, schema_editor):
    RevenueSource = apps.get_model('finance', 'RevenueSource')
    SpendCategory = apps.get_model('finance', 'SpendCategory')

    if not RevenueSource.objects.filter(slug='donations').exists():
        RevenueSource.objects.filter(slug='alumni').update(slug='donations')
    for slug, name, order in REVENUE_SOURCES:
        source, created = RevenueSource.objects.get_or_create(
            slug=slug, defaults={'name': name, 'sort_order': order})
        if not created:
            source.name = name
            source.sort_order = order
            source.save(update_fields=['name', 'sort_order'])

    SpendCategory.objects.filter(slug='film_rights').update(name='Films Expenses')
    SpendCategory.objects.filter(slug='event_other').update(
        description='Use for costs billed to an event.')


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0015_remove_books_start_setting'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
