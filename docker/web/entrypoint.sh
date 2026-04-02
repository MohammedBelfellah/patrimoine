#!/bin/sh
set -e

python manage.py migrate

# Fresh DB loads mpd_complete.sql with FKs to utilisateur; Django owns auth_user.
# Run once after migrate while legacy table still exists (idempotent check).
if [ -f fix_user_fkeys.sql ]; then
  if [ -n "$DATABASE_URL" ]; then
    EXISTS=$(psql "$DATABASE_URL" -tAc "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'utilisateur');")
  else
    export PGPASSWORD="${POSTGRES_PASSWORD:-}"
    EXISTS=$(psql -h "${POSTGRES_HOST:-db}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USER:-patrimoine}" -d "${POSTGRES_DB:-patrimoine}" -tAc "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'utilisateur');")
  fi
  if [ "$EXISTS" = "t" ]; then
    echo "Applying fix_user_fkeys.sql (utilisateur -> auth_user)..."
    if [ -n "$DATABASE_URL" ]; then
      psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f fix_user_fkeys.sql
    else
      psql -h "${POSTGRES_HOST:-db}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USER:-patrimoine}" -d "${POSTGRES_DB:-patrimoine}" -v ON_ERROR_STOP=1 -f fix_user_fkeys.sql
    fi
  fi
fi

exec python manage.py runserver 0.0.0.0:8000 --noreload
