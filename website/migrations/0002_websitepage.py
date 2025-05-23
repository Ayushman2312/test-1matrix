# Generated by Django 5.1.5 on 2025-04-17 13:48

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('website', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='WebsitePage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=100)),
                ('slug', models.SlugField(max_length=100)),
                ('template_file', models.CharField(help_text='HTML template file name', max_length=255)),
                ('content', models.JSONField(default=dict, help_text='Page-specific content')),
                ('is_homepage', models.BooleanField(default=False)),
                ('order', models.IntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('website', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pages', to='website.website')),
            ],
            options={
                'ordering': ['order', 'title'],
                'unique_together': {('website', 'slug')},
            },
        ),
    ]
