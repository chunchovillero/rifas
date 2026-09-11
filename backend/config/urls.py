from django.urls import include, path
from raffles.admin import rifacil_admin_site
from raffles.seo_views import raffle_seo_shell, robots, sitemap

urlpatterns = [
    path("robots.txt", robots, name="robots"),
    path("sitemap.xml", sitemap, name="sitemap"),
    path("seo/rifas/<slug:slug>", raffle_seo_shell, name="raffle-seo-shell"),
    path("admin/", rifacil_admin_site.urls),
    path("api/", include("api.urls")),
    path("cuenta/", include("django.contrib.auth.urls")),
    path("", include("raffles.urls")),
]
