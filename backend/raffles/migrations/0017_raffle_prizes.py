from django.db import migrations, models


def copy_existing_prizes(apps, schema_editor):
    Raffle = apps.get_model("raffles", "Raffle")
    for raffle in Raffle.objects.all().iterator():
        raffle.prizes = [raffle.prize] if raffle.prize else []
        raffle.save(update_fields=["prizes"])


class Migration(migrations.Migration):
    dependencies = [("raffles", "0016_raffle_mercadopago_enabled_rafflepropurchase_and_more")]
    operations = [
        migrations.AddField(model_name="raffle", name="prizes", field=models.JSONField(blank=True, default=list, verbose_name="premios")),
        migrations.RunPython(copy_existing_prizes, migrations.RunPython.noop),
    ]
