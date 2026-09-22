import logging
from decimal import Decimal
from datetime import datetime
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.http import Http404
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from apps.accounts.models import Profile
from apps.products.validators import validate_uploaded_image
from .decorators import staff_perm_required

logger = logging.getLogger(__name__)
User = get_user_model()
from apps.products.models import *
from apps.order.models import *
from apps.coupons.models import Coupon, CouponUsage, CouponConfiguration



def admin_required(request):
    """
    Check whether the logged-in user is a staff/admin user.
    """

    if not request.user.is_authenticated:
        return False

    if not request.user.is_staff:
        return False

    return True


def admin_login(request):
    """
    Separate admin login page has been removed.
    Redirect to the unified login page.
    """
    if request.user.is_authenticated and request.user.is_staff:
        return redirect("admin_dashboard")
    return redirect("login")


@login_required(login_url="login")
def admin_logout(request):

    logout(request)

    return redirect("login")


@login_required(login_url="login")
def dashboard(request):

    if not request.user.is_staff:

        messages.error(
            request,
            "You do not have permission to access the admin panel."
        )

        return redirect("home")

    total_products = Product.objects.count()

    total_categories = Category.objects.count()

    total_customers = User.objects.filter(
        is_staff=False
    ).count()

    total_orders = Order.objects.count()

    recent_orders = (
        Order.objects
        .order_by("-id")[:10]
    )

    context = {

        "total_products": total_products,

        "total_categories": total_categories,

        "total_customers": total_customers,

        "total_orders": total_orders,

        "recent_orders": recent_orders,

    }

    return render(
        request,
        "adminpanel/admin_dashboard.html",
        context
    )

@staff_perm_required("products.add_product")
def product_add(request):
    if not request.user.is_staff:
        return redirect("home")

    categories = Category.objects.all().order_by("name")

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        brand = request.POST.get("brand", "").strip()
        description = request.POST.get("description", "").strip()
        category_id = request.POST.get("category")
        image = request.FILES.get("image")
        is_active = request.POST.get("is_active") == "on"

        context = {
            "categories": categories,
            "form_data": request.POST,
        }

        if not name:
            messages.error(request, "Product name is required.")
            return render(request, "adminpanel/admin_product_add.html", context)

        if not brand:
            messages.error(request, "Brand is required.")
            return render(request, "adminpanel/admin_product_add.html", context)

        if not category_id:
            messages.error(request, "Category is required.")
            return render(request, "adminpanel/admin_product_add.html", context)

        category = get_object_or_404(Category, id=category_id)

        # Validate main cover image if uploaded
        if image and getattr(image, "size", 0) > 0:
            is_valid, err = validate_uploaded_image(image)
            if not is_valid:
                messages.error(request, f"Main Image: {err}")
                return render(request, "adminpanel/admin_product_add.html", context)

        # Validate and filter dynamic gallery images
        raw_gallery_images = request.FILES.getlist("gallery_images")
        valid_gallery_images = []
        for g_img in raw_gallery_images:
            if not g_img or not getattr(g_img, "name", "") or getattr(g_img, "size", 0) == 0:
                continue
            is_valid, err = validate_uploaded_image(g_img)
            if not is_valid:
                messages.error(request, f"Gallery Image ({g_img.name}): {err}")
                return render(request, "adminpanel/admin_product_add.html", context)
            valid_gallery_images.append(g_img)

        # Save product and upload images atomically with clean error handling
        try:
            with transaction.atomic():
                product = Product.objects.create(
                    name=name,
                    brand=brand,
                    description=description,
                    image=image if (image and getattr(image, "size", 0) > 0) else None,
                    is_active=is_active,
                )
                product.cat.set([category])

                for g_img in valid_gallery_images:
                    ProductImage.objects.create(
                        product=product,
                        image=g_img
                    )

            messages.success(request, "Product added successfully.")
            return redirect("admin_products")
        except Exception as e:
            logger.exception("Failed to add product or upload images to Cloudinary: %s", e)
            messages.error(
                request,
                f"Image upload or product creation failed: {str(e)}. "
                "Please make sure you have selected valid images (JPG, PNG, WEBP, GIF) and try again."
            )
            return render(request, "adminpanel/admin_product_add.html", context)

    return render(
        request,
        "adminpanel/admin_product_add.html",
        {"categories": categories}
    )

