from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.db.models import Q, Sum, Min
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

from .models import *
from apps.accounts.models import *
from apps.cart.models import *
from apps.cart.utils import get_cart_count


def product_list(request):

    products = (
        Product.objects
        .filter(is_active=True)
        .prefetch_related(
            "cat",
            "variants__color",
            "variants__stock"
        )
    )

    categories = Category.objects.all()

    query = request.GET.get("q", "").strip()

    if query:
        products = products.filter(
            Q(name__icontains=query)
            | Q(description__icontains=query)
            | Q(brand__icontains=query)
            | Q(cat__name__icontains=query)
        ).distinct()

    category_slug = request.GET.get("category", "").strip()

    selected_category = None

    if category_slug:
        if category_slug.isdigit():
            selected_category = Category.objects.filter(id=int(category_slug)).first()
        if not selected_category:
            selected_category = Category.objects.filter(slug=category_slug).first()

        if selected_category:
            products = products.filter(
                cat=selected_category
            )

    price_range = request.GET.get("price", "").strip()
    min_price = request.GET.get("min_price", "").strip()
    max_price = request.GET.get("max_price", "").strip()

    if price_range:
        if "-" in price_range:
            try:
                range_min, range_max = map(int, price_range.split("-", 1))
                products = products.filter(
                    variants__price__gte=range_min,
                    variants__price__lte=range_max
                )
            except ValueError:
                pass
        else:
            try:
                products = products.filter(
                    variants__price__gte=int(price_range)
                )
            except ValueError:
                pass

    if min_price:
        try:
            products = products.filter(
                variants__price__gte=float(min_price)
            )
        except (ValueError, TypeError):
            pass

    if max_price:
        try:
            products = products.filter(
                variants__price__lte=float(max_price)
            )
        except (ValueError, TypeError):
            pass

    products = products.distinct()

    sort = (request.GET.get("sort") or request.GET.get("sort_by") or "newest").strip()

    if sort in ["price_low", "low_to_high", "low_to_highest", "lowest_to_highest", "price_asc"]:
        products = (
            products
            .annotate(sort_price=Min("variants__price"))
            .order_by("sort_price", "id")
        )
    elif sort in ["price_high", "high_to_low", "high_to_lowest", "highest_to_lowest", "price_desc"]:
        products = (
            products
            .annotate(sort_price=Min("variants__price"))
            .order_by("-sort_price", "-id")
        )
    elif sort in ["name", "name_asc"]:
        products = products.order_by("name")
    elif sort == "name_desc":
        products = products.order_by("-name")
    else:
        products = products.order_by("-id")

    total_count = products.count()

    # Pagination: 12 products per chunk
    paginator = Paginator(products, 12)
    page_number = request.GET.get("page", 1)

    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        # If AJAX requests a page beyond the end, return empty HTML and has_next=False
        if request.headers.get("x-requested-with") == "XMLHttpRequest" or request.GET.get("ajax") == "1":
            return JsonResponse({
                "html": "",
                "has_next": False,
                "next_page": None,
                "current_page": paginator.num_pages,
                "total_pages": paginator.num_pages,
                "total_count": total_count,
            })
        page_obj = paginator.page(paginator.num_pages)

    wishlist_product_ids = set()

    if request.user.is_authenticated:

        wishlist_product_ids = set(
            WishList.objects
            .filter(user=request.user)
            .values_list("product_id", flat=True)
        )

    cart_count = get_cart_count(request)

    # AJAX chunk pagination handler
    is_ajax = (
        request.headers.get("x-requested-with") == "XMLHttpRequest"
        or request.GET.get("ajax") == "1"
    )

    if is_ajax:
        html = render_to_string(
            "product/partials/product_card.html",
            {
                "products": page_obj,
                "wishlist_product_ids": wishlist_product_ids,
                "request": request,
                "user": request.user,
            },
            request=request
        )
        return JsonResponse({
            "html": html,
            "has_next": page_obj.has_next(),
            "next_page": page_obj.next_page_number() if page_obj.has_next() else None,
            "current_page": page_obj.number,
            "total_pages": paginator.num_pages,
            "total_count": total_count,
        })

    context = {
        "products": page_obj,
        "categories": categories,
        "selected_category": selected_category,
        "query": query,
        "sort": sort,
        "sort_by": sort,
        "selected_price": price_range,
        "min_price": min_price,
        "max_price": max_price,
        "total_count": total_count,
        "wishlist_product_ids": wishlist_product_ids,
        "cart_count": cart_count,
    }

    return render(
        request,
        "product/product_list.html",
        context
    )


