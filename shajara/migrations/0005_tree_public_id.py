"""Give every tree an unguessable URL key so tree links stop exposing the
sequential database id (/shajara/17/ -> /shajara/hX7f.../)."""

from django.db import migrations, models

import shajara.models


def fill_public_ids(apps, schema_editor):
    Tree = apps.get_model("shajara", "Tree")
    for tree in Tree.objects.filter(public_id__isnull=True).only("id"):
        tree.public_id = shajara.models.make_tree_key()
        tree.save(update_fields=["public_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("shajara", "0004_emailotp_userprofile"),
    ]

    operations = [
        # Added nullable and non-unique first: a callable default is evaluated
        # once per AddField, so backfilling has to happen row by row.
        migrations.AddField(
            model_name="tree",
            name="public_id",
            field=models.CharField(
                max_length=22, null=True, editable=False, verbose_name="Havola kaliti"
            ),
        ),
        migrations.RunPython(fill_public_ids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="tree",
            name="public_id",
            field=models.CharField(
                max_length=22, unique=True, db_index=True, editable=False,
                default=shajara.models.make_tree_key,
                help_text="Shajara URL manzilida ishlatiladigan tasodifiy kalit",
                verbose_name="Havola kaliti",
            ),
        ),
    ]