@staff_perm_required("products.change_product")
def product_edit(request, slug):

    if not request.user.is_staff:
        return redirect("home")

    product = get_object_or_404(
        Product,
        slug=slug
    )

    categories = Category.objects.all().order_by("name")

    if request.method == "POST":

        name = request.POST.get("name", "").strip()
        brand = request.POST.get("brand", "").strip()
        description = request.POST.get("description", "").strip()
        category_id = request.POST.get("category")
        image = request.FILES.get("image")

        if not name:
            messages.error(request, "Product name is required.")
            return redirect(
                "admin_product_edit",
                slug=product.slug
            )

        if not brand:
            messages.error(request, "Brand is required.")
            return redirect(
                "admin_product_edit",
                slug=product.slug
            )

        if not category_id:
            messages.error(request, "Category is required.")
            return redirect(
                "admin_product_edit",
                slug=product.slug
            )

        category = get_object_or_404(
            Category,
            id=category_id
        )

        # Validate replacement main cover image if uploaded
        if image and getattr(image, "size", 0) > 0:
            is_valid, err = validate_uploaded_image(image)
            if not is_valid:
                messages.error(request, f"Main Image: {err}")
                return redirect(
                    "admin_product_edit",
                    slug=product.slug
                )

        # Validate and filter new gallery images
        raw_gallery_images = request.FILES.getlist("gallery_images")
        valid_gallery_images = []
        for g_img in raw_gallery_images:
            if not g_img or not getattr(g_img, "name", "") or getattr(g_img, "size", 0) == 0:
                continue
            is_valid, err = validate_uploaded_image(g_img)
            if not is_valid:
                messages.error(request, f"Gallery Image ({g_img.name}): {err}")
                return redirect(
                    "admin_product_edit",
                    slug=product.slug
                )
            valid_gallery_images.append(g_img)

        try:
            with transaction.atomic():
                product.name = name
                product.brand = brand
                product.description = description
                product.is_active = (
                    request.POST.get("is_active") == "on"
                )

                if image and getattr(image, "size", 0) > 0:
                    product.image = image

                product.save()

                product.cat.set([category])

                for g_img in valid_gallery_images:
                    ProductImage.objects.create(
                        product=product,
                        image=g_img
                    )

            messages.success(
                request,
                "Product updated successfully."
            )

            return redirect("admin_products")
        except Exception as e:
            logger.exception("Failed to update product or upload images to Cloudinary: %s", e)
            messages.error(
                request,
                f"Image upload or product update failed: {str(e)}. "
                "Please make sure you have selected valid images (JPG, PNG, WEBP, GIF) and try again."
            )
            return redirect(
                "admin_product_edit",
                slug=product.slug
            )

    return render(
        request,
        "adminpanel/admin_product_edit.html",
        {
            "product": product,
            "categories": categories,
        }
    )


@staff_perm_required("products.change_product")
def product_image_delete(request, image_id):

    if not request.user.is_staff:
        return redirect("home")

    img = get_object_or_404(ProductImage, id=image_id)
    product_slug = img.product.slug

    if img.image:
        img.image.delete(save=False)
    img.delete()

    messages.success(request, "Gallery image removed.")
    return redirect("admin_product_edit", slug=product_slug)


@staff_perm_required("products.view_product")
def product_detail(request, slug):

    if not request.user.is_staff:
        return redirect("home")

    product = get_object_or_404(
        Product,
        slug=slug
    )

    return render(
        request,
        "adminpanel/admin_product_detail.html",
        {
            "product": product
        }
    )

@staff_perm_required("products.delete_product")
def product_delete(request, slug):

    if not request.user.is_staff:
        return redirect("home")

    product = get_object_or_404(
        Product,
        slug=slug
    )

    if request.method == "POST":

        product.delete()

        messages.success(
            request,
            "Product deleted successfully."
        )

        return redirect("admin_products")

    return render(
        request,
        "adminpanel/admin_product_delete.html",
        {
            "product": product
        }
    )


@staff_perm_required("products.view_product")
def product_list(request):

    if not request.user.is_staff:
        return redirect("home")

    products = (
        Product.objects
        .prefetch_related("cat")
        .all()
        .order_by("-id")
    )

    search = request.GET.get("search", "").strip()

    if search:
        products = products.filter(
            Q(name__icontains=search) |
            Q(brand__icontains=search) |
            Q(description__icontains=search)
        )

    context = {
        "products": products,
        "search": search,
    }

    return render(
        request,
        "adminpanel/admin_product_list.html",
        context
    )


@staff_perm_required("products.view_category")
def category_list(request):

    if not request.user.is_staff:
        return redirect("home")

    categories = (
        Category.objects
        .all()
        .order_by("-id")
    )

    return render(
        request,
        "adminpanel/admin_category_list.html",
        {
            "categories": categories
        }
    )


@staff_perm_required("products.add_category")
def category_add(request):

    if not request.user.is_staff:
        return redirect("home")

    if request.method == "POST":

        name = request.POST.get("name", "").strip()

        if not name:
            messages.error(
                request,
                "Category name is required."
            )
            return redirect("admin_category_add")

        # Create base slug
        base_slug = slugify(name)
        slug = base_slug

        # Make slug unique
        counter = 1

        while Category.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1

        try:

            Category.objects.create(
                name=name,
                slug=slug
            )

            messages.success(
                request,
                "Category added successfully."
            )

            return redirect("admin_categories")

        except IntegrityError:

            messages.error(
                request,
                "Unable to add category. Slug already exists."
            )

            return redirect("admin_category_add")

    return render(
        request,
        "adminpanel/admin_category_add.html"
    )
from django.utils.text import slugify


@staff_perm_required("products.change_category")
def category_edit(request, slug):

    if not request.user.is_staff:
        return redirect("home")

    category = get_object_or_404(
        Category,
        slug=slug
    )

    if request.method == "POST":

        name = request.POST.get("name", "").strip()

        if not name:
            messages.error(
                request,
                "Category name is required."
            )
            return redirect(
                "admin_category_edit",
                slug=category.slug
            )

        # Generate unique slug
        base_slug = slugify(name)
        new_slug = base_slug
        counter = 1

        while Category.objects.filter(
            slug=new_slug
        ).exclude(
            pk=category.pk
        ).exists():

            new_slug = f"{base_slug}-{counter}"
            counter += 1

        category.name = name
        category.slug = new_slug
        category.save()

        messages.success(
            request,
            "Category updated successfully."
        )

        return redirect("admin_categories")

    return render(
        request,
        "adminpanel/admin_category_edit.html",
        {
            "category": category
        }
    )


@staff_perm_required("products.delete_category")
def category_delete(request, slug):

    if not request.user.is_staff:
        return redirect("home")

    category = get_object_or_404(
        Category,
        slug=slug
    )

    if request.method == "POST":

        category.delete()

        messages.success(
            request,
            "Category deleted successfully."
        )

        return redirect("admin_categories")

    return render(
        request,
        "adminpanel/admin_category_delete.html",
        {
            "category": category
        }
    )
