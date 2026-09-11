from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils.text import slugify
import uuid


class Raffle(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Borrador"
        PUBLISHED = "published", "Publicada"
        CLOSED = "closed", "Cerrada"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="raffles",
        verbose_name="organizador",
    )
    title = models.CharField("título", max_length=150)
    slug = models.SlugField(max_length=180, unique=True, editable=False)
    description = models.TextField("descripción")
    terms = models.TextField("bases y condiciones", blank=True)
    accent_color = models.CharField("color principal", max_length=7, default="#0749d9")
    prize = models.CharField("premio", max_length=200)
    prizes = models.JSONField("premios", default=list, blank=True)
    cover_image = models.FileField("imagen de portada", upload_to="raffle-covers/%Y/%m/", blank=True)
    total_numbers = models.PositiveIntegerField(
        "cantidad de números", validators=[MinValueValidator(2)]
    )
    number_price = models.PositiveIntegerField(
        "precio por número", validators=[MinValueValidator(1)]
    )
    fundraising_goal = models.PositiveIntegerField("meta de recaudación", blank=True, null=True)
    draw_date = models.DateTimeField("fecha del sorteo", blank=True, null=True)
    bank_name = models.CharField("banco", max_length=100, blank=True)
    account_type = models.CharField("tipo de cuenta", max_length=100, blank=True)
    account_number = models.CharField("número de cuenta", max_length=100, blank=True)
    account_holder = models.CharField("titular", max_length=150, blank=True)
    account_holder_id = models.CharField("RUT del titular", max_length=20, blank=True)
    transfer_email = models.EmailField("correo para transferencias", blank=True)
    phone_required = models.BooleanField("teléfono obligatorio", default=False)
    mercadopago_enabled = models.BooleanField("pagos con Mercado Pago", default=False)
    status = models.CharField(
        "estado", max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "rifa"
        verbose_name_plural = "rifas"

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title)[:150] or "rifa"
            candidate = base
            suffix = 2
            while Raffle.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
                candidate = f"{base}-{suffix}"
                suffix += 1
            self.slug = candidate
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("raffles:detail", kwargs={"slug": self.slug})


class RaffleNumber(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "available", "Disponible"
        RESERVED = "reserved", "Reservado"
        PENDING = "pending", "Pago pendiente"
        SOLD = "sold", "Vendido"

    raffle = models.ForeignKey(Raffle, on_delete=models.CASCADE, related_name="numbers")
    number = models.PositiveIntegerField("número")
    status = models.CharField(
        "estado", max_length=20, choices=Status.choices, default=Status.AVAILABLE
    )
    buyer_name = models.CharField("comprador", max_length=150, blank=True)
    buyer_email = models.EmailField("correo del comprador", blank=True)
    reservation = models.ForeignKey(
        "Reservation",
        on_delete=models.SET_NULL,
        related_name="numbers",
        blank=True,
        null=True,
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["number"]
        constraints = [
            models.UniqueConstraint(
                fields=["raffle", "number"], name="unique_number_per_raffle"
            )
        ]
        verbose_name = "número de rifa"
        verbose_name_plural = "números de rifa"

    def __str__(self):
        return f"{self.raffle}: {self.number}"


class Reservation(models.Model):
    class Source(models.TextChoices):
        ONLINE = "online", "Reserva web"
        MANUAL = "manual", "Venta manual"

    class Status(models.TextChoices):
        ACTIVE = "active", "Activa"
        CONFIRMED = "confirmed", "Confirmada"
        EXPIRED = "expired", "Vencida"
        CANCELLED = "cancelled", "Cancelada"

    code = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    raffle = models.ForeignKey(Raffle, on_delete=models.CASCADE, related_name="reservations")
    buyer_name = models.CharField("nombre", max_length=150)
    buyer_email = models.EmailField("correo electrónico")
    buyer_phone = models.CharField("teléfono", max_length=30, blank=True)
    source = models.CharField("origen", max_length=12, choices=Source.choices, default=Source.ONLINE)
    number_snapshot = models.JSONField("números reservados", default=list)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    expires_at = models.DateTimeField("vence el")
    payment_receipt = models.FileField("comprobante", upload_to="receipts/%Y/%m/", blank=True)
    receipt_uploaded_at = models.DateTimeField("comprobante recibido", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "reserva"
        verbose_name_plural = "reservas"

    def __str__(self):
        return f"Reserva {self.code} - {self.raffle}"


class RaffleDraw(models.Model):
    raffle = models.OneToOneField(Raffle, on_delete=models.CASCADE, related_name="draw")
    winning_number = models.ForeignKey(
        RaffleNumber,
        on_delete=models.PROTECT,
        related_name="winning_draws",
        verbose_name="número ganador",
    )
    drawn_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    winners = models.JSONField("ganadores", default=list, blank=True)
    drawn_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "sorteo"
        verbose_name_plural = "sorteos"

    def __str__(self):
        return f"{self.raffle}: número {self.winning_number.number}"


class MercadoPagoPayment(models.Model):
    reservation = models.OneToOneField(Reservation, on_delete=models.CASCADE, related_name="mercadopago_payment")
    payout = models.ForeignKey("Payout", on_delete=models.SET_NULL, related_name="payments", blank=True, null=True)
    preference_id = models.CharField(max_length=100, blank=True)
    payment_id = models.CharField(max_length=100, blank=True, null=True, unique=True)
    status = models.CharField(max_length=30, default="created")
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class PlanPurchase(models.Model):
    class Plan(models.TextChoices):
        PRO = "pro", "Pro"

    class Status(models.TextChoices):
        CREATED = "created", "Creado"
        PENDING = "pending", "Pendiente"
        APPROVED = "approved", "Aprobado"
        REJECTED = "rejected", "Rechazado"

    code = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="plan_purchases")
    plan = models.CharField(max_length=20, choices=Plan.choices, default=Plan.PRO)
    amount = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.CREATED)
    preference_id = models.CharField(max_length=100, blank=True)
    payment_id = models.CharField(max_length=100, blank=True, null=True, unique=True)
    payload = models.JSONField(default=dict, blank=True)
    active_until = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]


class RaffleProPurchase(models.Model):
    raffle = models.OneToOneField(Raffle, on_delete=models.CASCADE, related_name="pro_purchase")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="raffle_pro_purchases")
    code = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    amount = models.PositiveIntegerField()
    preference_id = models.CharField(max_length=100, blank=True)
    payment_id = models.CharField(max_length=100, blank=True, null=True, unique=True)
    status = models.CharField(max_length=30, default="created")
    payload = models.JSONField(default=dict, blank=True)
    activated_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Payout(models.Model):
    raffle = models.ForeignKey(Raffle, on_delete=models.PROTECT, related_name="payouts")
    settled_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="settled_payouts")
    gross_amount = models.PositiveIntegerField()
    mercadopago_fee = models.PositiveIntegerField(default=0)
    platform_fee = models.PositiveIntegerField()
    organizer_amount = models.PositiveIntegerField()
    payment_count = models.PositiveIntegerField()
    settled_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-settled_at"]
