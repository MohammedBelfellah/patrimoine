import json
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from patrimoine.models import Patrimoine, Inspection, Intervention, Document, Region
from django.contrib.gis.geos import MultiPolygon, Polygon, GEOSGeometry
from django.db import connection
from datetime import datetime, timedelta
import random


class Command(BaseCommand):
    help = "Seed database with sample patrimoines, inspections, and interventions"

    def handle(self, *args, **options):
        self.stdout.write("Creating sample heritage sites...")

        # Get or create test user
        user, _ = User.objects.get_or_create(
            username="admin",
            defaults={
                "email": "admin@patrimoine.local",
                "is_staff": True,
                "is_superuser": False,
            },
        )

        # Sample Moroccan heritage sites with their regions
        sample_sites = [
            {
                "nom": "Médina de Fès",
                "region": "Fès-Meknès",
                "type": "HISTORIQUE",
                "statut": "CLASSE",
                "description": "Ancien centre urbain fortifié",
            },
            {
                "nom": "Koutoubia de Marrakech",
                "region": "Marrakech-Safi",
                "type": "HISTORIQUE",
                "statut": "CLASSE",
                "description": "Grande mosquée du XIIe siècle",
            },
            {
                "nom": "Casbah Taourirt",
                "region": "Drâa-Tafilalet",
                "type": "HISTORIQUE",
                "statut": "CLASSE",
                "description": "Forteresse historique du XVI-XVIIe siècles",
            },
            {
                "nom": "Vallée du Drâa",
                "region": "Drâa-Tafilalet",
                "type": "NATUREL",
                "statut": "INSCRIT",
                "description": "Vallée oasis avec patrimoine naturel",
            },
            {
                "nom": "Medina d'Essaouira",
                "region": "Marrakech-Safi",
                "type": "HISTORIQUE",
                "statut": "INSCRIT",
                "description": "Port historique côtier",
            },
        ]

        for site_data in sample_sites:
            try:
                # Find commune in the specified region
                from patrimoine.models import Region, Commune

                region = Region.objects.get(nom_region=site_data["region"])
                province = region.province_set.first()
                commune = province.commune_set.first()

                if not commune:
                    self.stdout.write(
                        self.style.WARNING(f"No commune found for {site_data['region']}")
                    )
                    continue

                # Create a sample polygon (centered around Morocco coordinates)
                # Latitude: ~31-36°N, Longitude: ~1-6°W
                lat_offset = random.uniform(-0.1, 0.1)
                lon_offset = random.uniform(-0.1, 0.1)
                center_lat = 32.0 + lat_offset
                center_lon = -5.0 + lon_offset

                # Create a square polygon around the center
                coords = [
                    (center_lon - 0.05, center_lat - 0.05),
                    (center_lon + 0.05, center_lat - 0.05),
                    (center_lon + 0.05, center_lat + 0.05),
                    (center_lon - 0.05, center_lat + 0.05),
                    (center_lon - 0.05, center_lat - 0.05),
                ]

                polygon = Polygon(coords)
                multi_polygon = MultiPolygon([polygon])

                # Use raw SQL to avoid GENERATED column issue
                with connection.cursor() as cursor:
                    wkt = multi_polygon.wkt
                    cursor.execute(
                        """
                        INSERT INTO patrimoine 
                        (nom_fr, nom_ar, description, type_patrimoine, statut, polygon_geom, id_commune, created_by, created_at, updated_at)
                        VALUES 
                        (%s, %s, %s, %s, %s, ST_GeomFromText(%s, 4326), %s, %s, NOW(), NOW())
                        RETURNING id_patrimoine
                        """,
                        [
                            site_data["nom"],
                            site_data["nom"],
                            site_data["description"],
                            site_data["type"],
                            site_data["statut"],
                            wkt,
                            commune.id_commune,
                            user.id,
                        ],
                    )
                    patrimoine_id = cursor.fetchone()[0]

                self.stdout.write(
                    self.style.SUCCESS(f"✓ Created Patrimoine: {site_data['nom']}")
                )

                # Fetch the created patrimoine
                patrimoine = Patrimoine.objects.get(id_patrimoine=patrimoine_id)

                # Create sample inspections
                for i in range(random.randint(1, 3)):
                    date_inspection = datetime.now().date() - timedelta(
                        days=random.randint(1, 365)
                    )
                    inspection = Inspection.objects.create(
                        id_patrimoine=patrimoine,
                        id_inspecteur=user,
                        date_inspection=date_inspection,
                        etat=random.choice(["BON", "MOYEN", "DEGRADE"]),
                        observations=f"Inspection de {site_data['nom']} effectuée le {date_inspection}",
                    )
                    self.stdout.write(f"  ✓ Created Inspection: {inspection}")

                # Create sample interventions
                for i in range(random.randint(0, 2)):
                    date_debut = datetime.now().date() - timedelta(
                        days=random.randint(30, 365)
                    )
                    date_fin = date_debut + timedelta(days=random.randint(30, 180))
                    intervention = Intervention.objects.create(
                        id_patrimoine=patrimoine,
                        nom_projet=f"Intervention {i+1} - {site_data['nom']}",
                        type_intervention=random.choice(
                            ["RESTAURATION", "REHABILITATION", "AUTRE"]
                        ),
                        date_debut=date_debut,
                        date_fin=date_fin,
                        prestataire="Bureau d'études patrimoine",
                        description="Travaux de conservation et restauration",
                        statut=random.choice(
                            ["PLANIFIEE", "EN_COURS", "TERMINEE", "SUSPENDUE"]
                        ),
                        created_by=user,
                    )
                    self.stdout.write(f"  ✓ Created Intervention: {intervention}")

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error creating {site_data['nom']}: {e}"))

        self.stdout.write(self.style.SUCCESS("\n✅ Sample data seeding completed!"))

        # Summary
        patrimoine_count = Patrimoine.objects.count()
        inspection_count = Inspection.objects.count()
        intervention_count = Intervention.objects.count()

        self.stdout.write(f"\n📊 Summary:")
        self.stdout.write(f"  Patrimoines: {patrimoine_count}")
        self.stdout.write(f"  Inspections: {inspection_count}")
        self.stdout.write(f"  Interventions: {intervention_count}")
