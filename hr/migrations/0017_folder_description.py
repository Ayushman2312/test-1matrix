# Generated by Django 5.1.5 on 2025-04-13 12:01

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hr', '0016_folder_handbook_hiringagreement_trainingmaterial'),
    ]

    operations = [
        migrations.AddField(
            model_name='folder',
            name='description',
            field=models.TextField(blank=True, null=True),
        ),
    ]
