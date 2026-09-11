# Rifácil — Documento de traspaso para servidor

Este archivo contiene el contexto técnico necesario para continuar el proyecto Rifácil en otro chat, especialmente para desplegarlo en un VPS, panel de hosting o servidor con Docker.

> **Seguridad:** no copies ni publiques secretos reales. No incluyas tokens de GitHub, claves de Mercado Pago, contraseñas de base de datos ni el archivo `.env` en Git.

## 1. Objetivo de la aplicación

Rifácil es una plataforma para crear y administrar rifas en línea.

El organizador puede crear una rifa, definir números, precio, imágenes, condiciones y datos de transferencia. Los participantes reservan números y pueden pagar por transferencia. Las rifas que tengan acceso Pro pueden habilitar Mercado Pago. La plataforma considera una futura liquidación al organizador, descontando las comisiones de Mercado Pago y Rifácil.

Características implementadas o en desarrollo:

- Registro e inicio de sesión de organizadores.
- Creación, edición, publicación y visualización pública de rifas.
- Selección visual de números y selección manual separada por comas.
- Reservas con nombre, correo y teléfono opcional u obligatorio según la rifa.
- Confirmación manual de transferencias por el organizador.
- Pago online con Mercado Pago, sujeto a acceso Pro.
- Plan Pro mensual y Pro por una sola rifa.
- Límite de 50 números ocupados para rifas gratuitas.
- Panel React para el organizador y administración propia de la plataforma.
- Enlace público, QR descargable y exportación CSV.
- Sorteos, estados de números, ingresos y reservas.

## 2. Estructura del repositorio

```text
rifas/
├── backend/                 # Django + Django REST Framework
│   ├── config/              # Settings, URLs, Celery
│   ├── api/                 # Endpoints y serializadores
│   ├── raffles/             # Modelos, lógica de rifas, migraciones y tareas
│   ├── static/              # Estáticos Django
│   ├── templates/           # Plantillas Django antiguas/de apoyo
│   ├── Dockerfile
│   ├── entrypoint.sh
│   └── requirements.txt
├── frontend/                # React + Vite + TypeScript
│   ├── src/                 # Componentes, rutas, estilos y API client
│   ├── public/brand/        # Logos públicos de Rifácil
│   ├── Dockerfile
│   └── package.json
├── compose.yaml             # Desarrollo local con Docker
├── .env.example             # Plantilla de configuración, sin secretos
├── .gitignore
└── README.md
```

Repositorio remoto:

```text
https://github.com/chunchovillero/rifas.git
```

La rama principal es `main`.

## 3. Tecnologías

| Capa | Tecnología |
| --- | --- |
| Backend | Python, Django, Django REST Framework |
| Frontend | React, TypeScript, Vite |
| Base de datos | PostgreSQL |
| Cola/tareas | Redis, Celery, Celery Beat |
| Pagos | Mercado Pago Checkout Pro/API de preferencias |
| Contenedores | Docker y Docker Compose |

## 4. Servicios Docker actuales

El archivo `compose.yaml` define estos servicios:

| Servicio | Uso | Puerto local |
| --- | --- | --- |
| `db` | PostgreSQL | Interno de Docker |
| `redis` | Broker/cache para Celery | Interno de Docker |
| `backend` | API Django y servidor de desarrollo | `8000` |
| `frontend` | Vite en desarrollo | `5173` |
| `worker` | Procesamiento de tareas Celery | Interno |
| `beat` | Planificador de tareas Celery | Interno |

En desarrollo se puede levantar así:

```bash
docker compose up --build
```

URLs locales habituales:

```text
Frontend: http://localhost:5173
API/Django: http://localhost:8000
Admin Django: http://localhost:8000/admin/
```

## 5. Variables de entorno

Copia `.env.example` a `.env` en el servidor y asigna valores reales. Nunca subas `.env` al repositorio.

Variables relevantes:

```dotenv
# Django
SECRET_KEY=CAMBIAR_POR_UN_VALOR_LARGO_Y_SECRETO
DEBUG=False
ALLOWED_HOSTS=rifacil.cl,www.rifacil.cl
CSRF_TRUSTED_ORIGINS=https://rifacil.cl,https://www.rifacil.cl

# PostgreSQL
POSTGRES_DB=rifacil
POSTGRES_USER=rifacil
POSTGRES_PASSWORD=CAMBIAR_POR_PASSWORD_SEGURA
POSTGRES_HOST=db
POSTGRES_PORT=5432

# Frontend público que usa Django para redirecciones de pago
FRONTEND_URL=https://rifacil.cl

# Mercado Pago: usar una credencial de producción al publicar
MERCADOPAGO_ACCESS_TOKEN=APP_USR-REEMPLAZAR
MERCADOPAGO_WEBHOOK_URL=https://api.rifacil.cl/api/payments/mercadopago/webhook/

# Negocio
PRO_PLAN_PRICE=4990
RAFFLE_PRO_PRICE=2495
FREE_RAFFLE_SALE_LIMIT=50
PLATFORM_COMMISSION_PERCENT=5
```