@staff_perm_required("products.view_productvariant")
def variant_list(request):
 
    if not request.user.is_staff:
        return redirect("home")

    variants = (
        ProductVariant.objects
        .select_related("product", "color")
        .prefetch_related("stock")
        .all()
        .order_by("-id")
    )

    context = {
        "variants": variants,
    }

    return render(
        request,
        "adminpanel/admin_variant_list.html",
        context
    )


@staff_perm_required("products.add_productvariant")
def variant_add(request):
    if not request.user.is_staff:
        return redirect("home")

    products = Product.objects.all().order_by("name")
    colors = Color.objects.all().order_by("name")

    if request.method == "POST":
        product_val = request.POST.get("product", "").strip()
        color_val = request.POST.get("color", "").strip()
        sku = request.POST.get("sku", "").strip()
        size = request.POST.get("size", "").strip()
        price = request.POST.get("price", "").strip()
        quantity = request.POST.get("stock", "0").strip()
        is_active = request.POST.get("is_active", "on") == "on"

        context = {
            "products": products,
            "colors": colors,
            "form_data": request.POST,
        }

        if not product_val:
            messages.error(request, "Product is required.")
            return render(request, "adminpanel/admin_variant_add.html", context)

        if not sku:
            messages.error(request, "SKU is required.")
            return render(request, "adminpanel/admin_variant_add.html", context)

        if ProductVariant.objects.filter(sku=sku).exists():
            messages.error(request, f"A variant with SKU '{sku}' already exists.")
            return render(request, "adminpanel/admin_variant_add.html", context)

        # Resolve product by ID or slug
        if product_val.isdigit():
            product = get_object_or_404(Product, id=int(product_val))
        else:
            product = get_object_or_404(Product, slug=product_val)

        # Resolve color by ID, slug, or name
        color = None
        if color_val:
            if color_val.isdigit():
                color = get_object_or_404(Color, id=int(color_val))
            else:
                color = Color.objects.filter(
                    Q(slug=color_val) | Q(name__iexact=color_val)
                ).first()
                if not color:
                    color = get_object_or_404(Color, slug=color_val)

        try:
            price_val = Decimal(price)
        except Exception:
            messages.error(request, "Please enter a valid price.")
            return render(request, "adminpanel/admin_variant_add.html", context)

        try:
            qty_int = max(0, int(quantity or 0))
        except (ValueError, TypeError):
            qty_int = 0

        try:
            with transaction.atomic():
                variant = ProductVariant.objects.create(
                    product=product,
                    color=color,
                    size=size,
                    sku=sku,
                    price=price_val,
                    is_active=is_active,
                )

                Stock.objects.create(
                    variant=variant,
                    quantity=qty_int,
                )

            messages.success(request, "Variant added successfully.")
            return redirect("admin_variants")

        except Exception as error:
            logger.exception("Unable to create variant: %s", error)
            messages.error(request, f"Unable to create variant: {error}")
            return render(request, "adminpanel/admin_variant_add.html", context)

    context = {
        "products": products,
        "colors": colors,
    }

    return render(
        request,
        "adminpanel/admin_variant_add.html",
        context
    )

@staff_perm_required("products.change_productvariant")
def variant_edit(request, slug):

    if not request.user.is_staff:
        return redirect("home")

    variant = get_object_or_404(
        ProductVariant,
        slug=slug
    )

    products = Product.objects.all().order_by("name")
    colors = Color.objects.all().order_by("name")

    context = {
        "variant": variant,
        "products": products,
        "colors": colors,
    }

    if request.method == "POST":
        product_val = request.POST.get("product", "").strip()
        sku = request.POST.get("sku", "").strip()
        size = request.POST.get("size", "").strip()
        color_val = request.POST.get("color", "").strip()
        price = request.POST.get("price", "").strip()
        quantity = request.POST.get("stock", "0").strip()

        if not product_val:
            messages.error(request, "Product is required.")
            return render(request, "adminpanel/admin_variant_edit.html", context)

        if not sku:
            messages.error(request, "SKU is required.")
            return render(request, "adminpanel/admin_variant_edit.html", context)

        if ProductVariant.objects.filter(sku=sku).exclude(pk=variant.pk).exists():
            messages.error(request, f"Another variant with SKU '{sku}' already exists.")
            return render(request, "adminpanel/admin_variant_edit.html", context)

        # Resolve product by ID or slug
        if product_val.isdigit():
            product = get_object_or_404(Product, id=int(product_val))
        else:
            product = get_object_or_404(Product, slug=product_val)

        # Resolve color by ID, slug, or name
        color = None
        if color_val:
            if color_val.isdigit():
                color = get_object_or_404(Color, id=int(color_val))
            else:
                color = Color.objects.filter(
                    Q(slug=color_val) | Q(name__iexact=color_val)
                ).first()
                if not color:
                    color = get_object_or_404(Color, slug=color_val)

        try:
            price_val = Decimal(price)
        except Exception:
            messages.error(request, "Please enter a valid price.")
            return render(request, "adminpanel/admin_variant_edit.html", context)

        try:
            qty_int = max(0, int(quantity or 0))
        except (ValueError, TypeError):
            qty_int = 0

        try:
            with transaction.atomic():
                # Update ProductVariant
                variant.product = product
                variant.sku = sku
                variant.size = size
                variant.color = color
                variant.price = price_val
                if "is_active" in request.POST:
                    variant.is_active = (request.POST.get("is_active") == "on")

                variant.save()

                # Update or create Stock
                stock, created = Stock.objects.get_or_create(variant=variant)
                stock.quantity = qty_int
                stock.save()

            messages.success(request, "Variant updated successfully.")
            return redirect("admin_variants")

        except Exception as error:
            logger.exception("Unable to update variant: %s", error)
            messages.error(request, f"Unable to update variant: {error}")
            return render(request, "adminpanel/admin_variant_edit.html", context)

    return render(
        request,
        "adminpanel/admin_variant_edit.html",
        context
    )
 

