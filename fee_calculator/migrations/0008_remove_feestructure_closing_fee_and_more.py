# Generated by Django 5.1.5 on 2025-03-08 09:36

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fee_calculator', '0007_remove_amazonprogram_description_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='feestructure',
            name='closing_fee',
        ),
        migrations.AddField(
            model_name='amazonprogram',
            name='closing_fee',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
    ]
