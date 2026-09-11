from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("raffles", "0010_raffle_accent_color")]

    operations = [
        migrations.AddField(
            model_name="raffle",
            name="fundraising_goal",
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name="meta de recaudación"),
        ),
    ]
