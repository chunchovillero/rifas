import re

from django.contrib.auth.models import User
from django.db import transaction
from rest_framework import serializers
from django.urls import reverse
from django.utils import timezone

from raffles.models import PlanPurchase, Raffle, RaffleNumber, Reservation


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "email", "is_staff")


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ("username", "email", "password")

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class RaffleNumberSerializer(serializers.ModelSerializer):
    class Meta:
        model = RaffleNumber
        fields = ("id", "number", "status")


class AdminRaffleNumberSerializer(serializers.ModelSerializer):
    reservation_code = serializers.UUIDField(source="reservation.code", read_only=True)
    reservation_status = serializers.CharField(source="reservation.status", read_only=True)
    buyer_phone = serializers.CharField(source="reservation.buyer_phone", read_only=True)

    class Meta:
        model = RaffleNumber
        fields = (
            "id", "number", "status", "buyer_name", "buyer_email", "buyer_phone",
            "reservation_code", "reservation_status", "updated_at",
        )


class RaffleSerializer(serializers.ModelSerializer):
    owner = UserSerializer(read_only=True)
    numbers = RaffleNumberSerializer(many=True, read_only=True)
    available_count = serializers.SerializerMethodField()
    reserved_count = serializers.SerializerMethodField()
    sold_count = serializers.SerializerMethodField()
    sold_revenue = serializers.SerializerMethodField()
    cover_url = serializers.SerializerMethodField()
    winning_number = serializers.SerializerMethodField()
    drawn_at = serializers.SerializerMethodField()
    raffle_pro_active = serializers.SerializerMethodField()

    def validate_accent_color(self, value):
        if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            raise serializers.ValidationError("Ingresa un color hexadecimal válido.")
        return value.lower()

    def get_winning_number(self, obj):
        draw = getattr(obj, "draw", None)
        return draw.winning_number.number if draw else None

    def get_drawn_at(self, obj):
        draw = getattr(obj, "draw", None)
        return draw.drawn_at if draw else None

    def get_raffle_pro_active(self, obj):
        raffle_pro = getattr(obj, "pro_purchase", None)
        if raffle_pro and raffle_pro.status == "approved":
            return True
        return PlanPurchase.objects.filter(user=obj.owner, status=PlanPurchase.Status.APPROVED, active_until__gt=timezone.now()).exists()

    def get_cover_url(self, obj):
        if not obj.cover_image:
            return None
        version = int(obj.updated_at.timestamp())
        path = f'{reverse("api-raffle-cover", kwargs={"slug": obj.slug})}?v={version}'
        request = self.context.get("request")
        return request.build_absolute_uri(path) if request else path

    def get_available_count(self, obj):
        return obj.numbers.filter(status=RaffleNumber.Status.AVAILABLE).count()

    def get_reserved_count(self, obj):
        return obj.numbers.filter(
            status__in=[RaffleNumber.Status.RESERVED, RaffleNumber.Status.PENDING]
        ).count()

    def get_sold_count(self, obj):
        return obj.numbers.filter(status=RaffleNumber.Status.SOLD).count()

    def get_sold_revenue(self, obj):
        return self.get_sold_count(obj) * obj.number_price

    class Meta:
        model = Raffle
        fields = (
            "id", "owner", "title", "slug", "description", "terms", "accent_color", "prize", "cover_url",
            "total_numbers", "number_price", "fundraising_goal", "draw_date", "status",
            "bank_name", "account_type", "account_number", "account_holder",
            "account_holder_id", "transfer_email", "phone_required", "mercadopago_enabled",
            "available_count", "reserved_count", "sold_count", "sold_revenue",
            "winning_number", "drawn_at", "raffle_pro_active",
            "numbers", "created_at", "updated_at",
        )
        read_only_fields = ("slug", "owner", "numbers", "created_at", "updated_at")

    @transaction.atomic
    def create(self, validated_data):
        raffle = Raffle.objects.create(owner=self.context["request"].user, **validated_data)
        RaffleNumber.objects.bulk_create(
            [RaffleNumber(raffle=raffle, number=n) for n in range(1, raffle.total_numbers + 1)]
        )
        return raffle

    @transaction.atomic
    def update(self, instance, validated_data):
        old_total = instance.total_numbers
        new_total = validated_data.get("total_numbers", old_total)
        if new_total < old_total:
            occupied = instance.numbers.filter(
                number__gt=new_total,
            ).exclude(status=RaffleNumber.Status.AVAILABLE)
            if occupied.exists():
                raise serializers.ValidationError(
                    {"total_numbers": "No puedes eliminar números reservados o vendidos."}
                )

        instance = super().update(instance, validated_data)
        if new_total > old_total:
            RaffleNumber.objects.bulk_create(
                [RaffleNumber(raffle=instance, number=n) for n in range(old_total + 1, new_total + 1)]
            )
        elif new_total < old_total:
            instance.numbers.filter(
                number__gt=new_total,
                status=RaffleNumber.Status.AVAILABLE,
            ).delete()
        return instance


