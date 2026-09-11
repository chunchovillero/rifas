import json
from html import escape

from django.conf import settings
from django.http import Http404, HttpResponse
from django.utils.html import strip_tags
from django.views.decorators.http import require_GET

from .models import Raffle


SITE_URL = "https://rifacil.cl"


def _clean(value, limit=160):
    text = " ".join(strip_tags(str(value or "")).split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


@require_GET
def raffle_seo_shell(request, slug):
    try:
        raffle = Raffle.objects.select_related("owner").get(
            slug=slug, status__in=[Raffle.Status.PUBLISHED, Raffle.Status.CLOSED]
        )
    except Raffle.DoesNotExist as exc:
        raise Http404 from exc
    canonical = f"{SITE_URL}/rifas/{raffle.slug}"
    title = f"{_clean(raffle.title, 52)} | Rifa online en Rifácil"
    prizes = raffle.prizes or [raffle.prize]
    description = _clean(
        f"Participa en {raffle.title}. Premio: {prizes[0]}. "
        f"Números a ${raffle.number_price:,} en Rifácil.", 158
    ).replace(",", ".")
    image = request.build_absolute_uri(f"/api/raffles/{raffle.slug}/cover/") if raffle.cover_image else f"{SITE_URL}/brand/rifacil-logo-completo.png"
    structured = {
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": raffle.title,
        "description": description,
        "url": canonical,
        "image": image,
        "isPartOf": {"@type": "WebSite", "name": "Rifácil", "url": SITE_URL},
        "about": {"@type": "Thing", "name": f"Rifa: {raffle.title}"},
        "dateModified": raffle.updated_at.isoformat(),
    }
    structured_json = json.dumps(structured, ensure_ascii=False).replace("</", "<\\/")
    visible_prizes = "".join(f"<li>{escape(_clean(prize, 200))}</li>" for prize in prizes)
    html = f'''<!doctype html><html lang="es-CL"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title><meta name="description" content="{escape(description)}">
<link rel="canonical" href="{canonical}"><meta name="robots" content="index,follow,max-image-preview:large">
<meta property="og:type" content="website"><meta property="og:site_name" content="Rifácil"><meta property="og:locale" content="es_CL">
<meta property="og:title" content="{escape(title)}"><meta property="og:description" content="{escape(description)}"><meta property="og:url" content="{canonical}"><meta property="og:image" content="{escape(image)}">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{escape(title)}"><meta name="twitter:description" content="{escape(description)}"><meta name="twitter:image" content="{escape(image)}">
<meta name="theme-color" content="#0749d9"><link rel="icon" href="/brand/rifacil-isotipo.png">
<script type="application/ld+json">{structured_json}</script>
<script type="module" crossorigin src="/assets/app.js"></script><link rel="stylesheet" crossorigin href="/assets/app.css">
</head><body><div id="root"><main><h1>{escape(raffle.title)}</h1><p>{escape(_clean(raffle.description, 500))}</p><h2>Premios</h2><ol>{visible_prizes}</ol><p>Valor por número: ${raffle.number_price:,}</p></main></div></body></html>'''
    return HttpResponse(html)


@require_GET
def sitemap(request):
    static_urls = ["", "planes", "ayuda/pro", "privacidad", "terminos"]
    entries = [f"<url><loc>{SITE_URL}/{path}</loc></url>" for path in static_urls]
    for raffle in Raffle.objects.filter(status__in=[Raffle.Status.PUBLISHED, Raffle.Status.CLOSED]).only("slug", "updated_at"):
        entries.append(f"<url><loc>{SITE_URL}/rifas/{escape(raffle.slug)}</loc><lastmod>{raffle.updated_at.date().isoformat()}</lastmod></url>")
    xml = '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + "".join(entries) + "</urlset>"
    return HttpResponse(xml, content_type="application/xml")


@require_GET
def robots(request):
    body = """User-agent: *
Allow: /
Disallow: /panel
Disallow: /administracion
Disallow: /perfil
Disallow: /nueva
Disallow: /ingresar
Disallow: /registro
Disallow: /reserva
Disallow: /rifas/*/editar
Disallow: /api/
Sitemap: https://rifacil.cl/sitemap.xml
"""
    return HttpResponse(body, content_type="text/plain")
