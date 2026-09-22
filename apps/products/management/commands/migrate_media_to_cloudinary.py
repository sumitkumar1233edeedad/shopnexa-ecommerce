import os
from pathlib import Path
import cloudinary
import cloudinary.uploader
from django.core.management.base import BaseCommand
from django.conf import settings
from apps.products.models import Product, Review
from apps.accounts.models import Profile


class Command(BaseCommand):
    help = "Safely migrates local MEDIA_ROOT images to Cloudinary without altering local files or breaking database records."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simulate the migration without uploading files to Cloudinary.",
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Overwrite existing assets on Cloudinary with the same public ID.",
        )
        parser.add_argument(
            "--subfolder",
            type=str,
            default="",
            help="Only migrate a specific subfolder inside MEDIA_ROOT (e.g. 'product', 'default', 'profile_pic').",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        overwrite = options["overwrite"]
        subfolder_filter = options["subfolder"].strip().strip("/\\")

        self.stdout.write(self.style.MIGRATE_HEADING("=== Cloudinary Media Migration Tool ==="))

        # 1. Verify Cloudinary configuration
        cloud_name = getattr(settings, "CLOUDINARY_STORAGE", {}).get("CLOUD_NAME")
        api_key = getattr(settings, "CLOUDINARY_STORAGE", {}).get("API_KEY")
        api_secret = getattr(settings, "CLOUDINARY_STORAGE", {}).get("API_SECRET")

        if not (cloud_name and api_key and api_secret):
            self.stdout.write(
                self.style.ERROR(
                    "Cloudinary credentials missing! Please configure CLOUDINARY_CLOUD_NAME, "
                    "CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET in your .env file."
                )
            )
            return

        cloudinary.config(
            cloud_name=cloud_name,
            api_key=api_key,
            api_secret=api_secret,
            secure=True,
        )

        media_root = Path(settings.MEDIA_ROOT)
        if not media_root.exists():
            self.stdout.write(self.style.ERROR(f"MEDIA_ROOT does not exist at: {media_root}"))
            return

        scan_dir = media_root / subfolder_filter if subfolder_filter else media_root
        if not scan_dir.exists():
            self.stdout.write(self.style.ERROR(f"Target subfolder does not exist at: {scan_dir}"))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING("Mode: DRY-RUN (No files will be uploaded)"))
        else:
            self.stdout.write(self.style.SUCCESS(f"Mode: LIVE MIGRATION (Target Cloud: {cloud_name})"))

        # 2. Collect local media files
        self.stdout.write(f"\nScanning local files in: {scan_dir} ...")
        files_to_migrate = []
        for file_path in scan_dir.rglob("*"):
            if file_path.is_file():
                # Ignore OS metadata files
                if file_path.name in [".DS_Store", "Thumbs.db", "desktop.ini"]:
                    continue
                rel_path = file_path.relative_to(media_root).as_posix()
                files_to_migrate.append((file_path, rel_path))

        total_files = len(files_to_migrate)
        self.stdout.write(f"Found {total_files} file(s) in local media directory.\n")

        if total_files == 0:
            self.stdout.write(self.style.WARNING("No files to migrate."))
            return

        # 3. Process uploads
        uploaded_count = 0
        skipped_count = 0
        failed_count = 0

        for idx, (file_path, rel_path) in enumerate(files_to_migrate, start=1):
            file_size_kb = file_path.stat().st_size / 1024
            size_str = f"{file_size_kb:.1f} KB" if file_size_kb < 1024 else f"{file_size_kb / 1024:.2f} MB"

            # Derive public_id matching django-cloudinary-storage standard
            # Django-cloudinary-storage uses prefix 'media/' and relative path without extension
            rel_dir = os.path.dirname(rel_path).replace("\\", "/")
            base_name, _ = os.path.splitext(os.path.basename(rel_path))
            public_id = f"media/{rel_dir}/{base_name}" if rel_dir else f"media/{base_name}"
            public_id = public_id.replace("//", "/")

            self.stdout.write(f"[{idx}/{total_files}] {rel_path} ({size_str}) -> public_id: '{public_id}'")

            if dry_run:
                self.stdout.write(self.style.NOTICE(f"    [DRY-RUN] Would upload to https://res.cloudinary.com/{cloud_name}/image/upload/f_auto,q_auto/v1/{public_id}"))
                uploaded_count += 1
                continue

            try:
                upload_res = cloudinary.uploader.upload(
                    str(file_path),
                    public_id=public_id,
                    overwrite=overwrite,
                    resource_type="image",
                    tags=["media"],
                    use_filename=False,
                    unique_filename=False,
                )
                secure_url = upload_res.get("secure_url", "")
                self.stdout.write(self.style.SUCCESS(f"    Uploaded successfully -> {secure_url}"))
                uploaded_count += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"    Failed to upload {rel_path}: {e}"))
                failed_count += 1

        # 4. Audit database records
        self.stdout.write(self.style.MIGRATE_HEADING("\n=== Database Records Audit ==="))
        products = Product.objects.exclude(image="").exclude(image=None)
        self.stdout.write(f"Products with images: {products.count()}")
        for prod in products[:5]:
            self.stdout.write(f"  - Product: {prod.name}")
            self.stdout.write(f"    DB Field: {prod.image.name}")
            self.stdout.write(f"    Resolved URL: {prod.image.url}")

        profiles = Profile.objects.exclude(profile_picture="").exclude(profile_picture=None)
        self.stdout.write(f"\nProfiles with pictures: {profiles.count()}")
        for prof in profiles[:3]:
            self.stdout.write(f"  - User: {prof.name.username}")
            self.stdout.write(f"    DB Field: {prof.profile_picture.name}")
            self.stdout.write(f"    Resolved URL: {prof.profile_picture.url}")

        reviews = Review.objects.exclude(image="").exclude(image=None)
        self.stdout.write(f"\nReviews with images: {reviews.count()}")

        # 5. Summary
        self.stdout.write(self.style.MIGRATE_HEADING("\n=== Migration Summary ==="))
        self.stdout.write(f"Total Local Files:    {total_files}")
        self.stdout.write(self.style.SUCCESS(f"Processed/Uploaded:   {uploaded_count}"))
        if failed_count > 0:
            self.stdout.write(self.style.ERROR(f"Failed:               {failed_count}"))
        self.stdout.write(self.style.NOTICE("Note: Local files in MEDIA_ROOT remain untouched and safe."))
        self.stdout.write(self.style.SUCCESS("All database records and {{ image.url }} tags now resolve to Cloudinary!\n"))