def product_detail(request, slug):

    product = get_object_or_404(
        Product.objects.prefetch_related(
            "cat",
            "reviews__user"
        ),
        slug=slug,
        is_active=True
    )

    variants = (
        product.variants
        .filter(is_active=True)
        .select_related(
            "color",
            "stock"
        )
    )

    selected_variant_param = request.GET.get("variant")

    selected_variant = None

    if selected_variant_param:

        selected_variant = variants.filter(
            slug=selected_variant_param
        ).first()

        if not selected_variant and selected_variant_param.isdigit():
            selected_variant = variants.filter(
                id=selected_variant_param
            ).first()

    if not selected_variant:

        selected_variant = variants.first()

    reviews = (
        product.reviews
        .select_related("user")
        .order_by("-id")
    )

    user_has_reviewed = False

    if request.user.is_authenticated:

        user_has_reviewed = reviews.filter(
            user=request.user
        ).exists()

    is_wishlisted = False

    if request.user.is_authenticated:

        is_wishlisted = WishList.objects.filter(
            user=request.user,
            product=product
        ).exists()

    related_products = (
        Product.objects
        .filter(
            cat__in=product.cat.all(),
            is_active=True
        )
        .exclude(id=product.id)
        .distinct()[:4]
    )
    cart_count = get_cart_count(request)

    context = {
        "product": product,
        "variants": variants,
        "selected_variant": selected_variant,
        "reviews": reviews,
        "user_has_reviewed": user_has_reviewed,
        "is_wishlisted": is_wishlisted,
        "related_products": related_products,
        'cart_count':cart_count,
    }

    return render(
        request,
        "product/product_detail.html",
        context
    )


@login_required(login_url="login")
def submit_review(request, slug):

    if request.method != "POST":

        return redirect(
            "product_detail",
            slug=slug
        )

    product = get_object_or_404(
        Product,
        slug=slug
    )

    try:

        rating = int(
            request.POST.get("rating", 5)
        )

        if rating < 1 or rating > 5:
            rating = 5

    except (ValueError, TypeError):

        rating = 5

    review_text = (
        request.POST
        .get("product_review", "")
        .strip()
    )

    review, created = Review.objects.get_or_create(
        user=request.user,
        product=product,
        defaults={
            "rating": rating,
            "product_review": review_text,
        }
    )

    if not created:

        review.rating = rating
        review.product_review = review_text
        review.save()

        messages.success(
            request,
            "Your review has been updated."
        )

    else:

        messages.success(
            request,
            "Thank you for reviewing this product!"
        )

    return redirect(
        "product_detail",
        slug=product.slug
    )


