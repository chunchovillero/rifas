from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Raffle


class RaffleFlowTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="organizador", password="test-pass-123")

    def test_authenticated_user_creates_raffle_and_numbers(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("raffles:create"),
            {
                "title": "Rifa solidaria",
                "description": "Una rifa de prueba",
                "prize": "Canasta familiar",
                "total_numbers": 20,
                "number_price": 2000,
                "draw_date": "",
                "status": Raffle.Status.PUBLISHED,
            },
        )

        self.assertRedirects(response, reverse("raffles:dashboard"))
        raffle = Raffle.objects.get(title="Rifa solidaria")
        self.assertEqual(raffle.owner, self.owner)
        self.assertEqual(raffle.numbers.count(), 20)
        self.assertEqual(list(raffle.numbers.values_list("number", flat=True)), list(range(1, 21)))

    def test_draft_is_hidden_from_another_user(self):
        raffle = Raffle.objects.create(
            owner=self.owner,
            title="Rifa privada",
            description="Todavía no se publica",
            prize="Premio",
            total_numbers=10,
            number_price=1000,
        )

        response = self.client.get(raffle.get_absolute_url())

        self.assertRedirects(response, reverse("raffles:home"))

    def test_signup_logs_user_in(self):
        response = self.client.post(
            reverse("raffles:signup"),
            {
                "username": "nuevo",
                "email": "nuevo@example.com",
                "password1": "Una-clave-segura-123",
                "password2": "Una-clave-segura-123",
            },
        )

        self.assertRedirects(response, reverse("raffles:dashboard"))
        self.assertTrue(User.objects.filter(username="nuevo").exists())

