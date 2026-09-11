# Rifácil

MVP de una plataforma para crear y administrar rifas con frontend y backend independientes.

## Arquitectura

- `frontend/`: React, TypeScript y Vite (`http://localhost:5173`).
- `backend/`: Django, API REST y administración (`http://localhost:8000`).
- PostgreSQL: base de datos accesible solamente por el backend.

```text
rifas/
├── backend/       Django y API REST
├── frontend/      React y TypeScript
├── compose.yaml   Orquestación de los tres servicios
└── .env           Variables locales
```

## Requisitos

- Docker Desktop con Docker Compose

## Puesta en marcha

1. Copia `.env.example` como `.env`.
2. Construye e inicia los servicios:

   ```bash
   docker compose up --build
   ```

3. Abre `http://localhost:5173`.

Las migraciones se ejecutan automáticamente al iniciar el contenedor web.

Para entrar al administrador, crea un superusuario:

```bash
docker compose exec backend python manage.py createsuperuser
```

## Comandos útiles

```bash
docker compose exec backend python manage.py test
docker compose exec backend python manage.py check
docker compose exec backend python manage.py makemigrations
docker compose exec frontend npm run build
docker compose down
```