@staff_perm_required("products.delete_productvariant")
def variant_delete(request, slug):

    if not request.user.is_staff:
        return redirect("home")

    variant = get_object_or_404(
        ProductVariant,
        slug=slug
    )

    if request.method == "POST":

        variant.delete()

        messages.success(
            request,
            "Variant deleted successfully."
        )

        return redirect(
            "admin_variants"
        )

    return render(
        request,
        "adminpanel/admin_variant_delete.html",
        {
            "variant": variant
        }
    )
 


@staff_perm_required("order.view_order")
def order_list(request):

    if not request.user.is_staff:
        return redirect("home")

    orders = (
        Order.objects
        .all()
        .order_by("-id")
    )

    status = request.GET.get(
        "status"
    )

    if status:

        orders = orders.filter(
            status=status
        )

    status_choices = []

    try:
        status_choices = Order._meta.get_field(
            "status"
        ).choices
    except Exception:
        pass

    context = {

        "orders": orders,

        "status": status,

        "status_choices": status_choices,

    }

    return render(
        request,
        "adminpanel/admin_order_list.html",
        context
    )


@staff_perm_required("order.view_order")
def order_detail(request, slug):

    if not request.user.is_staff:
        return redirect("home")

    order = get_object_or_404(
        Order.objects.select_related("user", "coupon").prefetch_related(
            "items__variant__product",
            "items__variant__color"
        ),
        slug=slug
    )

    return render(
        request,
        "adminpanel/admin_order_detail.html",
        {
            "order": order
        }
    )


@staff_perm_required("order.change_order")
def update_order_status(request, slug):

    if not request.user.is_staff:
        return redirect("home")

    order = get_object_or_404(
        Order,
        slug=slug
    )

    status_choices = []

    try:

        status_choices = (
            Order._meta
            .get_field("status")
            .choices
        )

    except Exception:

        status_choices = []

    if request.method == "POST":

        status = request.POST.get(
            "status"
        )

        if status:

            order.status = status

            order.save()

            messages.success(
                request,
                "Order status updated successfully."
            )

            return redirect(
                "admin_order_detail",
                slug=order.slug
            )

        messages.error(
            request,
            "Please select an order status."
        )

    context = {

        "order": order,

        "status_choices": status_choices,

    }

    return render(
        request,
        "adminpanel/admin_order_status.html",
        context
    )


@staff_perm_required("accounts.view_customuser")
def customer_list(request):

    if not request.user.is_staff:
        return redirect("home")

    customers = (
        User.objects
        .filter(is_staff=False)
        .select_related("profile")
        .order_by("-id")
    )

    search = request.GET.get(
        "search",
        ""
    ).strip()

    if search:

        customers = customers.filter(

            Q(username__icontains=search) |

            Q(email__icontains=search) |

            Q(first_name__icontains=search) |

            Q(last_name__icontains=search)

        )

    context = {

        "customers": customers,

        "search": search,

    }

    return render(
        request,
        "adminpanel/admin_customer_list.html",
        context
    )


@staff_perm_required("accounts.view_customuser")
def customer_detail(request, slug):

    if not request.user.is_staff:
        return redirect("home")

    customer = User.objects.filter(is_staff=False).filter(
        Q(profile__slug=slug) | Q(username=slug)
    ).first()

    if not customer:
        if slug.isdigit():
            customer = User.objects.filter(id=slug, is_staff=False).first()

    if not customer:
        raise Http404("Customer not found")

    customer_orders = (
        Order.objects
        .filter(user=customer)
        .order_by("-id")
    )

    context = {

        "customer": customer,

        "customer_orders": customer_orders,

    }

    return render(
        request,
        "adminpanel/admin_customer_detail.html",
        context
    )


@staff_perm_required("products.view_review")
def review_list(request):

    if not request.user.is_staff:
        return redirect("home")

    search_query = request.GET.get("search", "").strip()

    reviews = (
        Review.objects
        .select_related("product", "user", "user__profile")
        .all()
        .order_by("-id")
    )

    if search_query:
        reviews = reviews.filter(
            Q(product__name__icontains=search_query) |
            Q(user__username__icontains=search_query) |
            Q(user__first_name__icontains=search_query) |
            Q(user__last_name__icontains=search_query) |
            Q(product_review__icontains=search_query)
        )

    context = {
        "reviews": reviews,
        "search": search_query,
    }

    return render(
        request,
        "adminpanel/admin_review_list.html",
        context
    )


@staff_perm_required("products.view_review")
def review_detail(request, slug):

    if not request.user.is_staff:
        return redirect("home")

    review = Review.objects.select_related("product", "user", "user__profile").filter(slug=slug).first()
    if not review and slug.isdigit():
        review = Review.objects.select_related("product", "user", "user__profile").filter(id=int(slug)).first()

    if not review:
        raise Http404("Review not found")

    return render(
        request,
        "adminpanel/admin_review_detail.html",
        {
            "review": review
        }
    )


