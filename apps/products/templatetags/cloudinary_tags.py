import re
from django import template
from django.utils.safestring import mark_safe

register = template.Library()

 
"""
What was this file created for?
It was created as an optional utility helper in case you wanted to do custom image resizing or cropping inside your HTML templates in the future, such as:

{{ product.image|cloudinary_thumb:200 }} (creates a 200x200 square thumbnail)
{{ product.image|cloudinary_resize:600 }} (resizes image to 600px width)
{{ product.image|cloudinary_srcset:"400,800" }} (generates responsive srcset)


"""

def _extract_url(image_or_url):
    """
    Extracts the string URL from a FieldFile, ImageField, CloudinaryResource, or string.
    """
    if not image_or_url:
        return ""
    if hasattr(image_or_url, "url"):
        try:
            return image_or_url.url
        except Exception:
            return ""
    return str(image_or_url)


def _apply_cloudinary_transform(url, transform_string):
    """
    Injects transformation parameters into a Cloudinary URL after '/upload/'.
    Maintains f_auto,q_auto if not already specified.
    """
    if not url or "/upload/" not in url:
        return url

    parts = url.split("/upload/", 1)
    base_prefix = parts[0] + "/upload/"
    rest = parts[1]

    # Clean existing default optimization if present in rest to avoid duplication
    if rest.startswith("f_auto,q_auto/"):
        rest = rest[len("f_auto,q_auto/"):]

    # Ensure format and quality optimization are included if not overridden
    transforms = [t.strip() for t in transform_string.split(",") if t.strip()]
    has_format = any(t.startswith("f_") for t in transforms)
    has_quality = any(t.startswith("q_") for t in transforms)

    if not has_format:
        transforms.append("f_auto")
    if not has_quality:
        transforms.append("q_auto")

    combined_transform = ",".join(transforms)
    return f"{base_prefix}{combined_transform}/{rest}"


@register.filter(name="cloudinary_transform")
def cloudinary_transform(image_or_url, transform_string=""):
    """
    Applies custom Cloudinary transformations to an ImageField or URL.
    Example: {{ product.image|cloudinary_transform:"w_500,h_500,c_fill" }}
    """
    url = _extract_url(image_or_url)
    if not url or not transform_string:
        return url
    return _apply_cloudinary_transform(url, transform_string)


@register.filter(name="cloudinary_thumb")
def cloudinary_thumb(image_or_url, size=200):
    """
    Returns a square thumbnail cropped with smart gravity (g_auto) and optimal compression.
    Example: {{ product.image|cloudinary_thumb:250 }}
    """
    url = _extract_url(image_or_url)
    if not url:
        return ""
    try:
        size_int = int(size)
    except (ValueError, TypeError):
        size_int = 200
    transform = f"c_fill,g_auto,w_{size_int},h_{size_int}"
    return _apply_cloudinary_transform(url, transform)


@register.filter(name="cloudinary_resize")
def cloudinary_resize(image_or_url, width=600):
    """
    Resizes an image preserving aspect ratio up to the specified max width.
    Example: {{ product.image|cloudinary_resize:800 }}
    """
    url = _extract_url(image_or_url)
    if not url:
        return ""
    try:
        w = int(width)
    except (ValueError, TypeError):
        w = 600
    transform = f"c_limit,w_{w}"
    return _apply_cloudinary_transform(url, transform)


@register.filter(name="cloudinary_srcset")
def cloudinary_srcset(image_or_url, widths="360,720,1080"):
    """
    Generates a responsive srcset attribute string for modern <img> elements.
    Example:
      <img src="{{ product.image.url }}"
           srcset="{{ product.image|cloudinary_srcset:'360,720,1080' }}"
           sizes="(max-width: 600px) 100vw, 50vw"
           loading="lazy">
    """
    url = _extract_url(image_or_url)
    if not url or "/upload/" not in url:
        return ""

    width_list = [w.strip() for w in str(widths).split(",") if w.strip()]
    srcset_parts = []

    for w_str in width_list:
        try:
            w_int = int(w_str)
            resized_url = _apply_cloudinary_transform(url, f"c_limit,w_{w_int}")
            srcset_parts.append(f"{resized_url} {w_int}w")
        except (ValueError, TypeError):
            continue

    return mark_safe(", ".join(srcset_parts))
