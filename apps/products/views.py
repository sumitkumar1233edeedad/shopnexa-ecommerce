from decimal import Decimal
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.db.models import Q, Sum, Min, Count, Case, When, IntegerField, Prefetch
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

from .models import *
from apps.accounts.models import *
from apps.cart.models import *
from apps.cart.utils import get_cart_count


def get_active_variants_prefetch():
    return Prefetch(
        "variants",
        queryset=ProductVariant.objects.filter(is_active=True).select_related("color", "stock")
    )


def product_list(request):

    products = (
        Product.objects
        .filter(is_active=True)
        .prefetch_related(
            "cat",
            "reviews",
            get_active_variants_prefetch(),
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

    # Pagination: 12 products per chunk
    paginator = Paginator(products, 12)
    total_count = paginator.count
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
            "reviews__user",
            "images",
            get_active_variants_prefetch(),
        ),
        slug=slug,
        is_active=True
    )

    # Use prefetched active variants on product
    variants = [v for v in product.variants.all() if v.is_active]

    selected_variant_param = request.GET.get("variant")

    selected_variant = None

    if selected_variant_param:
        for v in variants:
            if v.slug == selected_variant_param or (selected_variant_param.isdigit() and v.id == int(selected_variant_param)):
                selected_variant = v
                break

    if not selected_variant:
        selected_variant = variants[0] if variants else None

    reviews_list = list(
        product.reviews
        .select_related("user")
        .order_by("-id")
    )

    user_has_reviewed = False

    if request.user.is_authenticated:
        user_has_reviewed = any(r.user_id == request.user.id for r in reviews_list)

    is_wishlisted = False
    wishlist_product_ids = set()
    if request.user.is_authenticated:
        wishlist_product_ids = set(
            WishList.objects
            .filter(user=request.user)
            .values_list("product_id", flat=True)
        )
        is_wishlisted = product.id in wishlist_product_ids

    # 1. Rating Distribution Breakdown (computed in memory from reviews_list)
    total_reviews = len(reviews_list)
    rating_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for r in reviews_list:
        if r.rating in rating_counts:
            rating_counts[r.rating] += 1

    rating_distribution = []
    for star in [5, 4, 3, 2, 1]:
        cnt = rating_counts[star]
        pct = round((cnt / total_reviews) * 100) if total_reviews > 0 else 0
        rating_distribution.append({
            "star": star,
            "count": cnt,
            "percentage": pct,
        })

    # Base queryset for recommendation sections
    base_product_qs = (
        Product.objects
        .filter(is_active=True)
        .exclude(id=product.id)
    )

    # 2. Similar Products (same category, prioritized by same brand, limit 10)
    product_categories = list(product.cat.all())
    related_products = list(
        base_product_qs
        .filter(cat__in=product_categories)
        .annotate(
            same_brand=Case(
                When(brand=product.brand, then=0),
                default=1,
                output_field=IntegerField()
            )
        )
        .order_by("same_brand", "-id")
        .distinct()[:10]
    )

    # 4. Similar with the Same Features (same brand / specs, limit 10)
    similar_by_feature = []
    if product.brand:
        similar_by_feature = list(
            base_product_qs
            .filter(brand__iexact=product.brand)
            .distinct()[:10]
        )

    # 5. Similar in Price Range (+/- 25% of current product price, limit 10)
    similar_by_price = []
    prod_price = product.price
    if prod_price and prod_price > 0:
        min_p = Decimal(str(prod_price)) * Decimal("0.75")
        max_p = Decimal(str(prod_price)) * Decimal("1.25")
        similar_by_price = list(
            base_product_qs
            .filter(variants__price__gte=min_p, variants__price__lte=max_p)
            .distinct()[:10]
        )

    # 6. Recently Viewed Products (stored in session)
    recently_viewed_ids = [
        pid for pid in request.session.get("recently_viewed_product_ids", [])
        if pid != product.id
    ]
    recently_viewed = []
    if recently_viewed_ids:
        rv_map = {
            p.id: p for p in base_product_qs.filter(id__in=recently_viewed_ids[:10])
        }
        recently_viewed = [rv_map[pid] for pid in recently_viewed_ids if pid in rv_map]

    # Consolidated batch prefetch for ALL recommendation carousels:
    # Deduplicates products across carousels to execute ONLY 3 prefetch queries in total
    all_recommended_map = {}
    for p in (related_products + similar_by_feature + similar_by_price + recently_viewed):
        all_recommended_map[p.id] = p

    if all_recommended_map:
        from django.db.models import prefetch_related_objects
        prefetch_related_objects(
            list(all_recommended_map.values()),
            "cat",
            "reviews",
            get_active_variants_prefetch(),
        )
        related_products = [all_recommended_map[p.id] for p in related_products]
        similar_by_feature = [all_recommended_map[p.id] for p in similar_by_feature]
        similar_by_price = [all_recommended_map[p.id] for p in similar_by_price]
        recently_viewed = [all_recommended_map[p.id] for p in recently_viewed]

    # 3. Frequently Bought Together Bundle (computed AFTER batch prefetching so bp.price is in memory)
    bundle_related = list(related_products[:2])
    bundle_products = [product] + bundle_related if len(bundle_related) >= 1 else []
    bundle_total_price = Decimal("0.00")
    for bp in bundle_products:
        p_val = bp.price or Decimal("0.00")
        bundle_total_price += Decimal(str(p_val))
    bundle_discount_price = round(bundle_total_price * Decimal("0.95"), 2)
    bundle_savings = bundle_total_price - bundle_discount_price

    # Update session with current product ID (limit 12)
    session_history = [product.id] + [
        pid for pid in request.session.get("recently_viewed_product_ids", [])
        if pid != product.id
    ]
    request.session["recently_viewed_product_ids"] = session_history[:12]

    # 7. Real Store Coupons & Top Coupon from apps.coupons
    active_coupons = []
    top_coupon = None
    try:
        from apps.coupons.services import get_available_coupons
        prod_amt = Decimal(str(product.price or 0))
        user_obj = request.user if request.user.is_authenticated else None

        # Fetch available coupons once and derive top coupon in memory
        available_coupons = get_available_coupons(user=user_obj, cart_amount=prod_amt)
        qualifying = [
            c for c in available_coupons
            if getattr(c, "qualifies", False) and getattr(c, "estimated_discount", Decimal("0.00")) > Decimal("0.00")
        ]
        top_coupon = max(
            qualifying,
            key=lambda c: (c.estimated_discount, -c.minimum_order_amount)
        ) if qualifying else None

        if not top_coupon and available_coupons:
            top_coupon = max(
                available_coupons,
                key=lambda c: (c.discount_value, -c.minimum_order_amount)
            )

        active_coupons = available_coupons[:4]
    except Exception:
        try:
            from apps.coupons.models import Coupon
            all_active = list(Coupon.objects.filter(
                is_active=True,
                valid_until__gte=timezone.now()
            ).order_by("-discount_value")[:4])
            if all_active:
                top_coupon = all_active[0]
            active_coupons = all_active
        except Exception:
            pass

    cart_count = get_cart_count(request)

    context = {
        "product": product,
        "variants": variants,
        "selected_variant": selected_variant,
        "reviews": reviews_list,
        "total_reviews": total_reviews,
        "rating_distribution": rating_distribution,
        "user_has_reviewed": user_has_reviewed,
        "is_wishlisted": is_wishlisted,
        "wishlist_product_ids": wishlist_product_ids,
        "related_products": related_products,
        "bundle_products": bundle_products,
        "bundle_total_price": bundle_total_price,
        "bundle_discount_price": bundle_discount_price,
        "bundle_savings": bundle_savings,
        "similar_by_feature": similar_by_feature,
        "similar_by_price": similar_by_price,
        "recently_viewed": recently_viewed,
        "top_coupon": top_coupon,
        "best_coupon": top_coupon,
        "active_coupons": active_coupons,
        "cart_count": cart_count,
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
        request.POST.get("product_review")
        or request.POST.get("comment", "")
    ).strip()

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
            "reviews",
            get_active_variants_prefetch(),
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
 
