# Generated by Django 5.1.5 on 2025-04-04 19:45

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('User', '0006_feedback'),
    ]

    operations = [
        migrations.RenameField(
            model_name='feedback',
            old_name='number_of_stars',
            new_name='rating',
        ),
    ]
