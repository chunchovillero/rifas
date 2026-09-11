import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("raffles", "0015_alter_payout_options")]
    operations = [
        migrations.AddField(model_name="raffle", name="mercadopago_enabled", field=models.BooleanField(default=False, verbose_name="pagos con Mercado Pago")),
        migrations.AddField(model_name="payout", name="mercadopago_fee", field=models.PositiveIntegerField(default=0)),
        migrations.CreateModel(name="RaffleProPurchase", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("code", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
            ("amount", models.PositiveIntegerField()),
            ("preference_id", models.CharField(blank=True, max_length=100)),
            ("payment_id", models.CharField(blank=True, max_length=100, null=True, unique=True)),
            ("status", models.CharField(default="created", max_length=30)),
            ("payload", models.JSONField(blank=True, default=dict)),
            ("activated_at", models.DateTimeField(blank=True, null=True)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("updated_at", models.DateTimeField(auto_now=True)),
            ("raffle", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="pro_purchase", to="raffles.raffle")),
            ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="raffle_pro_purchases", to=settings.AUTH_USER_MODEL)),
        ]),
    ]
