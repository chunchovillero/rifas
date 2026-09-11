import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("raffles", "0013_planpurchase")]

    operations = [
        migrations.CreateModel(name="Payout", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("gross_amount", models.PositiveIntegerField()),
            ("platform_fee", models.PositiveIntegerField()),
            ("organizer_amount", models.PositiveIntegerField()),
            ("payment_count", models.PositiveIntegerField()),
            ("settled_at", models.DateTimeField(auto_now_add=True)),
            ("raffle", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="payouts", to="raffles.raffle")),
            ("settled_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="settled_payouts", to=settings.AUTH_USER_MODEL)),
        ]),
        migrations.AddField(model_name="mercadopagopayment", name="payout", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="payments", to="raffles.payout")),
    ]
