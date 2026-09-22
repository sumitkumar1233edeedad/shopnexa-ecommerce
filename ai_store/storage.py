import cloudinary
from cloudinary_storage.storage import MediaCloudinaryStorage


class OptimizedMediaCloudinaryStorage(MediaCloudinaryStorage):
    """
    Subclass of MediaCloudinaryStorage that automatically delivers optimized images:
    - Injects Cloudinary's `f_auto` (automatic Next-Gen format delivery: AVIF / WebP)
      based on the requesting browser's capabilities.
    - Injects Cloudinary's `q_auto` (automatic perceptual compression) to minimize bandwidth
      without noticeable quality degradation.
    - Maintains 100% backward-compatibility with Django's FieldFile, `{{ image.url }}`,
      and upload forms using `request.FILES`.
    """

    def _get_url(self, name):
        if not name:
            return ""
        # If already an absolute URL
        if name.startswith("http://") or name.startswith("https://"):
            return name

        name = self._normalise_name(name)
        name = self._prepend_prefix(name)
        cloudinary_resource = cloudinary.CloudinaryResource(
            name,
            default_resource_type=self._get_resource_type(name),
            url_options={
                "fetch_format": "auto",
                "quality": "auto",
            },
        )
        return cloudinary_resource.url

    def _save(self, name, content):
        # Guarantee stream cursor is at position 0 so Cloudinary receives all bytes
        if hasattr(content, "seek"):
            try:
                content.seek(0)
            except Exception:
                pass
        return super()._save(name, content)
