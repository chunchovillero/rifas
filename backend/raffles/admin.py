from django.conf import settings
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group, User
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from .models import MercadoPagoPayment, Payout, PlanPurchase, Raffle, RaffleDraw, RaffleNumber, Reservation


class RifacilAdminSite(admin.AdminSite):
    site_header = "Rifácil · Administración"
    site_title = "Administración Rifácil"
    index_title = "Centro de control"
    index_template = "admin/rifacil_index.html"

    def index(self, request, extra_context=None):
        online_payments = MercadoPagoPayment.objects.filter(status="approved").select_related("reservation__raffle")
        collected = sum(payment.reservation.raffle.number_price * len(payment.reservation.number_snapshot) for payment in online_payments)
        extra_context = {**(extra_context or {}), "rifacil_stats": {
            "published_raffles": Raffle.objects.filter(status=Raffle.Status.PUBLISHED).count(),
            "active_reservations": Reservation.objects.filter(status=Reservation.Status.ACTIVE, expires_at__gt=timezone.now()).count(),
            "pending_payouts": MercadoPagoPayment.objects.filter(status="approved", payout__isnull=True).count(),
            "collected": collected,
            "recent_reservations": Reservation.objects.select_related("raffle").order_by("-created_at")[:8],
        }}
        return super().index(request, extra_context=extra_context)


rifacil_admin_site = RifacilAdminSite(name="rifacil_admin")
rifacil_admin_site.register(User, UserAdmin)
rifacil_admin_site.register(Group)


class RaffleNumberInline(admin.TabularInline):
    model = RaffleNumber
    extra = 0
    fields = ("number", "status", "buyer_name", "buyer_email")


@admin.register(Raffle, site=rifacil_admin_site)
class RaffleAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "status", "total_numbers", "number_price", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("title", "owner__username")
    readonly_fields = ("slug", "created_at", "updated_at")
    inlines = (RaffleNumberInline,)
    actions = ("publish_raffles", "close_raffles")

    @admin.action(description="Publicar rifas seleccionadas")
    def publish_raffles(self, request, queryset):
        updated = queryset.exclude(status=Raffle.Status.CLOSED).update(status=Raffle.Status.PUBLISHED)
        self.message_user(request, f"{updated} rifas publicadas.", messages.SUCCESS)

    @admin.action(description="Cerrar rifas seleccionadas")
    def close_raffles(self, request, queryset):
        updated = queryset.update(status=Raffle.Status.CLOSED)
        self.message_user(request, f"{updated} rifas cerradas.", messages.SUCCESS)


@admin.register(RaffleNumber, site=rifacil_admin_site)
class RaffleNumberAdmin(admin.ModelAdmin):
    list_display = ("raffle", "number", "status", "buyer_name")
    list_filter = ("status",)
    search_fields = ("raffle__title", "buyer_name", "buyer_email")


@admin.register(Reservation, site=rifacil_admin_site)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ("code", "raffle", "buyer_name", "source", "status", "expires_at", "created_at")
    list_filter = ("status", "source", "created_at")
    search_fields = ("code", "raffle__title", "buyer_name", "buyer_email")
    readonly_fields = ("code", "created_at")
    actions = ("confirm_reservations", "cancel_reservations")

    @admin.action(description="Confirmar reservas seleccionadas")
    def confirm_reservations(self, request, queryset):
        active = queryset.filter(status=Reservation.Status.ACTIVE)
        with transaction.atomic():
            RaffleNumber.objects.filter(reservation__in=active, status=RaffleNumber.Status.RESERVED).update(status=RaffleNumber.Status.SOLD)
            updated = active.update(status=Reservation.Status.CONFIRMED)
        self.message_user(request, f"{updated} reservas confirmadas.", messages.SUCCESS)

    @admin.action(description="Cancelar reservas seleccionadas y liberar números")
    def cancel_reservations(self, request, queryset):
        active = queryset.filter(status=Reservation.Status.ACTIVE)
        with transaction.atomic():
            RaffleNumber.objects.filter(reservation__in=active, status=RaffleNumber.Status.RESERVED).update(status=RaffleNumber.Status.AVAILABLE, buyer_name="", buyer_email="", reservation=None)
            updated = active.update(status=Reservation.Status.CANCELLED)
        self.message_user(request, f"{updated} reservas canceladas y números liberados.", messages.SUCCESS)


@admin.register(RaffleDraw, site=rifacil_admin_site)
class RaffleDrawAdmin(admin.ModelAdmin):
    list_display = ("raffle", "winning_number", "drawn_by", "drawn_at")
    readonly_fields = ("raffle", "winning_number", "drawn_by", "drawn_at")


@admin.register(MercadoPagoPayment, site=rifacil_admin_site)
class MercadoPagoPaymentAdmin(admin.ModelAdmin):
    list_display = ("payment_id", "reservation", "status", "payout", "updated_at")
    list_filter = ("status", "payout")
    search_fields = ("payment_id", "preference_id", "reservation__raffle__title", "reservation__buyer_name")
    readonly_fields = ("reservation", "preference_id", "payment_id", "status", "payload", "payout", "created_at", "updated_at")
    actions = ("register_payout",)

    @admin.action(description="Registrar liquidación para los pagos seleccionados")
    def register_payout(self, request, queryset):
        pending = queryset.filter(status="approved", payout__isnull=True).select_related("reservation__raffle")
        grouped = {}
        for payment in pending:
            grouped.setdefault(payment.reservation.raffle_id, []).append(payment)
        if not grouped:
            self.message_user(request, "Selecciona pagos aprobados que todavía no estén liquidados.", level=messages.WARNING)
            return
        with transaction.atomic():
            count = 0
            for payments in grouped.values():
                raffle = payments[0].reservation.raffle
                gross = sum(raffle.number_price * len(payment.reservation.number_snapshot) for payment in payments)
                fee = round(gross * settings.PLATFORM_COMMISSION_PERCENT / 100)
                payout = Payout.objects.create(
                    raffle=raffle, settled_by=request.user, gross_amount=gross, platform_fee=fee,
                    organizer_amount=gross - fee, payment_count=len(payments),
                )
                MercadoPagoPayment.objects.filter(pk__in=[payment.pk for payment in payments]).update(payout=payout)
                count += 1
        self.message_user(request, f"Se registraron {count} liquidaciones. Realiza la transferencia antes de ejecutar esta acción.", level=messages.SUCCESS)


@admin.register(Payout, site=rifacil_admin_site)
class PayoutAdmin(admin.ModelAdmin):
    list_display = ("id", "raffle", "organizer_amount", "platform_fee", "payment_count", "settled_by", "settled_at")
    list_filter = ("settled_at",)
    search_fields = ("raffle__title", "raffle__owner__username")
    readonly_fields = ("raffle", "settled_by", "gross_amount", "platform_fee", "organizer_amount", "payment_count", "settled_at")


@admin.register(PlanPurchase, site=rifacil_admin_site)
class PlanPurchaseAdmin(admin.ModelAdmin):
    list_display = ("user", "plan", "amount", "status", "active_until", "created_at")
    list_filter = ("plan", "status")
    search_fields = ("user__username", "user__email", "payment_id")
    readonly_fields = ("code", "user", "plan", "amount", "status", "preference_id", "payment_id", "payload", "active_until", "created_at", "updated_at")
