# Run Patrimoine Locally (Windows)

This guide explains how to run the project on another PC using Docker.

## 1) Requirements to Install

- Windows 10/11
- Docker Desktop (includes Docker Compose)
  - Download: https://www.docker.com/products/docker-desktop/

## 2) Get the Project Files

Option A: Copy the project folder with USB or ZIP.

Option B: Clone from GitHub (if you have a repo):

```powershell
# In PowerShell
cd d:\dev
# Replace with your repo URL
# git clone https://github.com/yourname/patrimoine.git
# cd patrimoine
```

## 3) Create the .env File

In the project root, copy the example file:

```powershell
cd d:\dev\patrimoine
Copy-Item .env.example .env
```

Open .env and check values. You can keep defaults for local use.

## 4) Start the App with Docker

```powershell
cd d:\dev\patrimoine
docker compose up --build
```

Wait until you see:

- Django server started
- Database is healthy

## 5) Open the App

- App: http://localhost:8000
- Admin: http://localhost:8000/admin/
- Health: http://localhost:8000/health/

## 6) Create a Superuser (Admin)

In a new terminal:

```powershell
cd d:\dev\patrimoine
docker compose exec web python manage.py createsuperuser
```

## 7) Optional: Seed Sample Data

```powershell
cd d:\dev\patrimoine
docker compose exec web python manage.py seed_sample_patrimoines
```

## 8) Stop the App

```powershell
docker compose down
```

## 9) Full Reset (Delete DB Data)

This removes ALL database data and re-runs mpd_complete.sql:

```powershell
docker compose down -v
docker compose up --build
```

## 10) Common Commands

```powershell
# Check running containers
docker compose ps

# View Django logs
docker compose logs -f web

# View DB logs
docker compose logs -f db
```

## Troubleshooting

- Docker not running: start Docker Desktop.
- Port 8000 busy: stop the other app using 8000 or change the port in docker-compose.yml.
- Database not ready: wait 10-30 seconds and check logs.

If you want a Linux or Mac version of this guide, ask me and I will add it.
