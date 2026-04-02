# Deploy Django With Supabase (Postgres) + Railway

This guide connects your Django app to a hosted Supabase PostgreSQL database, then deploys the web app on Railway.

## 0) Production Safety Checklist (Do this first)

1. Rotate all previously exposed credentials (DB password, SMTP password, Django secret key).
2. Use a dedicated production Supabase project, separate from development.
3. Keep DJANGO_DEBUG=0 in production.
4. Ensure DJANGO_ALLOWED_HOSTS and DJANGO_CSRF_TRUSTED_ORIGINS include exact production domains.
5. Keep daily database backups enabled in Supabase before first go-live.
6. Use URL-encoded DB password in DATABASE_URL if it contains special characters.

Password encoding examples:
- @ => %40
- $ => %24
- ! => %21

## 1) Create Supabase Project

1. Open Supabase dashboard.
2. Create a new project.
3. Go to Project Settings > Database.
4. Copy the connection string (URI).

Use the direct DB connection format similar to:
postgresql://postgres:YOUR_PASSWORD@db.YOUR_PROJECT_REF.supabase.co:5432/postgres?sslmode=require

If Supabase gives a pooler URL, you can also use it. Keep sslmode=require.

## 2) Enable PostGIS Extension on Supabase

Your app uses GeoDjango/PostGIS fields, so extension must be enabled.

Run in Supabase SQL Editor:
CREATE EXTENSION IF NOT EXISTS postgis;

Optional check:
SELECT PostGIS_Version();

## 2.1) Align user foreign keys with Django auth_user

If you initialized Supabase with mpd_complete.sql, run fix_user_fkeys.sql after it.
This updates all business foreign keys from legacy utilisateur(id_user) to Django auth_user(id).

Run in Supabase SQL Editor:
- Copy and execute the full file fix_user_fkeys.sql

## 3) Set Railway Environment Variables

Railway injects **`PORT`** (bind port) and often **`RAILWAY_PUBLIC_DOMAIN`** (your `*.up.railway.app` hostname). The app reads `RAILWAY_PUBLIC_DOMAIN` and appends it to **`ALLOWED_HOSTS`** and **`CSRF_TRUSTED_ORIGINS`** if you forgot to list it—still set explicit hosts for custom domains.

In Railway service variables, set at minimum:

| Variable | Example / note |
|----------|----------------|
| `DATABASE_URL` | Supabase URI (`postgresql://...`), password URL-encoded if needed |
| `DJANGO_DEBUG` | `0` |
| `DJANGO_SECRET_KEY` | Long random string (rotate if ever leaked) |
| `DJANGO_ALLOWED_HOSTS` | `127.0.0.1,localhost,your-app.up.railway.app` and any custom domain |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://your-app.up.railway.app,https://your-custom-domain.com` |
| `POSTGRES_SSLMODE` | `require` (usually also in `DATABASE_URL` query string) |

**Deploy command notes:** `railway.json` runs migrations and `collectstatic` in **preDeploy**, then starts **gunicorn** bound to **`0.0.0.0:$PORT`**. If the app failed to listen before, the usual cause was a shell quoting bug (`$PORT` must expand—this repo’s `railway.json` uses double quotes so it does).

Email variables if you need user welcome emails:
- EMAIL_BACKEND
- EMAIL_HOST
- EMAIL_PORT
- EMAIL_USE_TLS
- EMAIL_HOST_USER
- EMAIL_HOST_PASSWORD
- DEFAULT_FROM_EMAIL

## 4) Deploy on Railway

The project already includes Railway config in railway.json with:
- preDeployCommand: python manage.py migrate
- startCommand: collectstatic + gunicorn

Deploy steps:
1. Push code to GitHub.
2. In Railway, create new project from your repo.
3. Add the environment variables listed above.
4. Trigger deploy.

## 4.1) Static logo vs uploaded images

