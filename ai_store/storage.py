import cloudinary
from cloudinary_storage.storage import MediaCloudinaryStorage


class OptimizedMediaCloudinaryStorage(MediaCloudinaryStorage):
    """
    Subclass of MediaCloudinaryStorage that automatically delivers optimized images:
    - Injects Cloudinary's `f_auto` (automatic Next-Gen format delivery: AVIF / WebP)
    - Injects Cloudinary's `q_auto` (automatic perceptual compression)
    - Maintains 100% backward-compatibility with Django's FieldFile, `{{ image.url }}`,
      and upload forms using `request.FILES`.
    """

    def _get_url(self, name):
        if not name:
            return ""
        if name.startswith("http://") or name.startswith("https://"):
            return name

        # Build the URL directly — pure string construction, no network calls,
        # no dependency on base-class helper methods of unknown cost.
        return cloudinary.CloudinaryImage(name).build_url(
            transformation=[{"fetch_format": "auto", "quality": "auto"}]
        )

    def _save(self, name, content):
        if hasattr(content, "seek"):
            try:
                content.seek(0)
            except Exception:
                pass
        return super()._save(name, content)