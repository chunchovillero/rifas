from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail

from .models import Raffle, Reservation
from .services import release_expired_reservations


@shared_task
def release_all_expired_reservations():
    released = 0
    for raffle in Raffle.objects.filter(reservations__status="active").distinct():
        released += release_expired_reservations(raffle)
    return released


@shared_task
def send_reservation_created_email(reservation_id):
    reservation = Reservation.objects.select_related("raffle").get(id=reservation_id)
    numbers = ", ".join(map(str, reservation.number_snapshot))
    send_mail(
        f"Reserva creada: {reservation.raffle.title}",
        (
            f"Hola {reservation.buyer_name},\n\n"
            f"Reservaste los números {numbers}.\n"
            f"Código: {reservation.code}\n"
            f"Vence: {reservation.expires_at:%d-%m-%Y %H:%M}\n\n"
            "Conserva este código para consultar tu reserva."
        ),
        settings.DEFAULT_FROM_EMAIL,
        [reservation.buyer_email],
    )


@shared_task
def send_reservation_owner_email(reservation_id):
    reservation = Reservation.objects.select_related("raffle", "raffle__owner").get(id=reservation_id)
    if not reservation.raffle.owner.email:
        return 0
    numbers = ", ".join(map(str, reservation.number_snapshot))
    phone = f"\nTeléfono: {reservation.buyer_phone}" if reservation.buyer_phone else ""
    return send_mail(
        f"Nueva reserva: {reservation.raffle.title}",
        (
            f"{reservation.buyer_name} reservó los números {numbers}.\n"
            f"Correo: {reservation.buyer_email}{phone}\n"
            f"Código: {reservation.code}\n\n"
            "Revisa el panel de Rifácil para confirmar o cancelar la reserva."
        ),
        settings.DEFAULT_FROM_EMAIL,
        [reservation.raffle.owner.email],
    )


@shared_task
def send_receipt_uploaded_email(reservation_id):
    reservation = Reservation.objects.select_related("raffle", "raffle__owner").get(id=reservation_id)
    if not reservation.raffle.owner.email:
        return 0
    return send_mail(
        f"Nuevo comprobante: {reservation.raffle.title}",
        f"{reservation.buyer_name} subió un comprobante para la reserva {reservation.code}.",
        settings.DEFAULT_FROM_EMAIL,
        [reservation.raffle.owner.email],
    )


@shared_task
def send_reservation_status_email(reservation_id):
    reservation = Reservation.objects.select_related("raffle").get(id=reservation_id)
    labels = {
        Reservation.Status.CONFIRMED: "confirmado",
        Reservation.Status.CANCELLED: "cancelado",
        Reservation.Status.EXPIRED: "vencido",
    }
    label = labels.get(reservation.status, reservation.get_status_display().lower())
    return send_mail(
        f"Pago {label}: {reservation.raffle.title}",
        f"Hola {reservation.buyer_name}, el pago de tu reserva {reservation.code} fue {label}.",
        settings.DEFAULT_FROM_EMAIL,
        [reservation.buyer_email],
    )


@shared_task
def send_winner_email(draw_id):
    from .models import RaffleDraw

    draw = RaffleDraw.objects.select_related("raffle", "winning_number").get(id=draw_id)
    sent = 0
    winners = draw.winners or [{"position": 1, "prize": draw.raffle.prize, "number": draw.winning_number.number, "buyer_name": draw.winning_number.buyer_name}]
    for winner in winners:
        number = draw.raffle.numbers.filter(number=winner["number"]).first()
        if not number or not number.buyer_email:
            continue
        sent += send_mail(
            f"¡Ganaste la rifa {draw.raffle.title}!",
            f"Hola {winner['buyer_name']},\n\nTu número {winner['number']} ganó el {winner['position']}.º premio: {winner['prize']}. El organizador se pondrá en contacto contigo.",
            settings.DEFAULT_FROM_EMAIL,
            [number.buyer_email],
        )
    return sent
