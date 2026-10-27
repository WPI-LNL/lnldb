"""
A funding request's SGA number may name Exec (E) as well as A, F and S, or carry
? where SGA's numbering left the letter out. Help text only.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0011_settle_wording'),
    ]

    operations = [
        migrations.AlterField(
            model_name='fundingrequest',
            name='reference',
            field=models.CharField(blank=True, help_text="As SGA numbers it: the body that approved it (A for Appropriations Committee, F for Financial Board, S for Senate, E for Exec), the fiscal year, and the request's number -- e.g. A.27.16. When SGA's number came with ? for the letter, enter it that way.", max_length=64, verbose_name='SGA reference #'),
        ),
    ]
