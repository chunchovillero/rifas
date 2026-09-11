from datetime import timedelta
import json
import urllib.error
import urllib.request
import secrets

from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.http import FileResponse
from django.utils import timezone
from django.urls import reverse
from rest_framework import generics, permissions, status
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser
from rest_framework.views import APIView

from raffles.models import MercadoPagoPayment, Payout, PlanPurchase, Raffle, RaffleDraw, RaffleNumber, RaffleProPurchase, Reservation
from raffles.services import release_expired_reservations
from raffles.tasks import (
    send_receipt_uploaded_email,
    send_reservation_created_email,
    send_reservation_owner_email,
    send_reservation_status_email,
    send_winner_email,
)
from .serializers import (
    AdminRaffleNumberSerializer, BuyerReservationSerializer, CoverUploadSerializer, ManualSaleSerializer, RaffleSerializer, RegisterSerializer, ReservationRequestSerializer,
    ReservationSerializer, ReceiptUploadSerializer, UserSerializer,
)


class MercadoPagoError(Exception):
    pass


def mercadopago_request(path, method="GET", body=None):
    if not settings.MERCADOPAGO_ACCESS_TOKEN:
        raise RuntimeError("Mercado Pago no está configurado.")
    data=json.dumps(body).encode() if body is not None else None
    request=urllib.request.Request(f"https://api.mercadopago.com{path}", data=data, method=method)
    request.add_header("Authorization", f"Bearer {settings.MERCADOPAGO_ACCESS_TOKEN}")
    request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        try:
            detail = json.loads(error.read().decode()).get("message", "")
        except (json.JSONDecodeError, UnicodeDecodeError):
            detail = ""
        raise MercadoPagoError(detail or f"Mercado Pago respondió HTTP {error.code}") from error


def user_has_active_pro(user):
    return PlanPurchase.objects.filter(
        user=user,
        status=PlanPurchase.Status.APPROVED,
        active_until__gt=timezone.now(),
    ).exists()


def raffle_has_paid_access(raffle):
    return user_has_active_pro(raffle.owner) or getattr(getattr(raffle, "pro_purchase", None), "status", "") == "approved"


def free_raffle_limit_exceeded(raffle, extra_numbers=0):
    if raffle_has_paid_access(raffle):
        return False
    occupied = raffle.numbers.filter(
        status__in=[RaffleNumber.Status.RESERVED, RaffleNumber.Status.SOLD]
    ).count()
    return occupied + extra_numbers > settings.FREE_RAFFLE_SALE_LIMIT


def payment_amounts(payment):
    gross = payment.reservation.raffle.number_price * len(payment.reservation.number_snapshot)
    net = payment.payload.get("transaction_details", {}).get("net_received_amount")
    try:
        net = int(round(float(net)))
    except (TypeError, ValueError):
        net = gross
    return gross, max(0, gross - net), net


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        user = authenticate(username=request.data.get("username"), password=request.data.get("password"))
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key, "user": UserSerializer(user).data}, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        user = authenticate(username=request.data.get("username"), password=request.data.get("password"))
        if not user:
            return Response({"detail": "Credenciales incorrectas."}, status=status.HTTP_400_BAD_REQUEST)
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key, "user": UserSerializer(user).data})


class LogoutView(APIView):
    def post(self, request):
        request.auth.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    def get(self, request):
        return Response(UserSerializer(request.user).data)


class AdminDashboardView(APIView):
    def get(self, request):
        if not request.user.is_staff:
            return Response({"detail": "No tienes acceso a administración."}, status=status.HTTP_403_FORBIDDEN)
        payments = MercadoPagoPayment.objects.filter(status="approved").select_related("reservation__raffle")
        collected = sum(payment.reservation.raffle.number_price * len(payment.reservation.number_snapshot) for payment in payments)
        recent = Reservation.objects.select_related("raffle").order_by("-created_at")[:8]
        return Response({
            "stats": {
                "users": User.objects.count(),
                "published_raffles": Raffle.objects.filter(status=Raffle.Status.PUBLISHED).count(),
                "active_reservations": Reservation.objects.filter(status=Reservation.Status.ACTIVE, expires_at__gt=timezone.now()).count(),
                "pending_payouts": MercadoPagoPayment.objects.filter(status="approved", payout__isnull=True).count(),
                "collected": collected,
            },
            "recent_reservations": [{
                "code": str(reservation.code), "raffle_title": reservation.raffle.title,
                "buyer_name": reservation.buyer_name, "status": reservation.status,
                "total": reservation.raffle.number_price * len(reservation.number_snapshot),
                "created_at": reservation.created_at,
            } for reservation in recent],
        })


