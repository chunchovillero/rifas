from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from .forms import RaffleForm, SignUpForm
from .models import Raffle, RaffleNumber


def home(request):
    raffles = Raffle.objects.filter(status=Raffle.Status.PUBLISHED).select_related("owner")[:12]
    return render(request, "raffles/home.html", {"raffles": raffles})


def signup(request):
    if request.user.is_authenticated:
        return redirect("raffles:dashboard")
    form = SignUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect("raffles:dashboard")
    return render(request, "registration/signup.html", {"form": form})


@login_required
def dashboard(request):
    raffles = request.user.raffles.all()
    return render(request, "raffles/dashboard.html", {"raffles": raffles})


@login_required
@transaction.atomic
def create(request):
    form = RaffleForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        raffle = form.save(commit=False)
        raffle.owner = request.user
        raffle.save()
        RaffleNumber.objects.bulk_create(
            [RaffleNumber(raffle=raffle, number=n) for n in range(1, raffle.total_numbers + 1)]
        )
        return redirect("raffles:dashboard")
    return render(request, "raffles/form.html", {"form": form})


def detail(request, slug):
    raffle = get_object_or_404(Raffle.objects.select_related("owner"), slug=slug)
    if raffle.status == Raffle.Status.DRAFT and raffle.owner != request.user:
        return redirect("raffles:home")
    return render(request, "raffles/detail.html", {"raffle": raffle})

