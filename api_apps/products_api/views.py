from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated, BasePermission
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.db.models import Q, Min
from django.db import transaction

from apps.products.models import (
    Product,
    Category,
    Color,
    Stock,
    Review,
    ProductVariant,
    ProductImage,
)
from apps.accounts.models import WishList
from apps.products.validators import validate_uploaded_image
from .serializers import (
    CategorySerializer,
    ColorSerializer,
    StockSerializer,
    ProductImageSerializer,
    ReviewSerializer,
    ProductVariantSerializer,
    ProductListSerializer,
    ProductDetailSerializer,
    ProductCreateUpdateSerializer,
    ProductSerializer,
)


# =========================================================
# PERMISSION: STAFF OR SUPERUSER ONLY
# =========================================================


class IsStaffOrSuperuser(BasePermission):

    message = "Permission denied. You do not have the required permission."

    def has_permission(self, request, view):

        user = request.user

        # Not logged in
        if not user or not user.is_authenticated:
            return False

        # Superuser → always allowed
        if user.is_superuser:
            return True

        # Staff user → check assigned permission
        if user.is_staff:
            required_permission = getattr(
                view,
                "required_permission",
                None
            )

            if not required_permission:
                return False

            return user.has_perm(required_permission)

        # Normal customer
        return False


# =========================================================
# PRODUCT LIST API VIEW (CATALOG / SEARCH / FILTER / PAGINATION)
# =========================================================

class ProductListAPIView(APIView):
  

    def get_permissions(self):

        if self.request.method == "POST":
            self.required_permission = "products.add_product"
            return [IsStaffOrSuperuser()]

        return [AllowAny()]


    def get(self, request):
        products = (
            Product.objects
            .filter(is_active=True)
            .prefetch_related(
                "cat",
                "variants__color",
                "variants__stock",
            )
        )

        # 1. Search filter
        query = request.GET.get("q", "").strip()
        if query:
            products = products.filter(
                Q(name__icontains=query)
                | Q(description__icontains=query)
                | Q(brand__icontains=query)
                | Q(cat__name__icontains=query)
            ).distinct()

        # 2. Category filter
        category_param = (request.GET.get("category") or request.GET.get("cat") or "").strip()
        if category_param:
            selected_category = None
            if category_param.isdigit():
                selected_category = Category.objects.filter(id=int(category_param)).first()
            if not selected_category:
                selected_category = Category.objects.filter(slug=category_param).first()
            if selected_category:
                products = products.filter(cat=selected_category)
            else:
                products = products.none()

        # 3. Brand filter
        brand = request.GET.get("brand", "").strip()
        if brand:
            products = products.filter(brand__iexact=brand)

        # 4. Color filter
        color_param = (request.GET.get("color") or "").strip()
        if color_param:
            selected_color = None
            if color_param.isdigit():
                selected_color = Color.objects.filter(id=int(color_param)).first()
            if not selected_color:
                selected_color = (
                    Color.objects.filter(slug=color_param).first()
                    or Color.objects.filter(name__iexact=color_param).first()
                )
            if selected_color:
                products = products.filter(variants__color=selected_color)
            else:
                products = products.none()

        # 4. Price range filter
        price_range = request.GET.get("price", "").strip()
        min_price = request.GET.get("min_price", "").strip()
        max_price = request.GET.get("max_price", "").strip()

        if price_range:
            if "-" in price_range:
                try:
                    range_min, range_max = map(float, price_range.split("-", 1))
                    products = products.filter(
                        variants__price__gte=range_min,
                        variants__price__lte=range_max
                    )
                except (ValueError, TypeError):
                    pass
            else:
                try:
                    products = products.filter(
                        variants__price__gte=float(price_range)
                    )
                except (ValueError, TypeError):
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

        # 5. Sorting
        sort = (request.GET.get("sort") or request.GET.get("sort_by") or "newest").strip().lower()

        if sort in ["price_low", "low_to_high", "lowest_to_highest", "price_asc"]:
            products = (
                products
                .annotate(sort_price=Min("variants__price"))
                .order_by("sort_price", "id")
            )
        elif sort in ["price_high", "high_to_low", "highest_to_lowest", "price_desc"]:
            products = (
                products
                .annotate(sort_price=Min("variants__price"))
                .order_by("-sort_price", "-id")
            )
        elif sort in ["name", "name_asc"]:
            products = products.order_by("name")
        elif sort in ["name_desc"]:
            products = products.order_by("-name")
        else:
            products = products.order_by("-id")

        total_count = products.count()

        # 6. Pagination
        try:
            page_size = int(request.GET.get("page_size", 12))
            if page_size < 1:
                page_size = 12
            elif page_size > 100:
                page_size = 100
        except (ValueError, TypeError):
            page_size = 12

        paginator = Paginator(products, page_size)
        page_number = request.GET.get("page", 1)

        try:
            page_obj = paginator.page(page_number)
        except PageNotAnInteger:
            page_obj = paginator.page(1)
        except EmptyPage:
            page_obj = paginator.page(paginator.num_pages) if paginator.num_pages > 0 else []

        # 7. Wishlist IDs for authenticated users
        wishlist_product_ids = []
        if request.user.is_authenticated:
            wishlist_product_ids = list(
                WishList.objects
                .filter(user=request.user)
                .values_list("product_id", flat=True)
            )

        serializer = ProductListSerializer(
            page_obj,
            many=True,
            context={"request": request}
        )

        return Response(
            {
                "success": True,
                "total_count": total_count,
                "total_pages": paginator.num_pages,
                "current_page": page_obj.number if hasattr(page_obj, "number") else 1,
                "page_size": page_size,
                "has_next": page_obj.has_next() if hasattr(page_obj, "has_next") else False,
                "has_previous": page_obj.has_previous() if hasattr(page_obj, "has_previous") else False,
                "next_page": page_obj.next_page_number() if hasattr(page_obj, "has_next") and page_obj.has_next() else None,
                "previous_page": page_obj.previous_page_number() if hasattr(page_obj, "has_previous") and page_obj.has_previous() else None,
                "wishlist_product_ids": wishlist_product_ids,
                "products": serializer.data,
            },
            status=status.HTTP_200_OK
        )

    def post(self, request):
        data = request.data.copy() if hasattr(request.data, "copy") else dict(request.data)

        # Support category slug passed via query parameter (e.g. POST /api/products/?cat_slug=phones)
        cat_slug_query = (
            request.GET.get("cat_slug")
            or request.GET.get("category_slug")
            or request.GET.get("category")
            or request.GET.get("cat")
        )
        if cat_slug_query and not any(k in data for k in ["cat", "cat_slug", "category", "category_slug"]):
            data["cat_slug"] = cat_slug_query

        serializer = ProductCreateUpdateSerializer(
            data=data,
            context={"request": request}
        )
        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "message": "Product creation failed.",
                    "errors": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        product = serializer.save()
        return Response(
            {
                "success": True,
                "message": "Product created successfully.",
                "product": ProductDetailSerializer(
                    product,
                    context={"request": request}
                ).data,
            },
            status=status.HTTP_201_CREATED
        )