class CoverUploadSerializer(serializers.Serializer):
    cover = serializers.FileField()

    def validate_cover(self, value):
        allowed = {"image/jpeg", "image/png", "image/webp"}
        if value.content_type not in allowed:
            raise serializers.ValidationError("La portada debe ser JPG, PNG o WebP.")
        if value.size > 5 * 1024 * 1024:
            raise serializers.ValidationError("La imagen no puede superar 5 MB.")
        return value


class ReservationRequestSerializer(serializers.Serializer):
    numbers = serializers.ListField(
        child=serializers.IntegerField(min_value=1), min_length=1, max_length=20
    )
    buyer_name = serializers.CharField(max_length=150)
    buyer_email = serializers.EmailField()
    buyer_phone = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")

    def validate_numbers(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("No puedes repetir números.")
        return value


class ManualSaleSerializer(serializers.Serializer):
    numbers = serializers.ListField(
        child=serializers.IntegerField(min_value=1), min_length=1, max_length=100
    )
    buyer_name = serializers.CharField(max_length=150)
    buyer_email = serializers.EmailField(required=False, allow_blank=True, default="")
    buyer_phone = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")

    def validate_numbers(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("No puedes repetir números.")
        return value


class ReservationSerializer(serializers.ModelSerializer):
    numbers = serializers.SerializerMethodField()
    raffle_title = serializers.CharField(source="raffle.title", read_only=True)
    raffle_slug = serializers.CharField(source="raffle.slug", read_only=True)
    total = serializers.SerializerMethodField()
    receipt_url = serializers.SerializerMethodField()

    def get_total(self, obj):
        return len(self.get_numbers(obj)) * obj.raffle.number_price

    def get_numbers(self, obj):
        return obj.number_snapshot or list(obj.numbers.values_list("number", flat=True))

    def get_receipt_url(self, obj):
        request = self.context.get("request")
        if not obj.payment_receipt or not request or request.user != obj.raffle.owner:
            return None
        return reverse("api-receipt-download", kwargs={"code": obj.code})

    class Meta:
        model = Reservation
        fields = (
            "code", "raffle_title", "raffle_slug", "buyer_name", "buyer_email", "buyer_phone",
            "status", "source", "expires_at", "numbers", "total",
            "receipt_url", "receipt_uploaded_at",
        )


class ReceiptUploadSerializer(serializers.Serializer):
    receipt = serializers.FileField()

    def validate_receipt(self, value):
        allowed = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
        if value.content_type not in allowed:
            raise serializers.ValidationError("El comprobante debe ser JPG, PNG, WebP o PDF.")
        if value.size > 5 * 1024 * 1024:
            raise serializers.ValidationError("El archivo no puede superar 5 MB.")
        return value


class BuyerReservationSerializer(serializers.ModelSerializer):
    numbers = serializers.SerializerMethodField()
    raffle_title = serializers.CharField(source="raffle.title", read_only=True)
    raffle_slug = serializers.CharField(source="raffle.slug", read_only=True)
    number_price = serializers.IntegerField(source="raffle.number_price", read_only=True)
    bank_name = serializers.CharField(source="raffle.bank_name", read_only=True)
    account_type = serializers.CharField(source="raffle.account_type", read_only=True)
    account_number = serializers.CharField(source="raffle.account_number", read_only=True)
    account_holder = serializers.CharField(source="raffle.account_holder", read_only=True)
    account_holder_id = serializers.CharField(source="raffle.account_holder_id", read_only=True)
    transfer_email = serializers.EmailField(source="raffle.transfer_email", read_only=True)
    mercadopago_enabled = serializers.SerializerMethodField()
    total = serializers.SerializerMethodField()
    receipt_uploaded = serializers.SerializerMethodField()

    def get_total(self, obj):
        return len(self.get_numbers(obj)) * obj.raffle.number_price

    def get_numbers(self, obj):
        return obj.number_snapshot or list(obj.numbers.values_list("number", flat=True))

    def get_receipt_uploaded(self, obj):
        return bool(obj.payment_receipt)

    def get_mercadopago_enabled(self, obj):
        if not obj.raffle.mercadopago_enabled:
            return False
        raffle_pro = getattr(obj.raffle, "pro_purchase", None)
        if raffle_pro and raffle_pro.status == "approved":
            return True
        return PlanPurchase.objects.filter(
            user=obj.raffle.owner,
            status=PlanPurchase.Status.APPROVED,
            active_until__gt=timezone.now(),
        ).exists()

    class Meta:
        model = Reservation
        fields = (
            "code", "raffle_title", "raffle_slug", "buyer_name", "buyer_email", "buyer_phone",
            "status", "source", "expires_at", "numbers", "number_price", "total",
            "bank_name", "account_type", "account_number", "account_holder",
            "account_holder_id", "transfer_email", "mercadopago_enabled", "receipt_uploaded",
            "receipt_uploaded_at",
        )