@staff_perm_required("products.delete_review")
def review_delete(request, slug):

    if not request.user.is_staff:
        return redirect("home")

    review = Review.objects.select_related("product", "user", "user__profile").filter(slug=slug).first()
    if not review and slug.isdigit():
        review = Review.objects.select_related("product", "user", "user__profile").filter(id=int(slug)).first()

    if not review:
        raise Http404("Review not found")

    if request.method == "POST":

        review.delete()

        messages.success(
            request,
            "Review deleted successfully."
        )

        return redirect(
            "admin_reviews"
        )

    return render(
        request,
        "adminpanel/admin_review_delete.html",
        {
            "review": review
        }
    )



@staff_perm_required("products.view_color")
def color_list(request):
    if not request.user.is_staff:
        return redirect("home")

    colors = Color.objects.all().order_by("-id")

    search = request.GET.get("search", "").strip()

    if search:
        colors = colors.filter(name__icontains=search)

    context = {
        "colors": colors,
        "search": search,
    }

    return render(
        request,
        "adminpanel/admin_color_list.html",
        context
    )


@staff_perm_required("products.add_color")
def color_add(request):
    if not request.user.is_staff:
        return redirect("home")

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        hex_code = request.POST.get("hex_code", "").strip()

        if not name:
            messages.error(request, "Color name is required.")
            return redirect("admin_color_add")

        try:
            Color.objects.create(
                name=name,
                hex_code=hex_code,
            )

            messages.success(
                request,
                "Color added successfully."
            )

            return redirect("admin_colors")

        except Exception as error:
            messages.error(
                request,
                f"Unable to add color: {error}"
            )

    return render(
        request,
        "adminpanel/admin_color_add.html"
    )


@staff_perm_required("products.change_color")
def color_edit(request, slug):
    if not request.user.is_staff:
        return redirect("home")

    color = get_object_or_404(
        Color,
        slug=slug
    )

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        hex_code = request.POST.get("hex_code", "").strip()

        if not name:
            messages.error(request, "Color name is required.")
            return redirect(
                "admin_color_edit",
                slug=color.slug
            )

        color.name = name
        color.hex_code = hex_code
        color.save()

        messages.success(
            request,
            "Color updated successfully."
        )

        return redirect("admin_colors")

    context = {
        "color": color,
    }

    return render(
        request,
        "adminpanel/admin_color_edit.html",
        context
    )


@staff_perm_required("products.delete_color")
def color_delete(request, slug):
    if not request.user.is_staff:
        return redirect("home")

    color = get_object_or_404(
        Color,
        slug=slug
    )

    if request.method == "POST":
        color.delete()

        messages.success(
            request,
            "Color deleted successfully."
        )

        return redirect("admin_colors")

    context = {
        "color": color,
    }

    return render(
        request,
        "adminpanel/admin_color_delete.html",
        context
    )


# =============================================================================
# COUPON MANAGEMENT VIEWS
# =============================================================================

def parse_admin_datetime(dt_str, default=None):
    if not dt_str:
        return default
    try:
        dt = parse_datetime(dt_str)
        if dt is None:
            dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        if dt and timezone.is_naive(dt):
            dt = timezone.make_aware(dt)
        return dt
    except Exception:
        return default


@staff_perm_required("coupons.view_coupon")
def coupon_list(request):
    if not request.user.is_staff:
        return redirect("home")

    coupons = Coupon.objects.all().order_by("-created_at")

    now = timezone.now()

    search = request.GET.get("search", "").strip()
    if search:
        coupons = coupons.filter(
            Q(code__icontains=search) | Q(description__icontains=search)
        )

    status = request.GET.get("status", "").strip()
    if status == "active":
        coupons = coupons.filter(is_active=True, valid_from__lte=now, valid_until__gte=now)
    elif status == "inactive":
        coupons = coupons.filter(is_active=False)
    elif status == "expired":
        coupons = coupons.filter(valid_until__lt=now)
    elif status == "upcoming":
        coupons = coupons.filter(valid_from__gt=now)

    discount_type = request.GET.get("discount_type", "").strip()
    if discount_type in ["percentage", "fixed"]:
        coupons = coupons.filter(discount_type=discount_type)

    total_coupons = Coupon.objects.count()
    active_coupons = Coupon.objects.filter(is_active=True, valid_from__lte=now, valid_until__gte=now).count()
    total_usages = CouponUsage.objects.count()
    total_discount_given = CouponUsage.objects.aggregate(total=Sum("discount_amount"))["total"] or Decimal("0.00")

    context = {
        "coupons": coupons,
        "search": search,
        "status": status,
        "discount_type": discount_type,
        "total_coupons": total_coupons,
        "active_coupons": active_coupons,
        "total_usages": total_usages,
        "total_discount_given": total_discount_given,
    }
    return render(request, "adminpanel/admin_coupon_list.html", context)


@staff_perm_required("coupons.change_couponconfiguration")
def coupon_configuration(request):
    if not request.user.is_staff:
        return redirect("home")

    config = CouponConfiguration.get_config()

    if request.method == "POST":
        weekly_limit_str = request.POST.get("weekly_user_limit", "").strip()
        try:
            weekly_limit = int(weekly_limit_str)
            if weekly_limit < 1:
                raise ValueError("Weekly limit must be at least 1.")
            config.weekly_user_limit = weekly_limit
            config.save()
            messages.success(request, f"Global weekly coupon allowance updated to {weekly_limit} uses per customer.")
            return redirect("admin_coupon_configuration")
        except ValueError as e:
            messages.error(request, str(e) if "Weekly limit" in str(e) else "Please enter a valid positive number for the weekly limit.")

    now = timezone.now()
    active_coupons_count = Coupon.objects.filter(is_active=True, valid_from__lte=now, valid_until__gte=now).count()
    total_usages_count = CouponUsage.objects.count()
    total_discount_given = CouponUsage.objects.aggregate(total=Sum("discount_amount"))["total"] or Decimal("0.00")

    context = {
        "config": config,
        "active_coupons_count": active_coupons_count,
        "total_usages_count": total_usages_count,
        "total_discount_given": total_discount_given,
    }
    return render(request, "adminpanel/admin_coupon_configuration.html", context)


