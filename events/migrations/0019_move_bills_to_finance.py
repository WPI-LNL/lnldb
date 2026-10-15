"""
Hands the bills -- Billing, MultiBilling and the two email records -- over to
the finance app, which takes them in finance 0003_bills_from_events.

Only Django's record of which app owns them changes. No table is created,
dropped, renamed or copied: finance declares the same events_* table names
these models always had, so the rows stay exactly where they are.
"""
from django.db import migrations


STATE_OPERATIONS = [
    migrations.RemoveField(
        model_name='billingemail',
        name='billing',
    ),
    migrations.RemoveField(
        model_name='billingemail',
        name='email_to_orgs',
    ),
    migrations.RemoveField(
        model_name='billingemail',
        name='email_to_users',
    ),
    migrations.RemoveField(
        model_name='multibilling',
        name='events',
    ),
    migrations.RemoveField(
        model_name='multibilling',
        name='org',
    ),
    migrations.RemoveField(
        model_name='multibillingemail',
        name='email_to_orgs',
    ),
    migrations.RemoveField(
        model_name='multibillingemail',
        name='email_to_users',
    ),
    migrations.RemoveField(
        model_name='multibillingemail',
        name='multibilling',
    ),
    migrations.DeleteModel(
        name='Billing',
    ),
    migrations.DeleteModel(
        name='BillingEmail',
    ),
    migrations.DeleteModel(
        name='MultiBilling',
    ),
    migrations.DeleteModel(
        name='MultiBillingEmail',
    ),
]


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0017_is_sga_funded_squashed_0018_pricelist_extras'),
    ]

    operations = [
        # Django's record only: the tables are already there, under these names.
        migrations.SeparateDatabaseAndState(state_operations=STATE_OPERATIONS),
    ]