def category_page(request):
    category_param = (request.GET.get("category") or "").strip()

    price_range = request.GET.get(
        "price",
        ""
    ).strip()

    min_price = request.GET.get(
        "min_price",
        ""
    ).strip()

    max_price = request.GET.get(
        "max_price",
        ""
    ).strip()

    query = request.GET.get(
        "q",
        ""
    ).strip()

    sort = (request.GET.get("sort") or request.GET.get("sort_by") or "newest").strip()

    products = (
        Product.objects
        .filter(is_active=True)
        .prefetch_related(
            "cat",
            "variants__color",
            "variants__stock"
        )
    )

    if query:
        products = products.filter(
            Q(name__icontains=query)
            | Q(description__icontains=query)
            | Q(brand__icontains=query)
            | Q(cat__name__icontains=query)
        ).distinct()

    selected_category = None

    if category_param:
        if category_param.isdigit():
            selected_category = (
                Category.objects
                .filter(id=int(category_param))
                .first()
            )
        if not selected_category:
            selected_category = (
                Category.objects
                .filter(slug=category_param)
                .first()
            )

        if selected_category:
            products = products.filter(
                cat=selected_category
            )

    
    # PRICE RANGE
    if price_range:
        if "-" in price_range:
            try:
                range_min, range_max = map(
                    int,
                    price_range.split("-", 1)
                )
                products = products.filter(
                    variants__price__gte=range_min,
                    variants__price__lte=range_max
                )
            except ValueError:
                pass
        else:
            try:
                products = products.filter(
                    variants__price__gte=int(price_range)
                )
            except ValueError:
                pass


    # CUSTOM MIN PRICE
    if min_price:
        try:
            products = products.filter(
                variants__price__gte=float(min_price)
            )
        except (ValueError, TypeError):
            pass


    # CUSTOM MAX PRICE
    if max_price:
        try:
            products = products.filter(
                variants__price__lte=float(max_price)
            )
        except (ValueError, TypeError):
            pass

    products = products.distinct()

    if sort in ["price_low", "low_to_high", "low_to_highest", "lowest_to_highest", "price_asc"]:
        products = (
            products
            .annotate(sort_price=Min("variants__price"))
            .order_by("sort_price", "id")
        )
    elif sort in ["price_high", "high_to_low", "high_to_lowest", "highest_to_lowest", "price_desc"]:
        products = (
            products
            .annotate(sort_price=Min("variants__price"))
            .order_by("-sort_price", "-id")
        )
    elif sort in ["name", "name_asc"]:
        products = products.order_by("name")
    elif sort == "name_desc":
        products = products.order_by("-name")
    else:
        products = products.order_by("-id")

    categories = Category.objects.all()

    wishlist_product_ids = set()

    if request.user.is_authenticated:

        wishlist_product_ids = set(
            WishList.objects
            .filter(user=request.user)
            .values_list(
                "product_id",
                flat=True
            )
        )

    cart_count = get_cart_count(request)

    # # ========================================================
    # # 1 LAKH (100,000) PRODUCTS MOCK FOR PAGINATION TESTING
    # # ========================================================
    # products_list = list(products)
    # if products_list:
    #     mock_multiplier = (100000 // len(products_list)) + 1
    #     products_1lakh = (products_list * mock_multiplier)[:100000]
    # else:
    #     products_1lakh = []

    # ========================================================
    # PAGINATION (12 products per page)
    # ========================================================
    paginator = Paginator(products, 12)
    page_number = request.GET.get("page", 1)

    try:
        products_page = paginator.page(page_number)
    except PageNotAnInteger:
        products_page = paginator.page(1)
    except EmptyPage:
        products_page = paginator.page(paginator.num_pages)

    elided_page_range = paginator.get_elided_page_range(
        products_page.number,
        on_each_side=2,
        on_ends=1
    )

    # Preserve all filter/sort query params for pagination links
    query_params = request.GET.copy()
    if "page" in query_params:
        query_params.pop("page")
    page_querystring = query_params.urlencode()
    if page_querystring:
        page_querystring = "&" + page_querystring

    # Check if request is AJAX (infinite scroll pagination)
    is_ajax = (
        request.headers.get("x-requested-with") == "XMLHttpRequest"
        or request.GET.get("ajax") == "1"
    )

    if is_ajax:
      
        html = render_to_string(
            "product/includes/category_product_items.html",
            {
                "products": products_page,
                "request": request,
            },
            request=request
        )
        return JsonResponse({
            "html": html,
            "has_next": products_page.has_next(),
            "next_page": products_page.next_page_number() if products_page.has_next() else None,
            "current_page": products_page.number,
            "total_pages": paginator.num_pages,
            "total_count": paginator.count,
        })

    context = {
        "products": products_page,
        "categories": categories,
        "selected_category": selected_category,
        "selected_price": price_range,
        "min_price": min_price,
        "max_price": max_price,
        "query": query,
        "sort": sort,
        "sort_by": sort,
        "total_count": paginator.count,
        "wishlist_product_ids": wishlist_product_ids,
        "cart_count": cart_count,
        "elided_page_range": elided_page_range,
        "page_querystring": page_querystring,
    }

    return render(
        request,
        "product/cat.html",
        context
    )
 