Notas:

- `MERCADOPAGO_ACCESS_TOKEN` debe ser de producción para cobros reales. No uses tokens de prueba en producción.
- Configura el webhook de Mercado Pago con una URL HTTPS pública que apunte al backend.
- Si frontend y API usan subdominios distintos, ajusta CORS, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` y `FRONTEND_URL`.
- Antes de producción, rota cualquier secreto que se haya enviado por chat, correo o repositorio accidentalmente.

## 6. Base de datos y migraciones

Las migraciones de Django están versionadas en:

```text
backend/raffles/migrations/
```

Al desplegar una nueva versión, ejecutar:

```bash
docker compose exec backend python manage.py migrate --noinput
```

Para crear el administrador inicial:

```bash
docker compose exec backend python manage.py createsuperuser
```

Para comprobar el estado de la app:

```bash
docker compose ps
docker compose logs --tail=100 backend
docker compose exec backend python manage.py check --deploy
```

## 7. Modelo de negocio implementado

### Rifa gratuita

- Permite reservas y pago por transferencia.
- Puede ocupar hasta `FREE_RAFFLE_SALE_LIMIT` números (por defecto, 50).
- Al llegar al límite, no permite nuevas reservas hasta activar Pro.
- No debe permitir cobro online con Mercado Pago.

### Pro mensual

- El organizador compra una membresía Pro.
- Mientras esté vigente, sus rifas pueden habilitar Mercado Pago.
- El valor sale de `PRO_PLAN_PRICE`.

### Pro por rifa

- El organizador paga una sola vez para habilitar funciones Pro solo en una rifa.
- El valor sale de `RAFFLE_PRO_PRICE`.
- La compra aprobada se guarda como `RaffleProPurchase`.

### Mercado Pago y liquidaciones

- En la implementación actual, el pago online se cobra a la cuenta configurada para Rifácil.
- El sistema registra el pago aprobado y contempla una liquidación posterior hacia el organizador.
- La liquidación debe descontar comisión Mercado Pago y `PLATFORM_COMMISSION_PERCENT`.
- Antes de operar comercialmente, revisar obligaciones tributarias, términos de Mercado Pago y regulación local para rifas/sorteos.

## 8. Rutas importantes de frontend

Las rutas se gestionan desde `frontend/src/main.tsx`.

| Ruta | Descripción |
| --- | --- |
| `/` | Página pública principal |
| `/panel` | Panel del organizador |
| `/panel/rifas/:slug` | Administración de una rifa |
| `/nueva` | Crear rifa |
| `/rifas/:slug` | Página pública de una rifa |
| `/reserva/:code` | Reserva y pago del participante |
| `/planes` | Planes Pro |
| `/ayuda/pro` | Documentación para usuarios Pro |
| `/administracion` | Administración interna personalizada |
| `/administracion/rifas` | Rifas de la plataforma |
| `/administracion/pagos` | Pagos y liquidaciones |

## 9. API y pagos

La API Django vive en `backend/api/` y `backend/raffles/`.

Puntos a revisar al desplegar:

1. El frontend debe apuntar a la URL correcta de la API. Revisa `frontend/src/api.ts` y las variables configuradas para el build.
2. Mercado Pago debe tener URLs HTTPS públicas para `success`, `failure`, `pending` y webhook.
3. El webhook debe ser idempotente: Mercado Pago puede enviar más de una notificación por pago.
4. No aprobar una reserva únicamente por redirección del navegador: la confirmación debe venir de la consulta/notificación de Mercado Pago.
5. Las transferencias continúan siendo confirmadas manualmente por el organizador.

## 10. Despliegue recomendado: VPS con Docker + Nginx

Para producción se recomienda un VPS Linux con Docker, Docker Compose y Nginx como proxy inverso. Un hosting compartido tradicional normalmente no puede ejecutar Docker, Redis, Celery y procesos persistentes de Django.

### 10.1 Requisitos del servidor

- Ubuntu/Debian reciente o equivalente.
- Docker Engine y Docker Compose plugin.
- Dominio configurado con registros DNS A hacia la IP del servidor.
- Puertos 80 y 443 disponibles.
- Certificado TLS con Let's Encrypt/Certbot o proxy administrado.

### 10.2 Preparación inicial

```bash
git clone https://github.com/chunchovillero/rifas.git
cd rifas
cp .env.example .env
nano .env
```

Completa las variables reales de `.env` antes de levantar servicios.

### 10.3 Producción: ajustes necesarios

El `compose.yaml` actual está orientado al desarrollo: frontend con Vite y backend con `runserver`. Para producción hay que crear o ajustar lo siguiente:

1. Un `Dockerfile` de producción para Django que use Gunicorn, no `runserver`.
2. Un build estático de React (`npm run build`) servido por Nginx.
3. Nginx como proxy a Gunicorn para `/api/`, `/admin/`, `/static/` y `/media/`.
4. Volúmenes persistentes para PostgreSQL y archivos `media`.
5. `DEBUG=False` y un `SECRET_KEY` nuevo.
6. `collectstatic` durante despliegue.
7. Certificado HTTPS; Mercado Pago no debe recibir webhooks HTTP sin TLS.

Arquitectura objetivo:

```text
Internet
   │ HTTPS 443
   ▼
