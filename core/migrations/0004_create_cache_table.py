from django.db import migrations


class Migration(migrations.Migration):

    initial = False

    dependencies = [
        ('core', '0003_strava_app'),
    ]

    operations = [
        migrations.RunSQL(
            """
            CREATE TABLE django_cache_table (
                cache_key varchar(255) NOT NULL PRIMARY KEY,
                value text NOT NULL,
                expires timestamp with time zone NOT NULL
            );
            """,
            reverse_sql="DROP TABLE IF EXISTS django_cache_table;"
        ),
        migrations.RunSQL(
            """
            CREATE INDEX django_cache_table_expires_idx ON django_cache_table (expires);
            """,
            reverse_sql="DROP INDEX IF EXISTS django_cache_table_expires_idx;"
        ),
    ]