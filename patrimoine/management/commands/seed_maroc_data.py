import json
from django.core.management.base import BaseCommand
from patrimoine.models import Region, Province, Commune


class Command(BaseCommand):
    help = "Seed database with Moroccan regions, provinces, and communes from JSON"

    def add_arguments(self, parser):
        parser.add_argument(
            "--filepath",
            type=str,
            default="maroc_regions_provinces_communes.json",
            help="Path to JSON file with Moroccan administrative data",
        )

    def handle(self, *args, **options):
        filepath = options["filepath"]

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f"File not found: {filepath}"))
            return
        except json.JSONDecodeError as e:
            self.stdout.write(self.style.ERROR(f"Invalid JSON: {e}"))
            return

        # Clear existing data
        self.stdout.write("Clearing existing data...")
        Commune.objects.all().delete()
        Province.objects.all().delete()
        Region.objects.all().delete()

        # Seed regions
        regions_data = data.get("regions", [])
        self.stdout.write(f"Processing {len(regions_data)} regions...")

        for region_data in regions_data:
            region_id = region_data.get("id")
            nom_region = region_data.get("nom", "").strip()

            if not nom_region:
                self.stdout.write(self.style.WARNING(f"Skipping region with no name"))
                continue

            region, created = Region.objects.get_or_create(
                id_region=region_id, defaults={"nom_region": nom_region}
            )

            if created:
                self.stdout.write(self.style.SUCCESS(f"✓ Created Region: {nom_region}"))

            # Seed provinces for this region
            provinces_data = region_data.get("provinces_prefectures", [])
            for prov_data in provinces_data:
                nom_province = prov_data.get("nom", "").strip()
                type_province = "Préfecture" if "préfecture" in prov_data.get("type", "").lower() else "Province"

                if not nom_province:
                    continue

                province, prov_created = Province.objects.get_or_create(
                    nom_province=nom_province,
                    id_region=region,
                    defaults={"type_province": type_province},
                )

                if prov_created:
                    self.stdout.write(
                        self.style.SUCCESS(f"  ✓ Created {type_province}: {nom_province}")
                    )

                # Seed communes for this province
                communes_data = prov_data.get("communes", [])
                for commune_name in communes_data:
                    nom_commune = commune_name.strip()

                    if not nom_commune:
                        continue

                    # Infer commune type (simplified: assume mostly "Urbaine" unless specific rules)
                    type_commune = "Urbaine"

                    commune, comm_created = Commune.objects.get_or_create(
                        nom_commune=nom_commune,
                        id_province=province,
                        defaults={"type_commune": type_commune},
                    )

                    if comm_created:
                        self.stdout.write(f"    ✓ Created Commune: {nom_commune}")

        self.stdout.write(self.style.SUCCESS("\n✅ Database seeding completed!"))
        
        # Summary
        region_count = Region.objects.count()
        province_count = Province.objects.count()
        commune_count = Commune.objects.count()
        
        self.stdout.write(f"\n📊 Summary:")
        self.stdout.write(f"  Régions: {region_count}")
        self.stdout.write(f"  Provinces/Préfectures: {province_count}")
        self.stdout.write(f"  Communes: {commune_count}")
