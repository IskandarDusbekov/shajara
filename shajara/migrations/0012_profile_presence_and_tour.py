from django.db import migrations, models


def mark_existing_accounts_toured(apps, schema_editor):
    """The first-run tour is for new accounts; people already using the site skip it."""
    apps.get_model("shajara", "UserProfile").objects.update(tour_done=True)


class Migration(migrations.Migration):

    dependencies = [
        ("shajara", "0011_historical_maps"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="last_seen",
            field=models.DateTimeField(blank=True, db_index=True, null=True, verbose_name="Oxirgi faollik"),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="tour_done",
            field=models.BooleanField(default=False, verbose_name="Tanishuv qo'llanmasi ko'rilgan"),
        ),
        migrations.RunPython(mark_existing_accounts_toured, migrations.RunPython.noop),
    ]