@staff_perm_required("coupons.add_coupon")
def coupon_add(request):
    if not request.user.is_staff:
        return redirect("home")

    if request.method == "POST":
        code = request.POST.get("code", "").strip().upper()
        description = request.POST.get("description", "").strip()
        discount_type = request.POST.get("discount_type", "percentage")
        discount_value_str = request.POST.get("discount_value", "").strip()
        min_order_str = request.POST.get("minimum_order_amount", "0").strip()
        max_discount_str = request.POST.get("maximum_discount_amount", "").strip()
        valid_from_str = request.POST.get("valid_from", "").strip()
        valid_until_str = request.POST.get("valid_until", "").strip()
        usage_limit_str = request.POST.get("usage_limit", "").strip()
        per_user_limit_str = request.POST.get("per_user_limit", "").strip()
        weekly_user_limit_str = request.POST.get("weekly_user_limit", "5").strip()
        is_active = request.POST.get("is_active") in ["on", "true", "1"]

        if not code:
            messages.error(request, "Coupon code is required.")
            return render(request, "adminpanel/admin_coupon_add.html", {"form_data": request.POST})

        if Coupon.objects.filter(code__iexact=code).exists():
            messages.error(request, f"Coupon with code '{code}' already exists.")
            return render(request, "adminpanel/admin_coupon_add.html", {"form_data": request.POST})

        try:
            discount_value = Decimal(discount_value_str)
            if discount_value <= 0:
                raise ValueError()
            if discount_type == "percentage" and discount_value > 100:
                messages.error(request, "Percentage discount cannot exceed 100%.")
                return render(request, "adminpanel/admin_coupon_add.html", {"form_data": request.POST})
        except Exception:
            messages.error(request, "Please enter a valid discount value greater than 0.")
            return render(request, "adminpanel/admin_coupon_add.html", {"form_data": request.POST})

        try:
            minimum_order_amount = Decimal(min_order_str) if min_order_str else Decimal("0.00")
            if minimum_order_amount < 0:
                raise ValueError()
        except Exception:
            messages.error(request, "Minimum order amount must be 0 or greater.")
            return render(request, "adminpanel/admin_coupon_add.html", {"form_data": request.POST})

        maximum_discount_amount = None
        if max_discount_str:
            try:
                maximum_discount_amount = Decimal(max_discount_str)
                if maximum_discount_amount <= 0:
                    raise ValueError()
            except Exception:
                messages.error(request, "Maximum discount amount must be greater than 0.")
                return render(request, "adminpanel/admin_coupon_add.html", {"form_data": request.POST})

        valid_from = parse_admin_datetime(valid_from_str, default=timezone.now())
        valid_until = parse_admin_datetime(valid_until_str)
        if not valid_until:
            messages.error(request, "Valid until date is required.")
            return render(request, "adminpanel/admin_coupon_add.html", {"form_data": request.POST})

        if valid_until <= valid_from:
            messages.error(request, "Valid until date must be after valid from date.")
            return render(request, "adminpanel/admin_coupon_add.html", {"form_data": request.POST})

        usage_limit = int(usage_limit_str) if usage_limit_str else None
        per_user_limit = int(per_user_limit_str) if per_user_limit_str else None
        weekly_user_limit = int(weekly_user_limit_str) if weekly_user_limit_str else 5

        try:
            coupon = Coupon.objects.create(
                code=code,
                description=description,
                discount_type=discount_type,
                discount_value=discount_value,
                minimum_order_amount=minimum_order_amount,
                maximum_discount_amount=maximum_discount_amount,
                valid_from=valid_from,
                valid_until=valid_until,
                usage_limit=usage_limit,
                per_user_limit=per_user_limit,
                weekly_user_limit=weekly_user_limit,
                is_active=is_active,
            )
            messages.success(request, f"Coupon '{coupon.code}' created successfully.")
            return redirect("admin_coupons")
        except Exception as e:
            messages.error(request, f"Error creating coupon: {e}")
            return render(request, "adminpanel/admin_coupon_add.html", {"form_data": request.POST})

    now = timezone.now()
    default_data = {
        "valid_from": now.strftime("%Y-%m-%dT%H:%M"),
        "valid_until": (now + timezone.timedelta(days=30)).strftime("%Y-%m-%dT%H:%M"),
       
        "minimum_order_amount": "0.00",
        "is_active": True,
        "discount_type": "percentage",
    }
    return render(request, "adminpanel/admin_coupon_add.html", {"form_data": default_data})


