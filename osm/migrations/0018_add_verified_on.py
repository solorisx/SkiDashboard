# Generated manually on 2025-11-15

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('osm', '0017_alter_skiarea_daypass_price_currency_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='node',
            name='verified_on',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='way',
            name='verified_on',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='station',
            name='verified_on',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='aerialway',
            name='verified_on',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='piste',
            name='verified_on',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='skiarea',
            name='verified_on',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
