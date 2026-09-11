import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("rifacil")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

app.conf.beat_schedule = {
    "release-expired-reservations": {
        "task": "raffles.tasks.release_all_expired_reservations",
        "schedule": 60.0,
    }
}
