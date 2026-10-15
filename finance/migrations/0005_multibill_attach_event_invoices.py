"""
A multi-bill can say to follow its invoice with each event's own invoice.

It starts off for every existing bill, so none of them begins sending the
events' invoices without being asked to.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0004_multibill_names_and_charges'),
    ]

    operations = [
        migrations.AddField(
            model_name='multibilling',
            name='attach_event_invoices',
            field=models.BooleanField(default=False, help_text="Follow the bill's invoice with each event's own itemized invoice. The download and every email get the same document.", verbose_name="Add each event's invoice"),
        ),
    ]
