from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("raffles", "0011_raffle_fundraising_goal")]
    operations = [migrations.CreateModel(name="MercadoPagoPayment", fields=[
        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
        ("preference_id", models.CharField(blank=True, max_length=100)),
        ("payment_id", models.CharField(blank=True, max_length=100, null=True, unique=True)),
        ("status", models.CharField(default="created", max_length=30)),
        ("payload", models.JSONField(blank=True, default=dict)),
        ("created_at", models.DateTimeField(auto_now_add=True)),
        ("updated_at", models.DateTimeField(auto_now=True)),
        ("reservation", models.OneToOneField(on_delete=models.deletion.CASCADE, related_name="mercadopago_payment", to="raffles.reservation")),
    ])]
