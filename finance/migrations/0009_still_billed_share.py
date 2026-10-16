"""
The forecast's share of past billing, re-asked under the SGA-funded rule.

The old setting was the departments' share of billing before FY27, on the
understanding that from FY27 only departments were billed. In fact an
SGA-funded show is charged its rentals and one-off charges, and any other show
in full, whoever the client is. So the question is now what share of past
billing the same shows would still be charged. A figure given for the old
question does not answer the new one, so it is dropped, not carried over; the
new setting starts blank, and is measured from FY27's shows until it is set.
"""
import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0008_billing_digest_limits'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='financesettings',
            name='department_billing_share',
        ),
        migrations.AddField(
            model_name='financesettings',
            name='still_billed_share',
            field=models.PositiveSmallIntegerField(blank=True, help_text='From FY27 an SGA-funded show is charged only for its rentals and one-off charges; until then every show was charged in full. The forecast takes this share of past billing as what the same shows would bring in now. Leave blank to work it out from the shows run since FY27 began; until enough have run, the forecast leaves past billing out.', null=True, validators=[django.core.validators.MaxValueValidator(100)], verbose_name='Share of pre-FY27 billing still charged (%)'),
        ),
    ]
