# Generated by Django 3.1.14 on 2022-01-15 03:06

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0006_remove_doc_models'),
    ]

    operations = [
        migrations.AlterField(
            model_name='tokenrequest',
            name='code',
            field=models.PositiveIntegerField(),
        ),
    ]
