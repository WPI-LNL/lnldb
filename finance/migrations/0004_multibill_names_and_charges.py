"""
Multi-bills get a name, a description and a note on how they were paid, and
charges of their own: one-offs, rentals, and percentage fees or discounts.

The total stays a saved column. Nothing here recalculates it, so every
existing multi-bill keeps the figure it was sent with; its page says when the
events now come to something else, and offers to update an unpaid one.
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0019_move_bills_to_finance'),
        ('finance', '0003_bills_from_events'),
    ]

    operations = [
        migrations.AddField(
            model_name='multibilling',
            name='description',
            field=models.TextField(blank=True, help_text='Shown on the invoice under the name.'),
        ),
        migrations.AddField(
            model_name='multibilling',
            name='name',
            field=models.CharField(blank=True, help_text='What the bill is for, such as "Fall films". Shown on the invoice and in the email\'s subject.', max_length=128),
        ),
        migrations.AddField(
            model_name='multibilling',
            name='paid_note',
            field=models.CharField(blank=True, help_text='How it was paid, if not through Workday: cash, a check.', max_length=200),
        ),
        migrations.AlterField(
            model_name='multibilling',
            name='org',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='multibillings', to='events.organization', verbose_name='Bill to'),
        ),
        migrations.CreateModel(
            name='MultiBillingCharge',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('oneoff', 'One-off charge or credit'), ('rental', 'Rental'), ('percent', 'Percentage fee or discount')], default='oneoff', max_length=8)),
                ('description', models.CharField(max_length=128)),
                ('quantity', models.PositiveSmallIntegerField(default=1)),
                ('unit_price', models.DecimalField(blank=True, decimal_places=2, help_text='Negative for a credit.', max_digits=8, null=True)),
                ('rental_fee_percent', models.DecimalField(blank=True, decimal_places=2, help_text='The rental fee added to a rental, fixed when the fee was added so a later change to the default pricelist does not reprice the bill.', max_digits=5, null=True)),
                ('percent', models.DecimalField(blank=True, decimal_places=2, help_text="Of the events' total. Negative for a discount.", max_digits=5, null=True)),
                ('multibilling', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='charges', to='finance.multibilling')),
            ],
            options={
                'verbose_name': 'Multi-bill charge',
                'ordering': ('pk',),
            },
        ),
        migrations.AddConstraint(
            model_name='multibillingcharge',
            constraint=models.CheckConstraint(check=models.Q(models.Q(('kind', 'percent'), ('percent__isnull', False), ('unit_price__isnull', True)), models.Q(models.Q(('kind', 'percent'), _negated=True), ('percent__isnull', True), ('unit_price__isnull', False)), _connector='OR'), name='finance_multibill_charge_priced_by_kind'),
        ),
        migrations.AddConstraint(
            model_name='multibillingcharge',
            constraint=models.CheckConstraint(check=models.Q(('kind', 'rental'), ('rental_fee_percent__isnull', True), _connector='OR'), name='finance_multibill_charge_fee_on_rentals_only'),
        ),
    ]
