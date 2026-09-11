import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("raffles", "0012_mercadopagopayment")]

    operations = [migrations.CreateModel(name="PlanPurchase", fields=[
        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
        ("code", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
        ("plan", models.CharField(choices=[("pro", "Pro")], default="pro", max_length=20)),
        ("amount", models.PositiveIntegerField()),
        ("status", models.CharField(choices=[("created", "Creado"), ("pending", "Pendiente"), ("approved", "Aprobado"), ("rejected", "Rechazado")], default="created", max_length=20)),
        ("preference_id", models.CharField(blank=True, max_length=100)),
        ("payment_id", models.CharField(blank=True, max_length=100, null=True, unique=True)),
        ("payload", models.JSONField(blank=True, default=dict)),
        ("active_until", models.DateTimeField(blank=True, null=True)),
        ("created_at", models.DateTimeField(auto_now_add=True)),
        ("updated_at", models.DateTimeField(auto_now=True)),
        ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="plan_purchases", to=settings.AUTH_USER_MODEL)),
    ], options={"ordering": ["-created_at"]})]
