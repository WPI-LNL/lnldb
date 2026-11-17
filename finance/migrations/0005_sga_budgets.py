"""
SGA budgets, alongside funding requests.

A budget is a ``FundingRequest`` of another kind: the whole fiscal year, one a
year, deposited at its start rather than paid back after the spending. Every
schema change the feature needs is here, so the work lands as one migration:

* the request's ``kind``;
* on each line: the amount requested, the approved amount now able to be blank
  (pending SGA approval -- not the same as $0, a line SGA denied), and, for
  budget lines, a four-digit Request ID (``number``), a side (Event Production
  or Projection), a category from the new ``BudgetCategory`` table, and the
  undergraduates who benefited, which SGA's Budget Report Form asks for. A
  line's expected project is gone: requests and budgets don't need one, and
  no line had one when it was dropped;
* on each fund, ``draws_on`` -- whose lines spending from it has to name --
  in place of the yes/no ``requires_funding_request``.

The data step carries the yes/no across (yes is funding requests) and points
the SGA Budget fund at budgets. It runs on a new database as well, after the
seed, so the seed migration is left as it was.
"""
from decimal import Decimal

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


def carry_draws_on(apps, schema_editor):
    """ Yes becomes funding requests; SGA's budget fund draws on budgets. """
    FundSource = apps.get_model('finance', 'FundSource')
    FundSource.objects.filter(requires_funding_request=True).update(draws_on='request')
    FundSource.objects.filter(slug='sga_budget', requires_funding_request=False).update(
        draws_on='budget')


def carry_draws_on_back(apps, schema_editor):
    """ Funding requests becomes yes; a fund drawing on budgets had no yes/no of its own. """
    FundSource = apps.get_model('finance', 'FundSource')
    FundSource.objects.filter(draws_on='request').update(requires_funding_request=True)


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0004_multibill_names_and_charges_squashed_0021_encumbrance_no_date'),
    ]

    operations = [
        # -- funds: whose lines spending has to name --------------------------
        migrations.AddField(
            model_name='fundsource',
            name='draws_on',
            field=models.CharField(blank=True, choices=[('', 'Nothing'), ('request', 'Funding requests'), ('budget', 'Budgets')], default='', help_text="Money SGA grants line by line has to burn down one of those lines, or the balance silently drifts. Spending from a fund set to funding requests can't be saved without a funding request line, and spending from one set to budgets without a budget line; no other fund may name either. SGA's own payments into and out of the fund name the request or budget they're for.", max_length=16, verbose_name='Charged to lines of'),
        ),
        migrations.RunPython(carry_draws_on, carry_draws_on_back),
        migrations.RemoveField(
            model_name='fundsource',
            name='requires_funding_request',
        ),

        # -- requests and budgets ---------------------------------------------
        migrations.AddField(
            model_name='fundingrequest',
            name='kind',
            field=models.CharField(choices=[('request', 'Funding request'), ('budget', 'Budget')], db_index=True, default='request', help_text='A funding request is for one purpose and paid back after the spending; a budget covers the whole fiscal year and is deposited at its start.', max_length=16, verbose_name='Type'),
        ),
        migrations.CreateModel(
            name='BudgetCategory',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=96)),
                ('sort_order', models.PositiveIntegerField(default=0, verbose_name='Order')),
                ('funding_request', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='budget_categories', to='finance.fundingrequest')),
            ],
            options={
                'verbose_name': 'Budget Category',
                'verbose_name_plural': 'Budget Categories',
                'ordering': ('sort_order', 'name', 'pk'),
            },
        ),
        migrations.AddConstraint(
            model_name='budgetcategory',
            constraint=models.UniqueConstraint(fields=('funding_request', 'name'), name='finance_budget_category_name_unique'),
        ),

        # -- lines --------------------------------------------------------------
        migrations.AddField(
            model_name='frlineitem',
            name='amount_requested',
            field=models.DecimalField(blank=True, decimal_places=2, help_text='What LNL asked SGA for on this line.', max_digits=10, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0.00'))], verbose_name='Requested'),
        ),
        migrations.AlterField(
            model_name='frlineitem',
            name='amount_awarded',
            field=models.DecimalField(blank=True, decimal_places=2, help_text='What SGA approved. Leave blank while the line is pending SGA approval; enter 0 if SGA denied it.', max_digits=10, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0.00'))], verbose_name='Approved'),
        ),
        migrations.AddField(
            model_name='frlineitem',
            name='number',
            field=models.CharField(blank=True, help_text="A budget line's four-digit Request ID, as SGA gives it. Workday memos quote it: Velcro restock, consumables, (4521).", max_length=4, validators=[django.core.validators.RegexValidator('^\\d{4}$', "A budget line's Request ID is four digits, like 4521.")], verbose_name='Request ID'),
        ),
        migrations.AddField(
            model_name='frlineitem',
            name='is_projection',
            field=models.BooleanField(default=False, help_text="A budget line's side. A funding request's lines are on its request's side.", verbose_name='Projection'),
        ),
        migrations.AddField(
            model_name='frlineitem',
            name='category',
            field=models.ForeignKey(blank=True, help_text='The category a budget line is nested under.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='lines', to='finance.budgetcategory'),
        ),
        migrations.RemoveField(
            model_name='frlineitem',
            name='project_tag',
        ),
        migrations.AddField(
            model_name='frlineitem',
            name='undergraduates',
            field=models.PositiveIntegerField(blank=True, help_text="SGA's Budget Report Form asks for it for each line.", null=True, verbose_name='Undergraduates who benefited'),
        ),
    ]
