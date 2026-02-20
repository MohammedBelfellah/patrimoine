# Patrimoine — Django + PostGIS (Docker)

Ce projet est prêt pour:

- **Backend**: Django (Python)
- **Base de données**: PostgreSQL + PostGIS
- **Orchestration**: Docker Compose

Le schéma SQL `mpd_complete.sql` est chargé automatiquement au **premier** démarrage de la base.

## 1) Prérequis

- Docker Desktop installé et démarré

## 2) Initialiser les variables d'environnement

Depuis la racine du projet:

```bash
cp .env.example .env
```

Sur Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

## 3) Lancer le projet

```bash
docker compose up --build
```

Services:

- Django: http://localhost:8000
- Healthcheck: http://localhost:8000/health/
- PostGIS: localhost:5432

## 4) Commandes utiles

Créer un superuser Django:

```bash
docker compose exec web python manage.py createsuperuser
```

Arrêter les conteneurs:

```bash
docker compose down
```

## Important: réinitialiser complètement la base

Le script `mpd_complete.sql` est exécuté uniquement si le volume DB est vide.

Si tu modifies le script SQL et veux le rejouer:

```bash
docker compose down -v
docker compose up --build
```

`-v` supprime le volume Postgres, donc toutes les données de dev.
