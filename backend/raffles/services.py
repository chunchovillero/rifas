from django.db import transaction
from django.utils import timezone

from .models import RaffleNumber, Reservation


@transaction.atomic
def release_expired_reservations(raffle):
    expired = list(
        Reservation.objects.select_for_update().filter(
            raffle=raffle,
            status=Reservation.Status.ACTIVE,
            expires_at__lte=timezone.now(),
        )
    )
    if not expired:
        return 0
    reservation_ids = [item.id for item in expired]
    RaffleNumber.objects.filter(
        reservation_id__in=reservation_ids,
        status=RaffleNumber.Status.RESERVED,
    ).update(
        status=RaffleNumber.Status.AVAILABLE,
        buyer_name="",
        buyer_email="",
        reservation=None,
    )
    Reservation.objects.filter(id__in=reservation_ids).update(status=Reservation.Status.EXPIRED)
    return len(reservation_ids)
