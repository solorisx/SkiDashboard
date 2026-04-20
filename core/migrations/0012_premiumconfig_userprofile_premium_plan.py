from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0011_userprofile_premium_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='PremiumConfig',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('monthly_price_usd', models.DecimalField(decimal_places=2, default=5.0, max_digits=6)),
                ('yearly_price_usd', models.DecimalField(decimal_places=2, default=50.0, max_digits=6)),
                ('monthly_threshold_usd', models.DecimalField(decimal_places=2, default=5.0, max_digits=6)),
                ('yearly_threshold_usd', models.DecimalField(decimal_places=2, default=50.0, max_digits=6)),
            ],
            options={
                'verbose_name': 'Premium Configuration',
            },
        ),
        migrations.AddField(
            model_name='userprofile',
            name='premium_plan',
            field=models.CharField(
                blank=True,
                choices=[('monthly', 'Monthly'), ('yearly', 'Yearly')],
                max_length=20,
                null=True,
            ),
        ),
    ]
