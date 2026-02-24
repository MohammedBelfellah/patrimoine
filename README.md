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

## 5) Email de bienvenue à la création d'utilisateur

Quand un Superadmin crée un utilisateur depuis **Gestion des utilisateurs**, un email de bienvenue est envoyé avec:

- rôle
- identifiants de connexion
- lien de connexion
- lien vers le dashboard du rôle

Configurer SMTP dans `.env`:

```dotenv
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp-relay.brevo.com
EMAIL_PORT=587
EMAIL_USE_TLS=1
EMAIL_HOST_USER=your_smtp_user
EMAIL_HOST_PASSWORD=your_smtp_password
DEFAULT_FROM_EMAIL=noreply@your-domain.com
```

### Services email gratuits (ou free tier)

- **Brevo (Sendinblue)**: free tier, SMTP simple à configurer
- **Mailtrap**: free tier pour test/dev (sandbox)
- **Gmail SMTP**: possible avec mot de passe d'application (moins recommandé pour prod)

## Important: réinitialiser complètement la base

Le script `mpd_complete.sql` est exécuté uniquement si le volume DB est vide.

Si tu modifies le script SQL et veux le rejouer:

```bash
docker compose down -v
docker compose up --build
```

`-v` supprime le volume Postgres, donc toutes les données de dev.
