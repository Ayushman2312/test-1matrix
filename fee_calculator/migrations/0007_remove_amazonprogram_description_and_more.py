# Generated by Django 5.1.5 on 2025-03-08 09:35

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fee_calculator', '0006_feestructure_value'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='amazonprogram',
            name='description',
        ),
        migrations.AlterUniqueTogether(
            name='feestructure',
            unique_together={('category', 'subcategory')},
        ),
        migrations.AddField(
            model_name='amazonprogram',
            name='fee_type',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='amazonprogram',
            name='fee_value',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.RemoveField(
            model_name='feestructure',
            name='fee_type',
        ),
        migrations.RemoveField(
            model_name='feestructure',
            name='program',
        ),
    ]
