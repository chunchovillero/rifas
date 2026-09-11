from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("raffles", "0008_reservation_source")]

    operations = [
        migrations.AddField(
            model_name="raffle",
            name="terms",
            field=models.TextField(blank=True, verbose_name="bases y condiciones"),
        ),
    ]