def admin_only(request):
    if request.user.is_staff:
        return None
    return Response({"detail": "No tienes acceso a administración."}, status=status.HTTP_403_FORBIDDEN)


class AdminRaffleListView(generics.ListAPIView):
    serializer_class = RaffleSerializer

    def get_queryset(self):
        return Raffle.objects.select_related("owner").prefetch_related("numbers")

    def list(self, request, *args, **kwargs):
        denied = admin_only(request)
        return denied or super().list(request, *args, **kwargs)


class AdminRaffleDetailView(APIView):
    def get(self, request, slug):
        denied = admin_only(request)
        if denied:
            return denied
        raffle = get_object_or_404(Raffle.objects.select_related("owner").prefetch_related("numbers__reservation__mercadopago_payment"), slug=slug)
        pending = MercadoPagoPayment.objects.filter(reservation__raffle=raffle, status="approved", payout__isnull=True).select_related("reservation")
        pending_amount = sum(raffle.number_price * len(payment.reservation.number_snapshot) for payment in pending)
        data = RaffleSerializer(raffle, context={"request": request}).data
        data["pending_payout_count"] = pending.count()
        data["pending_payout_amount"] = pending_amount
        data["commission_percent"] = settings.PLATFORM_COMMISSION_PERCENT
        breakdown = {"mercadopago": [], "transfer": [], "manual": []}
        for number in raffle.numbers.filter(status=RaffleNumber.Status.SOLD):
            reservation = number.reservation
            if reservation and getattr(reservation, "mercadopago_payment", None) and reservation.mercadopago_payment.status == "approved":
                breakdown["mercadopago"].append(number.number)
            elif reservation and reservation.source == Reservation.Source.MANUAL:
                breakdown["manual"].append(number.number)
            else:
                breakdown["transfer"].append(number.number)
        data["sales_breakdown"] = {
            key: {"numbers": numbers, "count": len(numbers), "amount": len(numbers) * raffle.number_price}
            for key, numbers in breakdown.items()
        }
        data["numbers"] = [{
            "id": number.id, "number": number.number, "status": number.status,
            "buyer_name": number.buyer_name, "buyer_email": number.buyer_email,
            "buyer_phone": number.reservation.buyer_phone if number.reservation else "",
            "payment_method": "mercadopago" if number.reservation and getattr(number.reservation, "mercadopago_payment", None) and number.reservation.mercadopago_payment.status == "approved" else ("manual" if number.reservation and number.reservation.source == Reservation.Source.MANUAL else ("transfer" if number.status == RaffleNumber.Status.SOLD else "")),
            "reservation_status": number.reservation.status if number.reservation else "",
            "payout_id": getattr(getattr(number.reservation, "mercadopago_payment", None), "payout_id", None) if number.reservation else None,
        } for number in raffle.numbers.all()]
        return Response(data)


class AdminReservationListView(generics.ListAPIView):
    serializer_class = ReservationSerializer

    def get_queryset(self):
        return Reservation.objects.select_related("raffle").prefetch_related("numbers")

    def list(self, request, *args, **kwargs):
        denied = admin_only(request)
        return denied or super().list(request, *args, **kwargs)


class AdminPaymentListView(APIView):
    def get(self, request):
        denied = admin_only(request)
        if denied:
            return denied
        payments = MercadoPagoPayment.objects.select_related("reservation__raffle", "payout").order_by("-updated_at")[:100]
        return Response([{
            "id": payment.id, "payment_id": payment.payment_id, "status": payment.status,
            "raffle_title": payment.reservation.raffle.title, "raffle_slug": payment.reservation.raffle.slug,
            "buyer_name": payment.reservation.buyer_name, "number_count": len(payment.reservation.number_snapshot),
            "amount": payment.reservation.raffle.number_price * len(payment.reservation.number_snapshot),
            "payout_id": payment.payout_id, "updated_at": payment.updated_at,
        } for payment in payments])


