from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("raffles", "0009_raffle_terms")]

    operations = [
        migrations.AddField(
            model_name="raffle",
            name="accent_color",
            field=models.CharField(default="#0749d9", max_length=7, verbose_name="color principal"),
        ),
    ]
