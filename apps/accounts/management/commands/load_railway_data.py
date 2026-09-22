from pathlib import Path
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.conf import settings

User = get_user_model()


class Command(BaseCommand):
    help = "Loads initial database data from datadump.json into Railway PostgreSQL if the database is empty."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force loading datadump.json even if users already exist.",
        )

    def handle(self, *args, **options):
        fixture_path = settings.BASE_DIR / "datadump.json"
        force = options.get("force", False)

        if not fixture_path.exists():
            self.stdout.write(
                self.style.WARNING(f"Fixture file '{fixture_path}' not found. Skipping data load.")
            )
            return

        if not force and User.objects.exists():
            self.stdout.write(
                self.style.SUCCESS(
                    "Database already contains records (users exist). Skipping initial data load."
                )
            )
            return

        self.stdout.write(
            self.style.NOTICE("Populating database from datadump.json...")
        )
        try:
            call_command("loaddata", str(fixture_path))
            self.stdout.write(
                self.style.SUCCESS("Successfully loaded data from datadump.json into database!")
            )
        except Exception as e:
            self.stderr.write(
                self.style.ERROR(f"Error loading initial data: {e}")
            )
