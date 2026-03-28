from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create or update test accounts for demo login"

    def handle(self, *args, **options):
        user_model = get_user_model()

        admin_group, _ = Group.objects.get_or_create(name="ADMIN")
        inspecteur_group, _ = Group.objects.get_or_create(name="INSPECTEUR")

        accounts = [
            {
                "username": "superadmin",
                "email": "superadmin@patrimoine.local",
                "password": "SuperAdmin@123",
                "is_superuser": True,
                "is_staff": True,
                "groups": [],
            },
            {
                "username": "admin",
                "email": "admin@patrimoine.local",
                "password": "Admin@123",
                "is_superuser": False,
                "is_staff": True,
                "groups": [admin_group],
            },
            {
                "username": "inspecteur",
                "email": "inspecteur@patrimoine.local",
                "password": "Inspecteur@123",
                "is_superuser": False,
                "is_staff": False,
                "groups": [inspecteur_group],
            },
        ]

        for account in accounts:
            user, created = user_model.objects.get_or_create(
                username=account["username"],
                defaults={
                    "email": account["email"],
                    "is_staff": account["is_staff"],
                    "is_superuser": account["is_superuser"],
                },
            )

            user.email = account["email"]
            user.is_staff = account["is_staff"]
            user.is_superuser = account["is_superuser"]
            user.set_password(account["password"])
            user.save()

            user.groups.clear()
            for group in account["groups"]:
                user.groups.add(group)

            status = "created" if created else "updated"
            self.stdout.write(self.style.SUCCESS(f"{status}: {account['email']}"))

        self.stdout.write(self.style.SUCCESS("Demo test accounts are ready."))
