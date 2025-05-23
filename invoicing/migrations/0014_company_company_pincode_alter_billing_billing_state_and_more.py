# Generated by Django 5.1.5 on 2025-04-12 12:02

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('invoicing', '0013_billing_billing_pincode'),
    ]

    operations = [
        migrations.AddField(
            model_name='company',
            name='company_pincode',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='billing',
            name='billing_state',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='company',
            name='company_state',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
