# Generated by Django 5.1.5 on 2025-04-24 12:19

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('website', '0005_cleanup_duplicate_websites'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='website',
            constraint=models.UniqueConstraint(fields=('user',), name='one_website_per_user'),
        ),
    ]
