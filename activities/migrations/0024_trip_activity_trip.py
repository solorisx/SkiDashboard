# Generated migration for Trip model and Activity.trip FK

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('activities', '0023_add_activity_indices'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Trip',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('auto_name', models.CharField(blank=True, max_length=200)),
                ('name_modified', models.BooleanField(default=False, help_text='True if user has manually changed the name')),
                ('start_date', models.DateField()),
                ('end_date', models.DateField()),
                ('created_on', models.DateTimeField(auto_now_add=True)),
                ('modified_on', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-start_date'],
            },
        ),
        migrations.AddIndex(
            model_name='trip',
            index=models.Index(fields=['user', '-start_date'], name='trip_user_start_date_idx'),
        ),
        migrations.AddField(
            model_name='activity',
            name='trip',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='activities',
                to='activities.trip',
            ),
        ),
    ]