@staff_perm_required("coupons.change_coupon")
def coupon_edit(request, slug):
    if not request.user.is_staff:
        return redirect("home")

    coupon = get_object_or_404(Coupon, slug=slug)

    if request.method == "POST":
        code = request.POST.get("code", "").strip().upper()
        description = request.POST.get("description", "").strip()
        discount_type = request.POST.get("discount_type", "percentage")
        discount_value_str = request.POST.get("discount_value", "").strip()
        min_order_str = request.POST.get("minimum_order_amount", "0").strip()
        max_discount_str = request.POST.get("maximum_discount_amount", "").strip()
        valid_from_str = request.POST.get("valid_from", "").strip()
        valid_until_str = request.POST.get("valid_until", "").strip()
        usage_limit_str = request.POST.get("usage_limit", "").strip()
        per_user_limit_str = request.POST.get("per_user_limit", "").strip()
        weekly_user_limit_str = request.POST.get("weekly_user_limit", "5").strip()
        is_active = request.POST.get("is_active") in ["on", "true", "1"]

        if not code:
            messages.error(request, "Coupon code is required.")
            return render(request, "adminpanel/admin_coupon_edit.html", {"coupon": coupon})

        if Coupon.objects.filter(code__iexact=code).exclude(pk=coupon.pk).exists():
            messages.error(request, f"Another coupon with code '{code}' already exists.")
            return render(request, "adminpanel/admin_coupon_edit.html", {"coupon": coupon})

        try:
            discount_value = Decimal(discount_value_str)
            if discount_value <= 0:
                raise ValueError()
            if discount_type == "percentage" and discount_value > 100:
                messages.error(request, "Percentage discount cannot exceed 100%.")
                return render(request, "adminpanel/admin_coupon_edit.html", {"coupon": coupon})
        except Exception:
            messages.error(request, "Please enter a valid discount value greater than 0.")
            return render(request, "adminpanel/admin_coupon_edit.html", {"coupon": coupon})

        try:
            minimum_order_amount = Decimal(min_order_str) if min_order_str else Decimal("0.00")
            if minimum_order_amount < 0:
                raise ValueError()
        except Exception:
            messages.error(request, "Minimum order amount must be 0 or greater.")
            return render(request, "adminpanel/admin_coupon_edit.html", {"coupon": coupon})

        maximum_discount_amount = None
        if max_discount_str:
            try:
                maximum_discount_amount = Decimal(max_discount_str)
                if maximum_discount_amount <= 0:
                    raise ValueError()
            except Exception:
                messages.error(request, "Maximum discount amount must be greater than 0.")
                return render(request, "adminpanel/admin_coupon_edit.html", {"coupon": coupon})

        valid_from = parse_admin_datetime(valid_from_str, default=coupon.valid_from)
        valid_until = parse_admin_datetime(valid_until_str, default=coupon.valid_until)

        if valid_until <= valid_from:
            messages.error(request, "Valid until date must be after valid from date.")
            return render(request, "adminpanel/admin_coupon_edit.html", {"coupon": coupon})

        usage_limit = int(usage_limit_str) if usage_limit_str else None
        per_user_limit = int(per_user_limit_str) if per_user_limit_str else None
        weekly_user_limit = int(weekly_user_limit_str) if weekly_user_limit_str else 5

        try:
            coupon.code = code
            coupon.description = description
            coupon.discount_type = discount_type
            coupon.discount_value = discount_value
            coupon.minimum_order_amount = minimum_order_amount
            coupon.maximum_discount_amount = maximum_discount_amount
            coupon.valid_from = valid_from
            coupon.valid_until = valid_until
            coupon.usage_limit = usage_limit
            coupon.per_user_limit = per_user_limit
            coupon.weekly_user_limit = weekly_user_limit
            coupon.is_active = is_active
            coupon.save()

            messages.success(request, f"Coupon '{coupon.code}' updated successfully.")
            return redirect("admin_coupons")
        except Exception as e:
            messages.error(request, f"Error updating coupon: {e}")
            return render(request, "adminpanel/admin_coupon_edit.html", {"coupon": coupon})

    return render(request, "adminpanel/admin_coupon_edit.html", {"coupon": coupon})


@staff_perm_required("coupons.view_coupon")
def coupon_detail(request, slug):
    if not request.user.is_staff:
        return redirect("home")

    coupon = get_object_or_404(Coupon, slug=slug)
    usages = coupon.usages.select_related("user", "order").order_by("-used_at")[:100]
    total_discount = coupon.usages.aggregate(total=Sum("discount_amount"))["total"] or Decimal("0.00")
    unique_users_count = coupon.usages.values("user").distinct().count()

    context = {
        "coupon": coupon,
        "usages": usages,
        "total_discount": total_discount,
        "unique_users_count": unique_users_count,
    }
    return render(request, "adminpanel/admin_coupon_detail.html", context)


@staff_perm_required("coupons.change_coupon")
def coupon_toggle(request, slug):
    if not request.user.is_staff:
        return redirect("home")

    coupon = get_object_or_404(Coupon, slug=slug)
    coupon.is_active = not coupon.is_active
    coupon.save(update_fields=["is_active", "updated_at"])

    status_text = "activated" if coupon.is_active else "deactivated"
    messages.success(request, f"Coupon '{coupon.code}' {status_text} successfully.")

    next_url = request.META.get("HTTP_REFERER")
    if next_url:
        return redirect(next_url)
    return redirect("admin_coupons")


@staff_perm_required("coupons.delete_coupon")
def coupon_delete(request, slug):
    if not request.user.is_staff:
        return redirect("home")

    coupon = get_object_or_404(Coupon, slug=slug)
    has_usages = coupon.usages.exists()

    if request.method == "POST":
        if has_usages:
            coupon.is_active = False
            coupon.save(update_fields=["is_active", "updated_at"])
            messages.warning(
                request,
                f"Coupon '{coupon.code}' has historical order usage records and cannot be permanently deleted. It has been deactivated instead."
            )
        else:
            code = coupon.code
            coupon.delete()
            messages.success(request, f"Coupon '{code}' deleted successfully.")
        return redirect("admin_coupons")

    context = {
        "coupon": coupon,
        "has_usages": has_usages,
    }
    return render(request, "adminpanel/admin_coupon_delete.html", context)


