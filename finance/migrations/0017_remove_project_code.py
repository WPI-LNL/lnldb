"""
Projects no longer have a code.

The code was only ever looked for in Workday memos to suggest a project, and
that suggestion is gone. A project is known by its name everywhere.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0016_revenue_sources_and_category_names'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='projecttag',
            name='code',
        ),
    ]