# =========================================================
# PRODUCT DETAIL API VIEW (FULL DETAILS / VARIANTS / RELATED)
# =========================================================

class ProductDetailAPIView(APIView):
    
    def get_permissions(self):

        if self.request.method == "PUT":
            self.required_permission = "products.change_product"
            return [IsStaffOrSuperuser()]

        if self.request.method == "PATCH":
            self.required_permission = "products.change_product"
            return [IsStaffOrSuperuser()]

        if self.request.method == "DELETE":
            self.required_permission = "products.delete_product"
            return [IsStaffOrSuperuser()]

       
        return [AllowAny()]

    def _get_product(self, slug, active_only=True):
        qs = Product.objects.all()
        if active_only:
            qs = qs.filter(is_active=True)
        product = (
            qs
            .filter(slug=str(slug))
            .prefetch_related(
                "cat",
                "images",
                "reviews__user",
                "variants__color",
                "variants__stock",
            )
            .first()
        )
        if not product and str(slug).isdigit():
            product = (
                qs
                .filter(id=int(slug))
                .prefetch_related(
                    "cat",
                    "images",
                    "reviews__user",
                    "variants__color",
                    "variants__stock",
                )
                .first()
            )
        return product

    def get(self, request, slug):
        product = self._get_product(slug, active_only=True)
        if not product:
            return Response(
                {
                    "success": False,
                    "message": "Product not found.",
                },
                status=status.HTTP_404_NOT_FOUND
            )

        variants = product.variants.filter(is_active=True).select_related("color", "stock")

        # Check variant selection
        selected_variant_param = request.GET.get("variant", "").strip()
        selected_variant = None
        if selected_variant_param:
            selected_variant = variants.filter(slug=selected_variant_param).first()
            if not selected_variant and selected_variant_param.isdigit():
                selected_variant = variants.filter(id=int(selected_variant_param)).first()

        if not selected_variant:
            selected_variant = variants.first()

        # Wishlist status & review status
        is_wishlisted = False
        user_has_reviewed = False
        if request.user.is_authenticated:
            is_wishlisted = WishList.objects.filter(
                user=request.user,
                product=product
            ).exists()
            user_has_reviewed = product.reviews.filter(
                user=request.user
            ).exists()

        # Related products
        related_products = (
            Product.objects
            .filter(
                cat__in=product.cat.all(),
                is_active=True
            )
            .exclude(id=product.id)
            .distinct()[:4]
        )

        return Response(
            {
                "success": True,
                "product": ProductDetailSerializer(
                    product,
                    context={"request": request}
                ).data,
                "selected_variant": ProductVariantSerializer(
                    selected_variant,
                    context={"request": request}
                ).data if selected_variant else None,
                "is_wishlisted": is_wishlisted,
                "user_has_reviewed": user_has_reviewed,
                "related_products": ProductListSerializer(
                    related_products,
                    many=True,
                    context={"request": request}
                ).data,
            },
            status=status.HTTP_200_OK
        )

    def put(self, request, slug):
        return self.patch(request, slug)

    def patch(self, request, slug):
        product = self._get_product(slug, active_only=False)
        if not product:
            return Response(
                {
                    "success": False,
                    "message": "Product not found.",
                },
                status=status.HTTP_404_NOT_FOUND
            )

        data = request.data.copy() if hasattr(request.data, "copy") else dict(request.data)
        cat_slug_query = (
            request.GET.get("cat_slug")
            or request.GET.get("category_slug")
            or request.GET.get("category")
            or request.GET.get("cat")
        )
        if cat_slug_query and not any(k in data for k in ["cat", "cat_slug", "category", "category_slug"]):
            data["cat_slug"] = cat_slug_query

        serializer = ProductCreateUpdateSerializer(
            product,
            data=data,
            partial=True,
            context={"request": request}
        )
        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "message": "Product update failed.",
                    "errors": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        updated_product = serializer.save()
        return Response(
            {
                "success": True,
                "message": "Product updated successfully.",
                "product": ProductDetailSerializer(
                    updated_product,
                    context={"request": request}
                ).data,
            },
            status=status.HTTP_200_OK
        )

    def delete(self, request, slug):
        product = self._get_product(slug, active_only=False)
        if not product:
            return Response(
                {
                    "success": False,
                    "message": "Product not found.",
                },
                status=status.HTTP_404_NOT_FOUND
            )

        product_name = product.name
        product.delete()    
        return Response(
            {
                "success": True,
                "message": f"Product '{product_name}' deleted successfully.",
            },
            status=status.HTTP_200_OK
        )


