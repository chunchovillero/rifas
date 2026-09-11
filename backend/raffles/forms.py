from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Raffle


class SignUpForm(UserCreationForm):
    email = forms.EmailField(label="Correo electrónico", required=True)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")


class RaffleForm(forms.ModelForm):
    draw_date = forms.DateTimeField(
        label="Fecha del sorteo",
        required=False,
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )

    class Meta:
        model = Raffle
        fields = (
            "title",
            "description",
            "prize",
            "total_numbers",
            "number_price",
            "draw_date",
            "status",
        )

