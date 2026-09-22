import os
import logging
from PIL import Image

logger = logging.getLogger(__name__)

# Allowed image extensions for product & profile photos
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
# Maximum allowed image file size (10 MB)
MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024


def validate_uploaded_image(file):
    """
    Validates an uploaded image file:
    1. Ensures file exists and is not empty (size > 0).
    2. Enforces maximum size limit (10MB).
    3. Enforces allowed extensions (.jpg, .jpeg, .png, .webp, .gif).
    4. Uses Pillow to verify the binary image header and structure.
    5. Always resets the file pointer (seek(0)) so subsequent upload/storage
       reads the full image data from the beginning.

    Returns:
        tuple (bool is_valid, str | None error_message)
    """
    if not file:
        return True, None

    # Check for empty file
    file_size = getattr(file, "size", 0)
    if file_size == 0:
        return False, "The uploaded file is empty (0 bytes)."

    # Check file size limit
    if file_size > MAX_IMAGE_SIZE_BYTES:
        size_mb = file_size / (1024 * 1024)
        return False, f"Image size ({size_mb:.1f} MB) exceeds the 10 MB limit. Please upload a smaller image."

    # Check file extension
    file_name = getattr(file, "name", "")
    ext = os.path.splitext(file_name)[1].lower() if file_name else ""
    if ext and ext not in ALLOWED_IMAGE_EXTENSIONS:
        return (
            False,
            f"Unsupported file format '{ext}'. Please upload a valid image file (.jpg, .jpeg, .png, .webp, or .gif).",
        )

    # Verify actual image data with Pillow
    try:
        img = Image.open(file)
        img.verify()
        # verify() moves the cursor; seek back to 0 so Cloudinary / Django can read the full bytes
        file.seek(0)
        return True, None
    except Exception as e:
        logger.warning("Uploaded image failed PIL verification for '%s': %s", file_name, e)
        try:
            file.seek(0)
        except Exception:
            pass
        return (
            False,
            f"File '{file_name or 'upload'}' is not a valid image or is corrupted. "
            "Please upload a valid JPG, PNG, WEBP, or GIF image.",
        )
