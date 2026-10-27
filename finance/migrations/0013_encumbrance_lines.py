"""
An encumbrance can have several lines, each charged to its own fund.

The lines stay ParsedTransaction rows with no bank line, as every encumbrance
was before; the new Encumbrance row holds what they share -- the description,
the date and the quote. Every open encumbrance becomes an Encumbrance of one
line.
"""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def give_each_open_encumbrance_a_header(apps, schema_editor):
    Encumbrance = apps.get_model('finance', 'Encumbrance')
    ParsedTransaction = apps.get_model('finance', 'ParsedTransaction')
    for entry in ParsedTransaction.objects.filter(parent_transaction__isnull=True):
        header = Encumbrance.objects.create(
            description=entry.description or "(no description)",
            effective_date=entry.effective_date,
            receipt_file=entry.receipt_file.name if entry.receipt_file else None,
            created_by_id=entry.created_by_id)
        # auto_now_add stamps today; the line knows when it was really written.
        Encumbrance.objects.filter(pk=header.pk).update(created_on=entry.created_on)
        ParsedTransaction.objects.filter(pk=entry.pk).update(encumbrance=header)


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('finance', '0012_fr_reference_bodies'),
    ]

    operations = [
        migrations.CreateModel(
            name='Encumbrance',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('description', models.CharField(help_text='What the purchase is.', max_length=255)),
                ('effective_date', models.DateField(default=django.utils.timezone.localdate, help_text='Roughly when the money will go out.', verbose_name='Date')),
                ('receipt_file', models.FileField(blank=True, null=True, upload_to='finance/receipts/%Y/%m/', verbose_name='Receipt or quote')),
                ('created_on', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='encumbrances', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ('-effective_date', '-pk'),
            },
        ),
        migrations.AddField(
            model_name='parsedtransaction',
            name='encumbrance',
            field=models.ForeignKey(blank=True, help_text='The encumbrance this entry was written as a line of.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='lines', to='finance.encumbrance'),
        ),
        migrations.RunPython(give_each_open_encumbrance_a_header, migrations.RunPython.noop),
    ]