Nginx
   ├── /            → archivos compilados de React
   ├── /api/        → Gunicorn / Django
   ├── /admin/      → Gunicorn / Django
   ├── /static/     → archivos estáticos Django
   └── /media/      → imágenes subidas por usuarios

Django ── PostgreSQL
       └─ Redis ── Celery worker / Celery beat
```

### 10.4 Comandos típicos de actualización

Una vez que producción esté configurada:

```bash
cd /ruta/al/proyecto/rifas
git pull origin main
docker compose -f compose.prod.yaml build
docker compose -f compose.prod.yaml up -d
docker compose -f compose.prod.yaml exec backend python manage.py migrate --noinput
docker compose -f compose.prod.yaml exec backend python manage.py collectstatic --noinput
docker compose -f compose.prod.yaml ps
```

> `compose.prod.yaml` todavía debe crearse/adaptarse. No asumas que el archivo de desarrollo es seguro tal cual para producción.

## 11. Hosting compartido tradicional

Un hosting compartido puede servir HTML/PHP y a veces Python mediante Passenger, pero suele tener limitaciones importantes:

- No suele permitir Docker.
- Puede no permitir PostgreSQL propio.
- No permite Redis ni workers Celery persistentes.
- Puede limitar procesos, webhooks y tareas programadas.

Opciones si solo hay hosting compartido:

1. Usarlo solo para el frontend React compilado (`frontend/dist`).
2. Hospedar Django, PostgreSQL, Redis y Celery en un VPS, Render, Railway, DigitalOcean, etc.
3. Configurar el dominio o subdominio de la API hacia el backend externo.

Para una plataforma con pagos y webhooks, la opción recomendada es VPS o plataforma administrada para backend; no hosting compartido como único servidor.

## 12. Archivos que no se deben subir

Ya están ignorados por `.gitignore`:

```text
.env
node_modules/
dist/
media/
staticfiles/
*.sqlite3
__pycache__/
.venv/
```

Antes de cada push, comprobar:

```bash
git status
git diff --cached --name-only
```

No deben aparecer:

- `.env`
- tokens `github_pat_...`
- tokens `APP_USR-...` de Mercado Pago
- dumps de base de datos
- archivos de usuarios en `media/`

## 13. Estado de Git

El proyecto fue inicializado con:

```text
Rama: main
Commit inicial: 38147e3 — Initial commit: Rifácil platform
Remote: https://github.com/chunchovillero/rifas.git
```

Si el push no funciona, autenticar GitHub con Git Credential Manager, GitHub CLI o un Personal Access Token de acceso limitado al repositorio. Nunca escribir un token en chats, comandos guardados, `.env` ni archivos versionados.

## 14. Pruebas previas al despliegue

En desarrollo, ejecutar:

```bash
docker compose exec backend python manage.py test
docker compose exec frontend npm run build
```

Lista manual:

- Crear una rifa gratuita y validar límite de 50 números ocupados.
- Reservar por selección visual y por texto separado por comas.
- Validar teléfono obligatorio/opcional.
- Confirmar transferencia como organizador.
- Verificar que una rifa no Pro no muestra ni permite pago online.
- Comprar o simular Pro por rifa y verificar habilitación Mercado Pago.
- Probar webhook de Mercado Pago con credenciales de prueba antes de producción.
- Revisar QR, enlace compartible y descarga del QR.
- Verificar panel `/administracion` sin pantallas en blanco al navegar.

## 15. Instrucción sugerida para otro chat

Puedes pegar este texto junto a este archivo:

```text
Tengo el proyecto Rifácil en un repositorio Django + React + Docker. Lee SERVER_HANDOFF.md completo antes de hacer cambios. Necesito desplegarlo en [indicar VPS/panel/proveedor], manteniendo backend, PostgreSQL, Redis, Celery y frontend separados. No expongas secretos ni modifiques la lógica de pagos sin avisar. Propón los archivos de producción necesarios (Dockerfiles, compose.prod.yaml y Nginx), explícame cada variable de entorno y verifica migraciones, estáticos, HTTPS y webhook de Mercado Pago.
```

## 16. Pendientes técnicos recomendados

1. Crear configuración Docker específica de producción con Gunicorn y Nginx.
2. Agregar pruebas automatizadas de permisos Pro y webhook de Mercado Pago.
3. Firmar/verificar notificaciones de Mercado Pago según la documentación vigente.
4. Implementar notificaciones por correo/WhatsApp para reservas, pagos y sorteos.
5. Implementar conciliación y proceso controlado de liquidaciones.
6. Agregar monitoreo, backups automáticos de PostgreSQL y alertas.
7. Definir políticas legales, privacidad y términos de uso para rifas en Chile.
8. Revisar rendimiento para rifas con muchos números y agregar paginación/filtros cuando sea necesario.