- **Logo (`/static/...`)**: collected by `collectstatic` and served by **WhiteNoise**.
- **Uploads (`patrimoine/...` in DB)**: on Railway the container disk is **ephemeral**. If you do **not** configure object storage, `/media/...` URLs often return **404** after a redeploy or when the file was never on that instance—the row in Postgres still points at a path that no longer exists on disk.

## 4.2) Supabase Storage for uploads (recommended on Railway)

Use the **same Supabase project** as Postgres: create a bucket, allow **public read** for that bucket (so image/PDF links work in the browser), then create **S3-compatible access keys** (Supabase Dashboard → **Project Settings → Storage**; naming may vary by dashboard version).

Add these **Railway variables** (in addition to `DATABASE_URL`):

| Variable | Value |
|----------|--------|
| `SUPABASE_URL` | Project URL, e.g. `https://YOUR_PROJECT_REF.supabase.co` (Settings → API → **Project URL**—not the Postgres host) |
| `SUPABASE_STORAGE_BUCKET` | Bucket name (e.g. `patrimoine-media`) |
| `SUPABASE_S3_ACCESS_KEY_ID` | S3 access key from Supabase Storage settings |
| `SUPABASE_S3_SECRET_ACCESS_KEY` | S3 secret key |

Optional: `AWS_S3_REGION_NAME` if uploads fail (try `us-east-1` or your region).

When these four variables are set, Django stores files in the bucket and templates use a full **`MEDIA_URL`** (`…/object/public/<bucket>/…`), so links survive redeploys.

**After enabling Storage:** upload the files again (or re-sync), because old rows still point at paths that only existed on the old container disk.

## 4.3) Alternative: Railway volume

You can attach a **Railway volume** mounted at `/app/media` instead of Supabase Storage. Files persist for that service until you remove the volume. You must not set the `SUPABASE_*` Storage variables above, so the app keeps using disk + `/media/` URLs.

## 4.4) Local development

Omit the Storage variables; the app uses `MEDIA_ROOT` under `./media` and `/media/` URLs as before.

## 5) Verify Health

Open:
/health/

Expected response:
{"status": "ok"}

Also verify:
1. Login works.
2. Region > Province > Commune dropdowns load.
3. Audit page opens.
4. Uploading a test document works.

## 6) Common Errors and Fixes

1. Connection refused / timeout:
- Check DATABASE_URL host, password, and port.
- Confirm Supabase project is not paused.

2. SSL error:
- Ensure sslmode=require in DATABASE_URL or POSTGRES_SSLMODE=require.

3. GeoDjango errors about PostGIS functions/types:
- Run CREATE EXTENSION IF NOT EXISTS postgis; on Supabase.

4. Bad Request (400) on production:
- Add your exact domain to DJANGO_ALLOWED_HOSTS.
- Add https://domain to DJANGO_CSRF_TRUSTED_ORIGINS.

5. Intermittent DNS errors to Supabase host:
- Prefer direct DB host URL (db.<project-ref>.supabase.co) when possible.
- Recreate web container/service after env change.

6. Uploaded images/PDFs return **404 Not Found** on `/media/...`:
- Railway’s disk is ephemeral: files disappear on redeploy unless you use **Supabase Storage** (see §4.2) or a **Railway volume** (§4.3).
- After switching to Storage, **re-upload** (or copy) files so the bucket contains the objects for existing `file_path` values in the database.

## 8) Rollback plan (minimum)

1. Keep previous Railway deployment available.
2. If new deploy fails, rollback to previous deployment in Railway.
3. Restore database from latest Supabase backup only if migration/data corruption occurred.

## 7) Local Test Using Supabase DB

You can test locally using the same remote database:
1. Put DATABASE_URL in local .env.
2. Set POSTGRES_SSLMODE=require.
3. Run app (Docker or local) and open /health/.

Note: if using Docker compose with local db service, keeping DATABASE_URL set will make Django use Supabase DB first.