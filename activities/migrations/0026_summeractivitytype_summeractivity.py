# Generated migration for SummerActivityType and SummerActivity models.

import django.db.models.deletion
import djmoney.models.fields
from django.conf import settings
from django.db import migrations, models

CURRENCY_CHOICES = [
    ('GBP', 'British Pound'),
    ('CNY', 'Chinese Yuan'),
    ('EUR', 'Euro'),
    ('JPY', 'Japanese Yen'),
    ('CHF', 'Swiss Franc'),
    ('USD', 'US Dollar'),
]


class Migration(migrations.Migration):

    dependencies = [
        ('activities', '0025_activity_strava_description_updated'),
        ('cost', '0004_alter_seasonpass_price_currency_and_more'),
        ('osm', '0021_populate_piste_name'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SummerActivityType',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('natural_key', models.SlugField(help_text="Stable identifier, unique across deployments (e.g. 'mountain-biking').", max_length=120, unique=True)),
                ('icon', models.CharField(default='bi bi-bicycle', help_text='Bootstrap-icons class used in the UI.', max_length=100)),
                ('color', models.CharField(default='#2e7d32', max_length=20)),
                ('sort_order', models.PositiveIntegerField(default=100)),
                ('is_active', models.BooleanField(default=True)),
                ('created_on', models.DateTimeField(auto_now_add=True)),
                ('modified_on', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(blank=True, help_text='Owner of a custom type; NULL for built-in global types.', null=True, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['sort_order', 'name'],
            },
        ),
        migrations.AddIndex(
            model_name='summeractivitytype',
            index=models.Index(fields=['user'], name='summertype_user_idx'),
        ),
        migrations.CreateModel(
            name='SummerActivity',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('date', models.DateField(help_text='Calendar date the activity took place.')),
                ('timezone', models.CharField(blank=True, help_text='IANA timezone name (e.g., Europe/Zurich).', max_length=100, null=True)),
                ('strava_id', models.PositiveBigIntegerField(blank=True, null=True, unique=True)),
                ('strava_type', models.CharField(blank=True, help_text='Raw Strava sport_type (e.g. Run, Ride, Hike) when linked.', max_length=100, null=True)),
                ('distance', models.FloatField(blank=True, help_text='Distance in meters.', null=True)),
                ('elevation_gain', models.FloatField(blank=True, help_text='Total ascent in meters.', null=True)),
                ('duration', models.DurationField(blank=True, null=True)),
                ('cost_currency', djmoney.models.fields.CurrencyField(choices=CURRENCY_CHOICES, default='CHF', editable=False, max_length=3, null=True)),
                ('cost', djmoney.models.fields.MoneyField(blank=True, decimal_places=2, default_currency='CHF', help_text='Out-of-pocket cost paid for this activity.', max_digits=10, null=True)),
                ('value_currency', djmoney.models.fields.CurrencyField(choices=CURRENCY_CHOICES, default='CHF', editable=False, max_length=3, null=True)),
                ('value', djmoney.models.fields.MoneyField(blank=True, decimal_places=2, default_currency='CHF', help_text='Equivalent ticket value when covered by a season pass.', max_digits=10, null=True)),
                ('notes', models.TextField(blank=True)),
                ('created_on', models.DateTimeField(auto_now_add=True)),
                ('modified_on', models.DateTimeField(auto_now=True)),
                ('activity_type', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='activities', to='activities.summeractivitytype')),
                ('season_pass', models.ForeignKey(blank=True, help_text='Season pass covering this activity, if any.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='summer_activities', to='cost.seasonpass')),
                ('ski_area', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='summer_activities', to='osm.skiarea')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='summer_activities', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'summer activity',
                'verbose_name_plural': 'summer activities',
                'ordering': ['-date'],
            },
        ),
        migrations.AddIndex(
            model_name='summeractivity',
            index=models.Index(fields=['user', '-date'], name='summeract_user_date_idx'),
        ),
        migrations.AddIndex(
            model_name='summeractivity',
            index=models.Index(fields=['season_pass'], name='summeract_seasonpass_idx'),
        ),
    ]
