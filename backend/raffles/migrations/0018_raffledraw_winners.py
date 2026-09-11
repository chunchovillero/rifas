from django.db import migrations, models


def copy_existing_winner(apps, schema_editor):
    Draw = apps.get_model("raffles", "RaffleDraw")
    for draw in Draw.objects.select_related("winning_number", "raffle").all():
        number = draw.winning_number
        prizes = draw.raffle.prizes or [draw.raffle.prize]
        draw.winners = [{"position": 1, "prize": prizes[0], "number": number.number, "buyer_name": number.buyer_name}]
        draw.save(update_fields=["winners"])


class Migration(migrations.Migration):
    dependencies = [("raffles", "0017_raffle_prizes")]
    operations = [
        migrations.AddField(model_name="raffledraw", name="winners", field=models.JSONField(blank=True, default=list, verbose_name="ganadores")),
        migrations.RunPython(copy_existing_winner, migrations.RunPython.noop),
    ]