class AdminPayoutListView(APIView):
    def get(self, request):
        denied = admin_only(request)
        if denied:
            return denied
        payouts = Payout.objects.select_related("raffle", "settled_by").all()[:100]
        return Response([{
            "id": payout.id, "raffle_title": payout.raffle.title, "organizer": payout.raffle.owner.username,
            "gross_amount": payout.gross_amount, "platform_fee": payout.platform_fee,
            "organizer_amount": payout.organizer_amount, "payment_count": payout.payment_count,
            "settled_by": payout.settled_by.username, "settled_at": payout.settled_at,
        } for payout in payouts])


class AdminReservationActionView(APIView):
    @transaction.atomic
    def post(self, request, code, action):
        denied = admin_only(request)
        if denied:
            return denied
        reservation = get_object_or_404(Reservation.objects.select_for_update(), code=code, status=Reservation.Status.ACTIVE)
        numbers = RaffleNumber.objects.select_for_update().filter(reservation=reservation, status=RaffleNumber.Status.RESERVED)
        if action == "confirm":
            numbers.update(status=RaffleNumber.Status.SOLD)
            reservation.status = Reservation.Status.CONFIRMED
        elif action == "cancel":
            numbers.update(status=RaffleNumber.Status.AVAILABLE, buyer_name="", buyer_email="", reservation=None)
            reservation.status = Reservation.Status.CANCELLED
        else:
            return Response({"detail": "Acción inválida."}, status=status.HTTP_400_BAD_REQUEST)
        reservation.save(update_fields=["status"])
        return Response({"detail": "Reserva actualizada."})


class AdminPayoutCreateView(APIView):
    @transaction.atomic
    def post(self, request, slug):
        denied = admin_only(request)
        if denied:
            return denied
        raffle = get_object_or_404(Raffle, slug=slug)
        payments = list(MercadoPagoPayment.objects.select_for_update().filter(
            reservation__raffle=raffle, status="approved", payout__isnull=True
        ).select_related("reservation"))
        if not payments:
            return Response({"detail": "No hay pagos pendientes para liquidar."}, status=status.HTTP_409_CONFLICT)
        totals = [payment_amounts(payment) for payment in payments]
        gross = sum(item[0] for item in totals)
        mercadopago_fee = sum(item[1] for item in totals)
        net = sum(item[2] for item in totals)
        fee = round(net * settings.PLATFORM_COMMISSION_PERCENT / 100)
        payout = Payout.objects.create(raffle=raffle, settled_by=request.user, gross_amount=gross, mercadopago_fee=mercadopago_fee, platform_fee=fee, organizer_amount=net-fee, payment_count=len(payments))
        MercadoPagoPayment.objects.filter(pk__in=[payment.pk for payment in payments]).update(payout=payout)
        return Response({"detail": "Liquidación registrada."})


class PublicRaffleListView(generics.ListAPIView):
    serializer_class = RaffleSerializer
    permission_classes = [permissions.AllowAny]
    queryset = Raffle.objects.filter(
        status__in=[Raffle.Status.PUBLISHED, Raffle.Status.CLOSED]
    ).select_related("owner").prefetch_related("numbers")


class RaffleDetailView(generics.RetrieveAPIView):
    serializer_class = RaffleSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = "slug"

    def get_queryset(self):
        queryset = Raffle.objects.select_related("owner").prefetch_related("numbers")
        if self.request.user.is_authenticated:
            return queryset.filter(status__in=[Raffle.Status.PUBLISHED, Raffle.Status.CLOSED]) | queryset.filter(owner=self.request.user)
        return queryset.filter(status__in=[Raffle.Status.PUBLISHED, Raffle.Status.CLOSED])

    def retrieve(self, request, *args, **kwargs):
        raffle = self.get_object()
        release_expired_reservations(raffle)
        raffle.refresh_from_db()
        serializer = self.get_serializer(raffle)
        return Response(serializer.data)


class MyRaffleListCreateView(generics.ListCreateAPIView):
    serializer_class = RaffleSerializer

    def get_queryset(self):
        return Raffle.objects.filter(owner=self.request.user).select_related("owner").prefetch_related("numbers")

    def perform_create(self, serializer):
        if serializer.validated_data.get("mercadopago_enabled") and not user_has_active_pro(self.request.user):
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"mercadopago_enabled": "Debes activar Pro antes de habilitar Mercado Pago."})
        if serializer.validated_data.get("status") == Raffle.Status.PUBLISHED and not user_has_active_pro(self.request.user):
            if Raffle.objects.filter(owner=self.request.user, status=Raffle.Status.PUBLISHED).exists():
                from rest_framework.exceptions import ValidationError
                raise ValidationError({"status": "El plan Gratis permite una rifa publicada a la vez. Contrata Pro para publicar más."})
        serializer.save()


class MyRaffleDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = RaffleSerializer
    lookup_field = "slug"

    def get_queryset(self):
        return Raffle.objects.filter(owner=self.request.user).select_related("owner").prefetch_related("numbers")

    def perform_update(self, serializer):
        enabling_mercadopago = serializer.validated_data.get("mercadopago_enabled") and not self.get_object().mercadopago_enabled
        if enabling_mercadopago and not raffle_has_paid_access(self.get_object()):
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"mercadopago_enabled": "Debes activar Pro antes de habilitar Mercado Pago."})
        publishing = serializer.validated_data.get("status") == Raffle.Status.PUBLISHED and self.get_object().status != Raffle.Status.PUBLISHED
        if publishing and not user_has_active_pro(self.request.user):
            if Raffle.objects.filter(owner=self.request.user, status=Raffle.Status.PUBLISHED).exists():
                from rest_framework.exceptions import ValidationError
                raise ValidationError({"status": "El plan Gratis permite una rifa publicada a la vez. Contrata Pro para publicar más."})
        serializer.save()


class MyRaffleNumberListView(generics.ListAPIView):
    serializer_class = AdminRaffleNumberSerializer

    def get_queryset(self):
        return RaffleNumber.objects.filter(
            raffle__slug=self.kwargs["slug"], raffle__owner=self.request.user
        ).select_related("reservation")


class CoverUploadView(APIView):
    parser_classes = [MultiPartParser]

    def post(self, request, slug):
        raffle = get_object_or_404(Raffle, slug=slug, owner=request.user)
        serializer = CoverUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if raffle.cover_image:
            raffle.cover_image.delete(save=False)
        raffle.cover_image = serializer.validated_data["cover"]
        raffle.save(update_fields=["cover_image", "updated_at"])
        version = int(raffle.updated_at.timestamp())
        path = f'{reverse("api-raffle-cover", kwargs={"slug": raffle.slug})}?v={version}'
        return Response({"cover_url": request.build_absolute_uri(path)})


class CoverView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, slug):
        raffle = get_object_or_404(
            Raffle,
            slug=slug,
            status__in=[Raffle.Status.PUBLISHED, Raffle.Status.CLOSED],
        )
        if not raffle.cover_image:
            return Response({"detail": "Esta rifa no tiene portada."}, status=status.HTTP_404_NOT_FOUND)
        response = FileResponse(raffle.cover_image.open("rb"), as_attachment=False)
        response["Cache-Control"] = "no-store"
        return response


