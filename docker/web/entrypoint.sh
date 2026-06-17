#!/bin/sh
set -e

python manage.py migrate

# Fresh databases load mpd_complete.sql with FKs to utilisateur; Django owns auth_user.
# Run once after migrate while legacy table still exists (idempotent check).
python <<'PY'
from pathlib import Path
import os

import django
from django.db import connection

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

fix_path = Path("fix_user_fkeys.sql")
if fix_path.exists():
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = 'utilisateur'
            )
            """
        )
        if cursor.fetchone()[0]:
            print("Applying fix_user_fkeys.sql (utilisateur -> auth_user)...")
            cursor.execute(fix_path.read_text())
PY

exec python manage.py runserver 0.0.0.0:8000 --noreload
