from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("raffles", "0007_raffle_phone_required_reservation_buyer_phone")]

    operations = [
        migrations.AddField(
            model_name="reservation",
            name="source",
            field=models.CharField(
                choices=[("online", "Reserva web"), ("manual", "Venta manual")],
                default="online",
                max_length=12,
                verbose_name="origen",
            ),
        ),
    ]
