from django.contrib.auth.models import User
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core import mail
from django.test import override_settings
from datetime import timedelta
from unittest.mock import patch
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from raffles.models import Raffle, RaffleDraw, RaffleNumber, Reservation
from raffles.tasks import release_all_expired_reservations, send_reservation_created_email, send_reservation_owner_email


class RaffleApiTests(APITestCase):
    def test_seo_endpoints_and_raffle_metadata(self):
        owner = User.objects.create_user(username="seo-owner")
        raffle = Raffle.objects.create(owner=owner, title="Rifa solidaria SEO", description="Una descripción especial", prize="Gran premio", total_numbers=20, number_price=1500, status=Raffle.Status.PUBLISHED)
        robots = self.client.get("/robots.txt")
        sitemap = self.client.get("/sitemap.xml")
        shell = self.client.get(f"/seo/rifas/{raffle.slug}")
        missing = self.client.get("/seo/rifas/no-existe")
        self.assertEqual(robots.status_code, 200)
        self.assertIn("Sitemap: https://rifacil.cl/sitemap.xml", robots.content.decode())
        self.assertEqual(sitemap["Content-Type"], "application/xml")
        self.assertIn(f"https://rifacil.cl/rifas/{raffle.slug}", sitemap.content.decode())
        self.assertContains(shell, "Rifa solidaria SEO | Rifa online en Rifácil")
        self.assertContains(shell, 'property="og:title"')
        self.assertContains(shell, 'type="application/ld+json"')
        self.assertEqual(missing.status_code, 404)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_reservation_email_contains_code_and_numbers(self):
        owner = User.objects.create_user(username="correo-owner", email="owner@example.com")
        raffle = Raffle.objects.create(
            owner=owner, title="Rifa correo", description="Prueba", prize="Premio",
            total_numbers=10, number_price=1000, status=Raffle.Status.PUBLISHED,
        )
        reservation = Reservation.objects.create(
            raffle=raffle, buyer_name="Comprador", buyer_email="buyer@example.com",
            number_snapshot=[3, 7], expires_at=timezone.now() + timedelta(minutes=20),
        )

        send_reservation_created_email(reservation.id)

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(str(reservation.code), mail.outbox[0].body)
        self.assertIn("3, 7", mail.outbox[0].body)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_owner_receives_new_reservation_notification(self):
        owner = User.objects.create_user(username="aviso-owner", email="owner@example.com")
        raffle = Raffle.objects.create(
            owner=owner, title="Rifa aviso", description="Prueba", prize="Premio",
            total_numbers=10, number_price=1000, status=Raffle.Status.PUBLISHED,
        )
        reservation = Reservation.objects.create(
            raffle=raffle, buyer_name="Comprador", buyer_email="buyer@example.com",
            buyer_phone="+56912345678", number_snapshot=[2], expires_at=timezone.now() + timedelta(minutes=20),
        )

        send_reservation_owner_email(reservation.id)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["owner@example.com"])
        self.assertIn("+56912345678", mail.outbox[0].body)

    def test_register_returns_token(self):
        response = self.client.post(
            "/api/auth/register/",
            {"username": "nuevo", "email": "nuevo@example.com", "password": "clave-segura-123"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertIn("token", response.data)

    def test_login_accepts_username_or_email(self):
        User.objects.create_user(username="persona", email="persona@example.com", password="clave-segura-123")
        by_username = self.client.post("/api/auth/login/", {"username": "persona", "password": "clave-segura-123"}, format="json")
        by_email = self.client.post("/api/auth/login/", {"username": "PERSONA@example.com", "password": "clave-segura-123"}, format="json")
        self.assertEqual(by_username.status_code, 200)
        self.assertEqual(by_email.status_code, 200)

    @override_settings(GOOGLE_CLIENT_ID="client-id.apps.googleusercontent.com")
    @patch("api.views.id_token.verify_oauth2_token")
    def test_google_login_creates_user_from_verified_email(self, verify):
        verify.return_value = {"email": "google@example.com", "email_verified": True, "given_name": "Google"}
        response = self.client.post("/api/auth/google/", {"credential": "signed-token"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("token", response.data)
        self.assertTrue(User.objects.filter(email="google@example.com").exists())

    def test_user_updates_profile_and_changes_password(self):
        user = User.objects.create_user(username="perfil", email="old@example.com", password="clave-segura-123")
        token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        profile = self.client.patch("/api/auth/me/", {"email": "new@example.com"}, format="json")
        self.assertEqual(profile.status_code, 200)
        changed = self.client.post("/api/auth/password/", {"current_password": "clave-segura-123", "new_password": "Clave-nueva-segura-456"}, format="json")
        self.assertEqual(changed.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.check_password("Clave-nueva-segura-456"))
        self.assertFalse(Token.objects.filter(user=user).exists())

    def test_buyer_cancels_reservation_and_releases_numbers(self):
        owner = User.objects.create_user(username="cancel-owner", email="owner@example.com")
        raffle = Raffle.objects.create(
            owner=owner, title="Rifa cancelable", description="Prueba", prize="Premio",
            total_numbers=2, number_price=1000, status=Raffle.Status.PUBLISHED,
        )
        reservation = Reservation.objects.create(
            raffle=raffle, buyer_name="Comprador", buyer_email="buyer@example.com",
            number_snapshot=[1], expires_at=timezone.now() + timedelta(minutes=20),
        )
        number = RaffleNumber.objects.create(
            raffle=raffle, number=1, status=RaffleNumber.Status.RESERVED,
            reservation=reservation, buyer_name="Comprador", buyer_email="buyer@example.com",
        )

        response = self.client.post(f"/api/reservations/{reservation.code}/cancel/")

        self.assertEqual(response.status_code, 200)
        reservation.refresh_from_db()
        number.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.CANCELLED)
        self.assertEqual(number.status, RaffleNumber.Status.AVAILABLE)
        self.assertIsNone(number.reservation_id)
        self.assertEqual(response.data["numbers"], [1])

    def test_authenticated_user_creates_raffle(self):
        user = User.objects.create_user(username="organizador", password="clave-segura-123")
        token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        response = self.client.post(
            "/api/me/raffles/",
            {
                "title": "Rifa desde React", "description": "Prueba API", "prize": "Premio",
                "total_numbers": 15, "number_price": 1000, "status": "published",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        raffle = Raffle.objects.get()
        self.assertEqual(raffle.owner, user)
        self.assertEqual(raffle.numbers.count(), 15)

        update = self.client.patch(
            f"/api/me/raffles/{raffle.slug}/",
            {"total_numbers": 18, "bank_name": "Banco de prueba"},
            format="json",
        )
        self.assertEqual(update.status_code, 200)
        raffle.refresh_from_db()
        self.assertEqual(raffle.total_numbers, 18)
        self.assertEqual(raffle.numbers.count(), 18)
        self.assertEqual(raffle.bank_name, "Banco de prueba")

        cover = SimpleUploadedFile("portada.png", b"fake-png-content", content_type="image/png")
        cover_upload = self.client.post(
            f"/api/me/raffles/{raffle.slug}/cover/",
            {"cover": cover},
            format="multipart",
        )
        self.assertEqual(cover_upload.status_code, 200)
        public_cover = self.client.get(f"/api/raffles/{raffle.slug}/cover/")
        self.assertEqual(public_cover.status_code, 200)
        raffle.refresh_from_db()
        raffle.cover_image.delete(save=False)

    def test_public_user_reserves_available_numbers(self):
        owner = User.objects.create_user(username="dueno", password="clave-segura-123")
        raffle = Raffle.objects.create(
            owner=owner, title="Rifa pública", description="Prueba", prize="Premio",
            total_numbers=5, number_price=1000, status=Raffle.Status.PUBLISHED,
        )
        RaffleNumber.objects.bulk_create(
            [RaffleNumber(raffle=raffle, number=n) for n in range(1, 6)]
        )

        response = self.client.post(
            f"/api/raffles/{raffle.slug}/reserve/",
            {"numbers": [2, 4], "buyer_name": "Comprador", "buyer_email": "buyer@example.com"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(set(response.data["numbers"]), {2, 4})
        self.assertEqual(Reservation.objects.count(), 1)
        self.assertEqual(
            RaffleNumber.objects.filter(status=RaffleNumber.Status.RESERVED).count(), 2
        )

        conflict = self.client.post(
            f"/api/raffles/{raffle.slug}/reserve/",
            {"numbers": [4], "buyer_name": "Otra persona", "buyer_email": "other@example.com"},
            format="json",
        )
        self.assertEqual(conflict.status_code, 409)

        receipt = SimpleUploadedFile("comprobante.jpg", b"fake-jpeg-content", content_type="image/jpeg")
        upload = self.client.post(
            f"/api/reservations/{response.data['code']}/receipt/",
            {"receipt": receipt},
            format="multipart",
        )
        self.assertEqual(upload.status_code, 200)
        buyer_status = self.client.get(f"/api/reservations/{response.data['code']}/")
        self.assertEqual(buyer_status.status_code, 200)
        self.assertEqual(set(buyer_status.data["numbers"]), {2, 4})
        self.assertEqual(buyer_status.data["total"], 2000)
        self.assertTrue(buyer_status.data["receipt_uploaded"])

        token = Token.objects.create(user=owner)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        receipt_download = self.client.get(
            f"/api/me/reservations/{response.data['code']}/receipt/"
        )
        self.assertEqual(receipt_download.status_code, 200)
        confirmation = self.client.post(
            f"/api/me/reservations/{response.data['code']}/confirm/",
            format="json",
        )
        self.assertEqual(confirmation.status_code, 200)
        self.assertEqual(confirmation.data["status"], Reservation.Status.CONFIRMED)
        self.assertEqual(
            RaffleNumber.objects.filter(status=RaffleNumber.Status.SOLD).count(), 2
        )
        history = self.client.get("/api/me/reservations/")
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.data[0]["status"], Reservation.Status.CONFIRMED)
        raffle_metrics = self.client.get(f"/api/me/raffles/{raffle.slug}/")
        self.assertEqual(raffle_metrics.data["sold_count"], 2)
        self.assertEqual(raffle_metrics.data["sold_revenue"], 2000)
        draw = self.client.post(f"/api/me/raffles/{raffle.slug}/draw/", format="json")
        self.assertEqual(draw.status_code, 200)
        self.assertIn(draw.data["winning_number"], [2, 4])
        self.assertEqual(RaffleDraw.objects.count(), 1)
        repeated_draw = self.client.post(f"/api/me/raffles/{raffle.slug}/draw/", format="json")
        self.assertEqual(repeated_draw.status_code, 409)
        public_result = self.client.get(f"/api/raffles/{raffle.slug}/")
        self.assertEqual(public_result.status_code, 200)
        self.assertIn(public_result.data["winning_number"], [2, 4])
        reservation = Reservation.objects.get()
        reservation.payment_receipt.delete(save=False)

    def test_detail_releases_expired_reservation(self):
        owner = User.objects.create_user(username="dueña", password="clave-segura-123")
        raffle = Raffle.objects.create(
            owner=owner, title="Rifa vencida", description="Prueba", prize="Premio",
            total_numbers=2, number_price=1000, status=Raffle.Status.PUBLISHED,
        )
        reservation = Reservation.objects.create(
            raffle=raffle, buyer_name="Comprador", buyer_email="buyer@example.com",
            number_snapshot=[1],
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        number = RaffleNumber.objects.create(
            raffle=raffle, number=1, status=RaffleNumber.Status.RESERVED,
            reservation=reservation,
        )

        released = release_all_expired_reservations()

        self.assertEqual(released, 1)
        number.refresh_from_db()
        reservation.refresh_from_db()
        self.assertEqual(number.status, RaffleNumber.Status.AVAILABLE)
        self.assertEqual(reservation.status, Reservation.Status.EXPIRED)
        buyer_history = self.client.get(f"/api/reservations/{reservation.code}/")
        self.assertEqual(buyer_history.data["numbers"], [1])

    def test_owner_can_register_manual_sale(self):
        owner = User.objects.create_user(username="venta-owner", password="clave-segura-123")
        raffle = Raffle.objects.create(
            owner=owner, title="Venta manual", description="Prueba", prize="Premio",
            total_numbers=3, number_price=1500, status=Raffle.Status.PUBLISHED,
        )
        RaffleNumber.objects.bulk_create(
            [RaffleNumber(raffle=raffle, number=number) for number in range(1, 4)]
        )
        token = Token.objects.create(user=owner)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        response = self.client.post(
            f"/api/me/raffles/{raffle.slug}/manual-sale/",
            {"numbers": [1, 3], "buyer_name": "Compra presencial", "buyer_phone": "+56912345678"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], Reservation.Status.CONFIRMED)
        self.assertEqual(response.data["buyer_phone"], "+56912345678")
        self.assertEqual(
            RaffleNumber.objects.filter(raffle=raffle, status=RaffleNumber.Status.SOLD).count(),
            2,
        )
