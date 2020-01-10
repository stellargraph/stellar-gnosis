# Generated by Django 2.2.5 on 2020-01-10 00:15

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('catalog', '__first__'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Bookmark',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('updated_at', models.DateField(null=True)),
                ('created_at', models.DateField(auto_now_add=True)),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='bookmarks', to=settings.AUTH_USER_MODEL)),
                ('paper', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='bookmarks', to='catalog.Paper')),
            ],
            options={
                'ordering': ['created_at'],
            },
        ),
    ]
