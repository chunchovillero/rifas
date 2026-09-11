from django.urls import include, path
from raffles.admin import rifacil_admin_site

urlpatterns = [
    path("admin/", rifacil_admin_site.urls),
    path("api/", include("api.urls")),
    path("cuenta/", include("django.contrib.auth.urls")),
    path("", include("raffles.urls")),
]
