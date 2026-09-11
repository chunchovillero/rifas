#!/bin/sh
set -e

echo "Esperando a PostgreSQL en ${POSTGRES_HOST:-db}:${POSTGRES_PORT:-5432}..."
until nc -z "${POSTGRES_HOST:-db}" "${POSTGRES_PORT:-5432}"; do
  sleep 1
done

python manage.py migrate --noinput
exec "$@"

