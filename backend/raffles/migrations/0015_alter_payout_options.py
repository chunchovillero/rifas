from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("raffles", "0014_payout_mercadopagopayment_payout")]

    operations = [
        migrations.AlterModelOptions(name="payout", options={"ordering": ["-settled_at"]}),
    ]