class DrawRaffleView(APIView):
    @transaction.atomic
    def post(self, request, slug):
        raffle = get_object_or_404(
            Raffle.objects.select_for_update(),
            slug=slug,
            owner=request.user,
        )
        if RaffleDraw.objects.filter(raffle=raffle).exists():
            return Response({"detail": "Esta rifa ya fue sorteada."}, status=status.HTTP_409_CONFLICT)
        sold_numbers = list(
            RaffleNumber.objects.select_for_update().filter(
                raffle=raffle,
                status=RaffleNumber.Status.SOLD,
            )
        )
        if not sold_numbers:
            return Response(
                {"detail": "Debes tener al menos un número vendido para realizar el sorteo."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        winner = sold_numbers[secrets.randbelow(len(sold_numbers))]
        draw = RaffleDraw.objects.create(
            raffle=raffle,
            winning_number=winner,
            drawn_by=request.user,
        )
        raffle.status = Raffle.Status.CLOSED
        raffle.save(update_fields=["status", "updated_at"])
        transaction.on_commit(lambda: send_winner_email.delay(draw.id))
        return Response({"winning_number": winner.number, "drawn_at": draw.drawn_at})


class ReserveNumbersView(APIView):
    permission_classes = [permissions.AllowAny]

    @transaction.atomic
    def post(self, request, slug):
        raffle = get_object_or_404(Raffle, slug=slug, status=Raffle.Status.PUBLISHED)
        serializer = ReservationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if raffle.phone_required and not serializer.validated_data.get("buyer_phone", "").strip():
            return Response(
                {"buyer_phone": ["El teléfono es obligatorio para esta rifa."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        requested = serializer.validated_data["numbers"]
        now = timezone.now()
        release_expired_reservations(raffle)
        if free_raffle_limit_exceeded(raffle, len(requested)):
            return Response(
                {"detail": f"Esta rifa Gratis alcanzó su límite de {settings.FREE_RAFFLE_SALE_LIMIT} números. El organizador debe activar Pro para seguir vendiendo."},
                status=status.HTTP_409_CONFLICT,
            )

        numbers = list(
            RaffleNumber.objects.select_for_update().filter(raffle=raffle, number__in=requested)
        )
        found = {item.number for item in numbers}
        missing = sorted(set(requested) - found)
        unavailable = sorted(item.number for item in numbers if item.status != RaffleNumber.Status.AVAILABLE)
        if missing:
            return Response({"detail": f"Los números {missing} no existen."}, status=status.HTTP_400_BAD_REQUEST)
        if unavailable:
            return Response(
                {"detail": f"Los números {unavailable} ya no están disponibles."},
                status=status.HTTP_409_CONFLICT,
            )

        reservation = Reservation.objects.create(
            raffle=raffle,
            buyer_name=serializer.validated_data["buyer_name"],
            buyer_email=serializer.validated_data["buyer_email"],
            buyer_phone=serializer.validated_data.get("buyer_phone", "").strip(),
            source=Reservation.Source.ONLINE,
            number_snapshot=sorted(requested),
            expires_at=now + timedelta(minutes=20),
        )
        for item in numbers:
            item.status = RaffleNumber.Status.RESERVED
            item.buyer_name = reservation.buyer_name
            item.buyer_email = reservation.buyer_email
            item.reservation = reservation
            item.updated_at = now
        RaffleNumber.objects.bulk_update(
            numbers, ["status", "buyer_name", "buyer_email", "reservation", "updated_at"]
        )
        transaction.on_commit(lambda: send_reservation_created_email.delay(reservation.id))
        transaction.on_commit(lambda: send_reservation_owner_email.delay(reservation.id))
        return Response(
            ReservationSerializer(reservation, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class MercadoPagoCheckoutView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, code):
        reservation = get_object_or_404(Reservation.objects.select_related("raffle"), code=code)
        if reservation.status != Reservation.Status.ACTIVE or reservation.expires_at <= timezone.now():
            return Response({"detail": "Esta reserva ya no está disponible para pago."}, status=status.HTTP_409_CONFLICT)
        if not reservation.raffle.mercadopago_enabled or not raffle_has_paid_access(reservation.raffle):
            return Response({"detail": "El pago con Mercado Pago no está habilitado para esta rifa."}, status=status.HTTP_403_FORBIDDEN)
        try:
            payload = {
                "items": [{"title": f"Rifa {reservation.raffle.title} · números {', '.join(map(str, reservation.number_snapshot))}", "quantity": 1, "currency_id": "CLP", "unit_price": reservation.raffle.number_price * len(reservation.number_snapshot)}],
                "external_reference": str(reservation.code),
                "payer": {"email": reservation.buyer_email, "name": reservation.buyer_name},
            }
            if settings.FRONTEND_URL.startswith("https://"):
                payload["back_urls"] = {key: f"{settings.FRONTEND_URL}/reserva/{reservation.code}?payment={key}" for key in ("success", "failure", "pending")}
                payload["auto_return"] = "approved"
            if settings.MERCADOPAGO_WEBHOOK_URL:
                payload["notification_url"] = settings.MERCADOPAGO_WEBHOOK_URL
            preference = mercadopago_request("/checkout/preferences", method="POST", body=payload)
        except (RuntimeError, MercadoPagoError, urllib.error.URLError) as error:
            return Response({"detail": f"No fue posible iniciar Mercado Pago: {error}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        payment, _ = MercadoPagoPayment.objects.get_or_create(reservation=reservation)
        payment.preference_id = preference.get("id", "")
        payment.status = "pending"
        payment.payload = preference
        payment.save()
        return Response({"checkout_url": preference.get("init_point") or preference.get("sandbox_init_point")})


class MyPlanView(APIView):
    def get(self, request):
        purchase = PlanPurchase.objects.filter(
            user=request.user,
            status=PlanPurchase.Status.APPROVED,
            active_until__gt=timezone.now(),
        ).order_by("-active_until").first()
        return Response({"plan": purchase.plan if purchase else "free", "active_until": purchase.active_until if purchase else None})


class PlanCheckoutView(APIView):
    def post(self, request):
        purchase = PlanPurchase.objects.create(user=request.user, plan=PlanPurchase.Plan.PRO, amount=settings.PRO_PLAN_PRICE)
        try:
            payload = {
                "items": [{"title": "Rifácil Pro · acceso por 30 días", "quantity": 1, "currency_id": "CLP", "unit_price": purchase.amount}],
                "external_reference": f"plan:{purchase.code}",
                "payer": {"email": request.user.email, "name": request.user.username},
            }
            if settings.FRONTEND_URL.startswith("https://"):
                payload["back_urls"] = {key: f"{settings.FRONTEND_URL}/planes?payment={key}" for key in ("success", "failure", "pending")}
                payload["auto_return"] = "approved"
            if settings.MERCADOPAGO_WEBHOOK_URL:
                payload["notification_url"] = settings.MERCADOPAGO_WEBHOOK_URL
            preference = mercadopago_request("/checkout/preferences", method="POST", body=payload)
        except (RuntimeError, MercadoPagoError, urllib.error.URLError) as error:
            purchase.delete()
            return Response({"detail": f"No fue posible iniciar Mercado Pago: {error}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        purchase.preference_id = preference.get("id", "")
        purchase.status = PlanPurchase.Status.PENDING
        purchase.payload = preference
        purchase.save(update_fields=["preference_id", "status", "payload", "updated_at"])
        return Response({"checkout_url": preference.get("init_point") or preference.get("sandbox_init_point")})


class RaffleProCheckoutView(APIView):
    def post(self, request, slug):
        raffle = get_object_or_404(Raffle, slug=slug, owner=request.user)
        purchase, _ = RaffleProPurchase.objects.get_or_create(raffle=raffle, defaults={"user": request.user, "amount": settings.RAFFLE_PRO_PRICE})
        if purchase.status == "approved":
            return Response({"detail": "Esta rifa ya tiene Pro activado."}, status=status.HTTP_409_CONFLICT)
        purchase.user = request.user
        purchase.amount = settings.RAFFLE_PRO_PRICE
        try:
            payload = {"items": [{"title": f"Rifácil Pro para la rifa: {raffle.title}", "quantity": 1, "currency_id": "CLP", "unit_price": purchase.amount}], "external_reference": f"raffle-pro:{purchase.code}", "payer": {"email": request.user.email, "name": request.user.username}}
            if settings.FRONTEND_URL.startswith("https://"):
                payload["back_urls"] = {key: f"{settings.FRONTEND_URL}/panel/rifas/{raffle.slug}?payment={key}" for key in ("success", "failure", "pending")}
                payload["auto_return"] = "approved"
            if settings.MERCADOPAGO_WEBHOOK_URL:
                payload["notification_url"] = settings.MERCADOPAGO_WEBHOOK_URL
            preference = mercadopago_request("/checkout/preferences", method="POST", body=payload)
        except (RuntimeError, MercadoPagoError, urllib.error.URLError) as error:
            return Response({"detail": f"No fue posible iniciar Mercado Pago: {error}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        purchase.preference_id = preference.get("id", "")
        purchase.status = "pending"
        purchase.payload = preference
        purchase.save()
        return Response({"checkout_url": preference.get("init_point") or preference.get("sandbox_init_point")})


class MercadoPagoWebhookView(APIView):
    permission_classes = [permissions.AllowAny]

    @transaction.atomic
    def post(self, request):
        payment_id = request.data.get("data", {}).get("id") or request.query_params.get("data.id")
        if not payment_id:
            return Response(status=status.HTTP_200_OK)
        try:
            payment_data = mercadopago_request(f"/v1/payments/{payment_id}")
        except (RuntimeError, MercadoPagoError, urllib.error.URLError):
            return Response(status=status.HTTP_503_SERVICE_UNAVAILABLE)
        reference = payment_data.get("external_reference", "")
        if isinstance(reference, str) and reference.startswith("raffle-pro:"):
            purchase = RaffleProPurchase.objects.select_for_update().filter(code=reference.removeprefix("raffle-pro:")).first()
            if not purchase:
                return Response(status=status.HTTP_200_OK)
            purchase.payment_id = str(payment_id)
            purchase.status = payment_data.get("status", "rejected")
            purchase.payload = payment_data
            if purchase.status == "approved" and not purchase.activated_at:
                purchase.activated_at = timezone.now()
            purchase.save()
            return Response(status=status.HTTP_200_OK)
        if isinstance(reference, str) and reference.startswith("plan:"):
            purchase = PlanPurchase.objects.select_for_update().filter(code=reference.removeprefix("plan:")).first()
            if not purchase:
                return Response(status=status.HTTP_200_OK)
            was_approved = purchase.status == PlanPurchase.Status.APPROVED
            purchase.payment_id = str(payment_id)
            purchase.status = payment_data.get("status", PlanPurchase.Status.REJECTED)
            purchase.payload = payment_data
            if purchase.status == PlanPurchase.Status.APPROVED and not was_approved:
                current = PlanPurchase.objects.filter(
                    user=purchase.user, status=PlanPurchase.Status.APPROVED, active_until__gt=timezone.now()
                ).exclude(pk=purchase.pk).order_by("-active_until").first()
                purchase.active_until = (current.active_until if current else timezone.now()) + timedelta(days=30)
            purchase.save()
            return Response(status=status.HTTP_200_OK)
        reservation = Reservation.objects.select_for_update().filter(code=reference).first()
        if not reservation:
            return Response(status=status.HTTP_200_OK)
        record, _ = MercadoPagoPayment.objects.get_or_create(reservation=reservation)
        record.payment_id = str(payment_id)
        record.status = payment_data.get("status", "unknown")
        record.payload = payment_data
        record.save()
        if payment_data.get("status") == "approved" and reservation.status == Reservation.Status.ACTIVE:
            numbers = RaffleNumber.objects.select_for_update().filter(reservation=reservation, status=RaffleNumber.Status.RESERVED)
            numbers.update(status=RaffleNumber.Status.SOLD)
            reservation.status = Reservation.Status.CONFIRMED
            reservation.save(update_fields=["status"])
            transaction.on_commit(lambda: send_reservation_status_email.delay(reservation.id))
        return Response(status=status.HTTP_200_OK)


class ManualSaleView(APIView):
    @transaction.atomic
    def post(self, request, slug):
        raffle = get_object_or_404(Raffle, slug=slug, owner=request.user)
        serializer = ManualSaleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        requested = serializer.validated_data["numbers"]
        if free_raffle_limit_exceeded(raffle, len(requested)):
            return Response(
                {"detail": f"Esta rifa Gratis alcanzó su límite de {settings.FREE_RAFFLE_SALE_LIMIT} números. Activa Pro para seguir vendiendo."},
                status=status.HTTP_409_CONFLICT,
            )
        numbers = list(
            RaffleNumber.objects.select_for_update().filter(raffle=raffle, number__in=requested)
        )
        found = {item.number for item in numbers}
        missing = sorted(set(requested) - found)
        unavailable = sorted(item.number for item in numbers if item.status != RaffleNumber.Status.AVAILABLE)
        if missing:
            return Response({"detail": f"Los números {missing} no existen."}, status=status.HTTP_400_BAD_REQUEST)
        if unavailable:
            return Response({"detail": f"Los números {unavailable} no están disponibles."}, status=status.HTTP_409_CONFLICT)

        reservation = Reservation.objects.create(
            raffle=raffle,
            buyer_name=serializer.validated_data["buyer_name"],
            buyer_email=serializer.validated_data["buyer_email"],
            buyer_phone=serializer.validated_data["buyer_phone"],
            number_snapshot=sorted(requested),
            status=Reservation.Status.CONFIRMED,
            source=Reservation.Source.MANUAL,
            expires_at=timezone.now(),
        )
        for item in numbers:
            item.status = RaffleNumber.Status.SOLD
            item.buyer_name = reservation.buyer_name
            item.buyer_email = reservation.buyer_email
            item.reservation = reservation
        RaffleNumber.objects.bulk_update(
            numbers, ["status", "buyer_name", "buyer_email", "reservation", "updated_at"]
        )
        return Response(
            ReservationSerializer(reservation, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class MyReservationListView(generics.ListAPIView):
    serializer_class = ReservationSerializer

    def get_queryset(self):
        raffles = list(Raffle.objects.filter(owner=self.request.user))
        for raffle in raffles:
            release_expired_reservations(raffle)
        return (
            Reservation.objects.filter(
                raffle__owner=self.request.user,
                status__in=[Reservation.Status.ACTIVE, Reservation.Status.CONFIRMED],
            )
            .select_related("raffle")
            .prefetch_related("numbers")
        )


class ReservationActionView(APIView):
    @transaction.atomic
    def post(self, request, code, action):
        reservation = get_object_or_404(
            Reservation.objects.select_for_update().select_related("raffle"),
            code=code,
            raffle__owner=request.user,
        )
        if reservation.status != Reservation.Status.ACTIVE:
            return Response({"detail": "Esta reserva ya fue procesada."}, status=status.HTTP_409_CONFLICT)
        if reservation.expires_at <= timezone.now():
            release_expired_reservations(reservation.raffle)
            return Response({"detail": "La reserva ya venció."}, status=status.HTTP_409_CONFLICT)

        numbers = RaffleNumber.objects.select_for_update().filter(
            reservation=reservation,
            status=RaffleNumber.Status.RESERVED,
        )
        if action == "confirm":
            numbers.update(status=RaffleNumber.Status.SOLD)
            reservation.status = Reservation.Status.CONFIRMED
        elif action == "cancel":
            numbers.update(
                status=RaffleNumber.Status.AVAILABLE,
                buyer_name="",
                buyer_email="",
                reservation=None,
            )
            reservation.status = Reservation.Status.CANCELLED
        else:
            return Response({"detail": "Acción inválida."}, status=status.HTTP_400_BAD_REQUEST)
        reservation.save(update_fields=["status"])
        transaction.on_commit(lambda: send_reservation_status_email.delay(reservation.id))
        return Response(ReservationSerializer(reservation, context={"request": request}).data)


class ReceiptUploadView(APIView):
    permission_classes = [permissions.AllowAny]
    parser_classes = [MultiPartParser]

    @transaction.atomic
    def post(self, request, code):
        reservation = get_object_or_404(
            Reservation.objects.select_for_update().select_related("raffle"),
            code=code,
            status=Reservation.Status.ACTIVE,
        )
        if reservation.expires_at <= timezone.now():
            release_expired_reservations(reservation.raffle)
            return Response({"detail": "La reserva ya venció."}, status=status.HTTP_409_CONFLICT)
        serializer = ReceiptUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if reservation.payment_receipt:
            reservation.payment_receipt.delete(save=False)
        reservation.payment_receipt = serializer.validated_data["receipt"]
        reservation.receipt_uploaded_at = timezone.now()
        reservation.save(update_fields=["payment_receipt", "receipt_uploaded_at"])
        transaction.on_commit(lambda: send_receipt_uploaded_email.delay(reservation.id))
        return Response({"detail": "Comprobante recibido.", "uploaded_at": reservation.receipt_uploaded_at})


class BuyerReservationDetailView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, code):
        reservation = get_object_or_404(
            Reservation.objects.select_related("raffle").prefetch_related("numbers"),
            code=code,
        )
        release_expired_reservations(reservation.raffle)
        reservation.refresh_from_db()
        return Response(BuyerReservationSerializer(reservation).data)


class BuyerReservationCancelView(APIView):
    permission_classes = [permissions.AllowAny]

    @transaction.atomic
    def post(self, request, code):
        reservation = get_object_or_404(
            Reservation.objects.select_for_update().select_related("raffle"),
            code=code,
        )
        if reservation.status != Reservation.Status.ACTIVE:
            return Response({"detail": "Esta reserva ya no está activa."}, status=status.HTTP_409_CONFLICT)
        if reservation.expires_at <= timezone.now():
            release_expired_reservations(reservation.raffle)
            return Response({"detail": "La reserva ya venció."}, status=status.HTTP_409_CONFLICT)
        RaffleNumber.objects.select_for_update().filter(
            reservation=reservation,
            status=RaffleNumber.Status.RESERVED,
        ).update(
            status=RaffleNumber.Status.AVAILABLE,
            buyer_name="",
            buyer_email="",
            reservation=None,
        )
        if reservation.payment_receipt:
            reservation.payment_receipt.delete(save=False)
            reservation.payment_receipt = ""
        reservation.status = Reservation.Status.CANCELLED
        reservation.save(update_fields=["status", "payment_receipt"])
        transaction.on_commit(lambda: send_reservation_status_email.delay(reservation.id))
        return Response(BuyerReservationSerializer(reservation).data)


class ReceiptDownloadView(APIView):
    def get(self, request, code):
        reservation = get_object_or_404(
            Reservation,
            code=code,
            raffle__owner=request.user,
        )
        if not reservation.payment_receipt:
            return Response({"detail": "Esta reserva no tiene comprobante."}, status=status.HTTP_404_NOT_FOUND)
        return FileResponse(
            reservation.payment_receipt.open("rb"),
            as_attachment=False,
            filename=reservation.payment_receipt.name.rsplit("/", 1)[-1],
        )
