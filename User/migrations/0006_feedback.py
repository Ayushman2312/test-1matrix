# Generated by Django 5.1.5 on 2025-04-04 19:38

import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('User', '0005_userarticle'),
    ]

    operations = [
        migrations.CreateModel(
            name='Feedback',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=255)),
                ('number_of_stars', models.IntegerField()),
                ('message', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
    ]