# =========================================================
# PRODUCT REVIEWS API VIEW (LIST / SUBMIT / DELETE REVIEWS)
# =========================================================

class ProductReviewAPIView(APIView):
    """
    Product Review API

    GET:
    - List all reviews for product
    - Include summary, rating breakdown, user's own review

    POST:
    - Submit or update review for product (requires IsAuthenticated)
    - Accepts rating (1-5), product_review, optional image

    DELETE:
    - Delete user's own review for product
    """

    def get_permissions(self):
        if self.request.method == "GET":
            return [AllowAny()]

        elif self.request.method == "DELETE":
            return [IsStaffOrSuperuser()]

         
        return [IsAuthenticated()]

    def _get_product(self, slug):
        product = Product.objects.filter(slug=str(slug), is_active=True).first()
        if not product and str(slug).isdigit():
            product = Product.objects.filter(id=int(slug), is_active=True).first()
        return product

    def get(self, request, slug):
        product = self._get_product(slug)
        if not product:
            return Response(
                {
                    "success": False,
                    "message": "Product not found.",
                },
                status=status.HTTP_404_NOT_FOUND
            )

        reviews = product.reviews.select_related("user").order_by("-id")
        user_review = None
        if request.user.is_authenticated:
            user_review = reviews.filter(user=request.user).first()

        return Response(
            {
                "success": True,
                "product_name": product.name,
                "product_slug": product.slug,
                "average_rating": product.average_rating,
                "review_count": product.review_count,
                "user_has_reviewed": user_review is not None,
                "user_review": ReviewSerializer(user_review, context={"request": request}).data if user_review else None,
                "reviews": ReviewSerializer(reviews, many=True, context={"request": request}).data,
            },
            status=status.HTTP_200_OK
        )

    def post(self, request, slug):
        product = self._get_product(slug)
        if not product:
            return Response(         
                {
                    "success": False,
                    "message": "Product not found.",
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # Rating validation
        raw_rating = request.data.get("rating", 5)
        try:
            rating = int(raw_rating)
            if rating < 1 or rating > 5:
                return Response(
                    {
                        "success": False,
                        "message": "Rating must be between 1 and 5.",
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
        except (ValueError, TypeError):
            return Response(
                {
                    "success": False,
                    "message": "Invalid rating format.",
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        review_text = (
            request.data.get("product_review")
            or request.data.get("review")
            or request.data.get("comment", "")
        ).strip()

        image = request.FILES.get("image") or request.data.get("image")
        if image and hasattr(image, "read"):
            is_valid, error = validate_uploaded_image(image)
            if not is_valid:
                return Response(
                    {
                        "success": False,
                        "message": error,
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

        review, created = Review.objects.get_or_create(
            user=request.user,
            product=product,
            defaults={
                "rating": rating,
                "product_review": review_text,
                "image": image if hasattr(image, "read") else None,
            }
        )

        if not created:
            review.rating = rating
            review.product_review = review_text
            if hasattr(image, "read"):
                review.image = image
            review.save()
            message = "Your review has been updated."
        else:
            message = "Thank you for reviewing this product!"

        return Response(
            {
                "success": True,
                "message": message,
                "created": created,
                "review": ReviewSerializer(
                    review,
                    context={"request": request}
                ).data,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )

    def delete(self, request, slug):
        product = self._get_product(slug)
        if not product:
            return Response(
                {
                    "success": False,
                    "message": "Product not found.",
                },
                status=status.HTTP_404_NOT_FOUND
            )

        review = Review.objects.filter(user=request.user, product=product).first()
        if not review:
            return Response(
                {
                    "success": False,
                    "message": "Review not found.",
                },
                status=status.HTTP_404_NOT_FOUND
            )

        review.delete()
        return Response(
            {
                "success": True,
                "message": "Your review has been deleted.",
            },
            status=status.HTTP_200_OK
        )


# =========================================================
# CATEGORY API VIEWS
# =========================================================

class CategoryListAPIView(APIView):
    """
    Categories API

    GET:
    - List all categories with active product count

    POST:
    - Create category (authenticated)
    """

    def get_permissions(self):

        if self.request.method == "POST":
            self.required_permission = "products.add_category"
            return [IsStaffOrSuperuser()]

        return [AllowAny()]

    def get(self, request):
        categories = Category.objects.all().order_by("name")
        serializer = CategorySerializer(
            categories,
            many=True,
            context={"request": request}
        )
        return Response(
            {
                "success": True,
                "count": categories.count(),
                "categories": serializer.data,
            },
            status=status.HTTP_200_OK
        )

    def post(self, request):
        serializer = CategorySerializer(
            data=request.data,
            context={"request": request}
        )
        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "message": "Category creation failed.",
                    "errors": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        category = serializer.save()
        return Response(
            {
                "success": True,
                "message": "Category created successfully.",
                "category": CategorySerializer(
                    category,
                    context={"request": request}
                ).data,
            },
            status=status.HTTP_201_CREATED
        )


class CategoryDetailAPIView(APIView):
    """
    Category Detail API

    GET:
    - Get category info and active products under this category

    PUT / PATCH:
    - Update category (staff/superuser only)

    DELETE:
    - Delete category (staff/superuser only)
    """

    def get_permissions(self):

        if self.request.method in ["PUT", "PATCH"]:
            self.required_permission = "products.change_category"
            return [IsStaffOrSuperuser()]

        if self.request.method == "DELETE":
            self.required_permission = "products.delete_category"
            return [IsStaffOrSuperuser()]

        return [AllowAny()]

    def _get_category(self, slug):
        category = Category.objects.filter(slug=str(slug)).first()
        if not category and str(slug).isdigit():
            category = Category.objects.filter(id=int(slug)).first()
        return category

    def get(self, request, slug):
        category = self._get_category(slug)
        if not category:
            return Response(
                {
                    "success": False,
                    "message": "Category not found.",
                },
                status=status.HTTP_404_NOT_FOUND
            )

        products = (
            Product.objects
            .filter(cat=category, is_active=True)
            .prefetch_related(
                "cat",
                "variants__color",
                "variants__stock",
            )
            .distinct()
        )

        return Response(
            {
                "success": True,
                "category": CategorySerializer(
                    category,
                    context={"request": request}
                ).data,
                "products_count": products.count(),
                "products": ProductListSerializer(
                    products,
                    many=True,
                    context={"request": request}
                ).data,
            },
            status=status.HTTP_200_OK
        )

    def put(self, request, slug):
        return self.patch(request, slug)

    def patch(self, request, slug):
        category = self._get_category(slug)
        if not category:
            return Response(
                {
                    "success": False,
                    "message": "Category not found.",
                },
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = CategorySerializer(
            category,
            data=request.data,
            partial=True,
            context={"request": request}
        )
        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "message": "Category update failed.",
                    "errors": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        updated_category = serializer.save()
        return Response(
            {
                "success": True,
                "message": "Category updated successfully.",
                "category": CategorySerializer(
                    updated_category,
                    context={"request": request}
                ).data,
            },
            status=status.HTTP_200_OK
        )

    def delete(self, request, slug):
        category = self._get_category(slug)
        if not category:
            return Response(
                {
                    "success": False,
                    "message": "Category not found.",
                },
                status=status.HTTP_404_NOT_FOUND
            )

        cat_name = category.name
        category.delete()
        return Response(
            {
                "success": True,
                "message": f"Category '{cat_name}' deleted successfully.",
            },
            status=status.HTTP_200_OK
        )

 
class ColorListAPIView(APIView):
     

    def get_permissions(self):

        if self.request.method == "POST":
            self.required_permission = "products.add_color"
            return [IsStaffOrSuperuser()]

        return [AllowAny()]

    def get(self, request):
        colors = Color.objects.all().order_by("name")
        return Response(
            {
                "success": True,
                "count": colors.count(),
                "colors": ColorSerializer(
                    colors,
                    many=True,
                    context={"request": request}
                ).data,
            },
            status=status.HTTP_200_OK
        )

    def post(self, request):
        serializer = ColorSerializer(
            data=request.data,
            context={"request": request}
        )
        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "message": "Color creation failed.",
                    "errors": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        color = serializer.save()
        return Response(
            {
                "success": True,
                "message": f"Color '{color.name}' created successfully.",
                "color": ColorSerializer(
                    color,
                    context={"request": request}
                ).data,
            },
            status=status.HTTP_201_CREATED
        )

 
class ColorDetailAPIView(APIView):
     

    def get_permissions(self):

        if self.request.method in ["PUT", "PATCH"]:
            self.required_permission = "products.change_color"
            return [IsStaffOrSuperuser()]

        if self.request.method == "DELETE":
            self.required_permission = "products.delete_color"
            return [IsStaffOrSuperuser()]

        return [AllowAny()]

    def _get_color(self, slug):
        color = Color.objects.filter(slug=str(slug)).first()
        if not color and str(slug).isdigit():
            color = Color.objects.filter(id=int(slug)).first()
        return color

    def get(self, request, slug):
        color = self._get_color(slug)
        if not color:
            return Response(
                {
                    "success": False,
                    "message": "Color not found.",
                },
                status=status.HTTP_404_NOT_FOUND
            )

        products = (
            Product.objects
            .filter(variants__color=color, is_active=True)
            .prefetch_related(
                "cat",
                "variants__color",
                "variants__stock",
            )
            .distinct()
        )

        return Response(
            {
                "success": True,
                "color": ColorSerializer(
                    color,
                    context={"request": request}
                ).data,
                "products_count": products.count(),
                "products": ProductListSerializer(
                    products,
                    many=True,
                    context={"request": request}
                ).data,
            },
            status=status.HTTP_200_OK
        )

    def put(self, request, slug):
        return self.patch(request, slug)

    def patch(self, request, slug):
        color = self._get_color(slug)
        if not color:
            return Response(
                {
                    "success": False,
                    "message": "Color not found.",
                },
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = ColorSerializer(
            color,
            data=request.data,
            partial=True,
            context={"request": request}
        )
        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "message": "Color update failed.",
                    "errors": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        updated_color = serializer.save()
        return Response(
            {
                "success": True,
                "message": f"Color '{updated_color.name}' updated successfully.",
                "color": ColorSerializer(
                    updated_color,
                    context={"request": request}
                ).data,
            },
            status=status.HTTP_200_OK
        )

    def delete(self, request, slug):
        color = self._get_color(slug)
        if not color:
            return Response(
                {
                    "success": False,
                    "message": "Color not found.",
                },
                status=status.HTTP_404_NOT_FOUND
            )

        name = color.name
        color.delete()
        return Response(
            {
                "success": True,
                "message": f"Color '{name}' deleted successfully.",
            },
            status=status.HTTP_200_OK
        )

