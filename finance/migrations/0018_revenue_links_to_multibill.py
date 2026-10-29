"""
A payment for a multi-bill can link to the bill itself.

Until now a payment that settled several shows at once had to be split into
one entry per show. ``linked_multibill`` lets it stay one entry, and each show
is credited with its share by price. It is revenue only, and an entry naming a
multi-bill names no event and no non-event source.
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0017_remove_project_code'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='parsedtransaction',
            name='finance_no_revenue_routing_on_expense',
        ),
        migrations.AddField(
            model_name='parsedtransaction',
            name='linked_multibill',
            field=models.ForeignKey(blank=True, help_text='A payment for a multi-bill. Each of its events is credited with its share, by price, as the bill is split.', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='subledger_entries', to='finance.multibilling', verbose_name='Linked multi-bill'),
        ),
        migrations.AddConstraint(
            model_name='parsedtransaction',
            constraint=models.CheckConstraint(check=models.Q(models.Q(('amount__gt', 0), ('refund_of__isnull', True)), models.Q(('linked_multibill__isnull', True), ('non_event_revenue_type__isnull', True)), _connector='OR'), name='finance_no_revenue_routing_on_expense'),
        ),
        migrations.AddConstraint(
            model_name='parsedtransaction',
            constraint=models.CheckConstraint(check=models.Q(('linked_multibill__isnull', True), models.Q(('linked_event__isnull', True), ('non_event_revenue_type__isnull', True)), _connector='OR'), name='finance_multibill_payment_names_only_the_bill'),
        ),
    ]
