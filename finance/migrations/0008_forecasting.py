"""
What the forecast needs: a minimum reserve, the departments' share of past
billing, planned purchases, corrections to old lines -- and the books start
written down before any history is imported.

Left blank, the books start at the beginning of the fiscal year of the
earliest imported line. Importing FY19's export so the forecast can learn from
it would then move the books back six years and put six years of lines in the
queue. Writing today's answer down first keeps the books where they are, and
every older line becomes history.

The two equipment categories are spending chosen one purchase at a time, so
the forecast counts them from planned purchases rather than from a typical
year.
"""
import datetime
from decimal import Decimal
from django.conf import settings
import django.core.validators
from django.db import migrations, models
import django.db.models.deletion


#: The seeded equipment categories, by slug. A category added later is
#: flagged in the admin.
EQUIPMENT_SLUGS = ('equipment_capital', 'equipment_noncapital')


def pin_books_start(apps, schema_editor):
    """ Write down where the books start now, if nobody has. """
    FinanceSettings = apps.get_model('finance', 'FinanceSettings')
    WorkdayTransaction = apps.get_model('finance', 'WorkdayTransaction')
    config = FinanceSettings.objects.filter(pk=1).first()
    if config is not None and config.ledger_start_date:
        return
    earliest = (WorkdayTransaction.objects.order_by('accounting_date')
                .values_list('accounting_date', flat=True).first())
    if earliest is None:
        # Nothing imported: the first import decides, as it always has.
        return
    month = config.fiscal_year_start_month if config is not None else 7
    year = earliest.year if earliest.month >= month else earliest.year - 1
    FinanceSettings.objects.update_or_create(
        pk=1, defaults={'ledger_start_date': datetime.date(year, month, 1)})


def flag_equipment(apps, schema_editor):
    """ Forecast the equipment categories from plans, not from a typical year. """
    SpendCategory = apps.get_model('finance', 'SpendCategory')
    SpendCategory.objects.filter(slug__in=EQUIPMENT_SLUGS).update(forecast_from_plans=True)


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('finance', '0007_sga_budget_source_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='financesettings',
            name='department_billing_share',
            field=models.PositiveSmallIntegerField(blank=True, help_text='Until FY27 LNL billed student organizations as well as departments, and now it bills departments only. The forecast takes this share of past billing as what departments alone bring in. Leave blank to work it out from billing filed against events; until enough is, the forecast leaves past billing out.', null=True, validators=[django.core.validators.MaxValueValidator(100)], verbose_name="Departments' share of billing before FY27 (%)"),
        ),
        migrations.AddField(
            model_name='financesettings',
            name='minimum_reserve',
            field=models.DecimalField(decimal_places=2, default=Decimal('10000.00'), help_text='The least LNL\'s own money should ever hold. The forecast marks any month projected below it, and "Can we afford it?" answers against it.', max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal('0.00'))], verbose_name='Minimum reserve'),
        ),
        migrations.AddField(
            model_name='spendcategory',
            name='forecast_from_plans',
            field=models.BooleanField(default=False, help_text='For spending chosen one purchase at a time, like equipment. The forecast leaves it out of a typical year and counts only what is reserved or on the planned purchases list, so one big purchase is not expected again every year.', verbose_name='Forecast from plans only'),
        ),
        migrations.AlterField(
            model_name='financesettings',
            name='ledger_start_date',
            field=models.DateField(blank=True, help_text='The first day the subledger accounts for every line. Fund balances are worked out from here: whatever each account held the night before is its opening, and every line on or after it counts. Leave blank to start at the beginning of the fiscal year of the earliest imported line. Lines from before it are history: kept for the forecast, never filed.', null=True, verbose_name='Books start on'),
        ),
        migrations.CreateModel(
            name='PlannedPurchase',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=128)),
                ('amount', models.DecimalField(decimal_places=2, help_text='What it will cost, as a positive figure.', max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))])),
                ('expected_date', models.DateField(help_text='Roughly when the money will go out.', verbose_name='Expected on')),
                ('status', models.CharField(choices=[('planned', 'Planned'), ('approved', 'Approved'), ('bought', 'Bought or reserved'), ('dropped', 'Dropped')], default='planned', max_length=12)),
                ('notes', models.TextField(blank=True)),
                ('created_on', models.DateTimeField(auto_now_add=True)),
                ('updated_on', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='finance_planned_purchases', to=settings.AUTH_USER_MODEL)),
                ('fund_source', models.ForeignKey(help_text='Money from a funding request comes back from SGA after it is spent, so the forecast shows only the wait for it.', on_delete=django.db.models.deletion.PROTECT, related_name='planned_purchases', to='finance.fundsource', verbose_name='Paid from')),
                ('spend_category', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='planned_purchases', to='finance.spendcategory')),
            ],
            options={
                'verbose_name': 'Planned Purchase',
                'ordering': ('expected_date', 'pk'),
            },
        ),
        migrations.CreateModel(
            name='HistoryOverride',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(blank=True, choices=[('billing', 'Client billing'), ('sga', 'SGA funding'), ('spending', 'Spending'), ('other', 'Other: transfers and gifts')], help_text='Leave blank to keep what the line itself says.', max_length=16, verbose_name='What it was')),
                ('leave_out', models.BooleanField(default=False, help_text='A one-off -- a conversion entry, a purchase that will not recur -- that a typical year should not include.', verbose_name='Leave out of the forecast')),
                ('note', models.CharField(blank=True, max_length=255)),
                ('updated_on', models.DateTimeField(auto_now=True)),
                ('line', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='history_override', to='finance.workdaytransaction')),
                ('spend_category', models.ForeignKey(blank=True, help_text='For spending. Leave blank to keep the estimate.', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='history_overrides', to='finance.spendcategory')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='finance_history_overrides', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'History Correction',
            },
        ),
        migrations.AddConstraint(
            model_name='plannedpurchase',
            constraint=models.CheckConstraint(check=models.Q(('amount__gt', 0)), name='finance_planned_purchase_amount_positive'),
        ),
        # Neither is undone: the date is the books' own, and the flag goes with
        # its column.
        migrations.RunPython(pin_books_start, migrations.RunPython.noop),
        migrations.RunPython(flag_equipment, migrations.RunPython.noop),
    ]
