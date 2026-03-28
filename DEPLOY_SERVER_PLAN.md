# Plan de Deploiement - Choix du Serveur

## Serveur recommande
Je recommande un VPS Linux Ubuntu 22.04/24.04 chez Hetzner (ou DigitalOcean equivalent), avec Docker Compose.

Profil minimum conseille:
- 2 vCPU
- 4 Go RAM
- 60 Go SSD

Exemple:
- Hetzner CPX21/CPX22
- DigitalOcean Droplet Basic 2vCPU/4GB

## Pourquoi ce choix pour ton projet
Ton application utilise:
- Django 5
- PostGIS (base geospatiale)
- GDAL/GEOS/PROJ (GeoDjango)
- stockage media local

Ce stack est tres bien supporte sur un VPS Docker, plus simple et plus stable que beaucoup de PaaS pour PostGIS + GDAL.

## Verifications requirements (OK)
Fichier requirements actuel:
- Django>=5.0,<6.0
- psycopg[binary]>=3.1
- python-dotenv>=1.0
- gunicorn>=22.0

Conclusion:
- Les requirements Python sont suffisants pour prod.
- Les libs systeme GDAL/GEOS sont deja gerees dans docker/web/Dockerfile.

## Parametres prod a prevoir
Dans .env de production:
- DJANGO_DEBUG=0
- DJANGO_ALLOWED_HOSTS=ton-domaine.com,www.ton-domaine.com
- DJANGO_SECRET_KEY=cle-forte
- POSTGRES_PASSWORD=mot-de-passe-fort
- EMAIL_HOST_USER / EMAIL_HOST_PASSWORD renseignes

## Architecture deploiement conseillee
- Conteneur web Django (gunicorn)
- Conteneur PostgreSQL/PostGIS
- Reverse proxy (Nginx ou Caddy) pour HTTPS
- Volumes persistant pour DB et media

## Commandes de base (sur serveur)
```bash
# 1) Cloner
git clone <ton-repo>
cd patrimoine

# 2) Configurer .env
cp .env.example .env
# puis editer les variables prod

# 3) Lancer
docker compose up -d --build

# 4) Creer superuser
docker compose exec web python manage.py createsuperuser
```

## Recommandation importante avant mise en production
Ton docker-compose actuel lance Django avec runserver (dev). En production, il faut passer sur gunicorn.

Commande gunicorn recommandee:
```bash
gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 120
```

## Option rapide pour ton cas
- Etape 1: deployer sur un VPS Hetzner avec Docker (le plus adapte a ton projet actuel)
- Etape 2: je te prepare ensuite une version docker-compose.prod.yml + proxy HTTPS