@staff_perm_required("coupons.change_coupon")
def coupon_broadcast(request, slug):
    if not request.user.is_staff:
        return redirect("home")

    coupon = get_object_or_404(Coupon, slug=slug)

    if request.method == "POST":
        from apps.accounts.tasks import broadcast_coupon_announcement_task
        broadcast_coupon_announcement_task.delay(coupon.id)
        # print('1111111111111111111')
        messages.success(
            request,
            f"Coupon '{coupon.code}' broadcast has been queued. "
            "Emails are being processed in the background."
        )
        return redirect("admin_coupon_detail", slug=coupon.slug)

    return redirect("admin_coupon_detail", slug=coupon.slug)


# =============================================================================
# STAFF & PERMISSION MANAGEMENT VIEWS
# =============================================================================

@login_required(login_url="login")
def staff_list(request):
    """
    List all staff members and their active permissions.
    Only superadmins can access this view.
    """
    if not request.user.is_superuser:
        messages.error(request, "Access denied. Only superadmins can manage staff permissions.")
        return redirect("admin_dashboard")

    staff_members = User.objects.filter(is_staff=True).prefetch_related("user_permissions").order_by("username")
    return render(request, "adminpanel/admin_staff_list.html", {
        "staff_members": staff_members
    })


@login_required(login_url="login")
def staff_permissions(request, user_id):
    """
    Configure specific permissions for a staff member.
    Only superadmins can access this view.
    """
    if not request.user.is_superuser:
        messages.error(request, "Access denied. Only superadmins can manage staff permissions.")
        return redirect("admin_dashboard")

    staff_user = get_object_or_404(User, id=user_id, is_staff=True)

    store_apps = ["products", "coupons", "order", "chat", "accounts"]
    permissions = (
        Permission.objects
        .filter(content_type__app_label__in=store_apps)
        .select_related("content_type")
        .order_by("content_type__app_label", "name")
    )

    if request.method == "POST":
        selected_perm_ids = request.POST.getlist("permissions")
        staff_user.user_permissions.set(selected_perm_ids)
        messages.success(request, f"Permissions updated successfully for {staff_user.username}.")
        return redirect("admin_staff_list")

    user_perm_ids = set(staff_user.user_permissions.values_list("id", flat=True))

    return render(request, "adminpanel/admin_staff_permissions.html", {
        "staff_user": staff_user,
        "permissions": permissions,
        "user_perm_ids": user_perm_ids,
    })


@login_required(login_url="login")
def staff_add(request):
    """
    Add a new staff member or promote an existing user to staff,
    and grant initial permissions.
    """
    if not request.user.is_superuser:
        messages.error(request, "Access denied. Only superadmins can add staff members.")
        return redirect("admin_dashboard")

    non_staff_users = User.objects.filter(is_staff=False).order_by("username")

    store_apps = ["products", "coupons", "order", "chat", "accounts"]
    permissions = (
        Permission.objects
        .filter(content_type__app_label__in=store_apps)
        .select_related("content_type")
        .order_by("content_type__app_label", "name")
    )

    if request.method == "POST":
        action_type = request.POST.get("action_type", "existing")
        selected_perm_ids = request.POST.getlist("permissions")

        if action_type == "existing":
            user_id = request.POST.get("user_id")
            if not user_id:
                messages.error(request, "Please select an existing user.")
                return redirect("admin_staff_add")

            user = get_object_or_404(User, id=user_id)
            user.is_staff = True
            user.save(update_fields=["is_staff"])
            user.user_permissions.set(selected_perm_ids)
            messages.success(request, f"User '{user.username}' is now a staff member with {len(selected_perm_ids)} permissions.")
            return redirect("admin_staff_list")

        elif action_type == "new":
            username = request.POST.get("username", "").strip()
            email = request.POST.get("email", "").strip().lower()
            password = request.POST.get("password", "")

            if not username or not email or not password:
                messages.error(request, "Username, email, and password are required.")
                return redirect("admin_staff_add")

            if User.objects.filter(username__iexact=username).exists():
                messages.error(request, f"Username '{username}' is already taken.")
                return redirect("admin_staff_add")

            if User.objects.filter(email__iexact=email).exists():
                messages.error(request, f"Email '{email}' is already in use.")
                return redirect("admin_staff_add")

            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                is_staff=True
            )
            user.user_permissions.set(selected_perm_ids)
            messages.success(request, f"Staff member '{user.username}' created successfully with {len(selected_perm_ids)} permissions.")
            return redirect("admin_staff_list")

    return render(request, "adminpanel/admin_staff_add.html", {
        "non_staff_users": non_staff_users,
        "permissions": permissions,
    })


@login_required(login_url="login")
def staff_remove(request, user_id):
    """
    Revoke staff status and permissions from a staff user.
    """
    if not request.user.is_superuser:
        messages.error(request, "Access denied.")
        return redirect("admin_dashboard")

    staff_user = get_object_or_404(User, id=user_id, is_staff=True)
    if staff_user.is_superuser:
        messages.error(request, "Superadmin accounts cannot be demoted.")
        return redirect("admin_staff_list")

    if request.method == "POST":
        staff_user.is_staff = False
        staff_user.user_permissions.clear()
        staff_user.save(update_fields=["is_staff"])
        messages.success(request, f"Staff access revoked for '{staff_user.username}'.")
        return redirect("admin_staff_list")

    return redirect("admin_staff_list")


