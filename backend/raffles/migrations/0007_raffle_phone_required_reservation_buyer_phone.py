from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("raffles", "0006_reservation_number_snapshot")]

    operations = [
        migrations.AddField(
            model_name="raffle",
            name="phone_required",
            field=models.BooleanField(default=False, verbose_name="teléfono obligatorio"),
        ),
        migrations.AddField(
            model_name="reservation",
            name="buyer_phone",
            field=models.CharField(blank=True, max_length=30, verbose_name="teléfono"),
        ),
    ]
