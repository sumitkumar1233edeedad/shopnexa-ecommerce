from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

from apps.products.models import (
    Category,
    Color,
    Product,
    ProductVariant,
    Stock,
    Review,
    ProductImage,
)
from apps.accounts.models import WishList
from api_apps.products_api.serializers import (
    CategorySerializer,
    ColorSerializer,
    StockSerializer,
    ProductImageSerializer,
    ReviewSerializer,
    ProductVariantSerializer,
    ProductListSerializer,
    ProductDetailSerializer,
    ProductCreateUpdateSerializer,
)

User = get_user_model()


class ProductSerializersTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username="reviewer",
            email="reviewer@example.com",
            password="Password123!",
            first_name="Review",
            last_name="Author",
        )

        self.category = Category.objects.create(
            name="Laptops",
            slug="laptops",
        )

        self.color = Color.objects.create(
            name="Space Gray",
            hex_code="#535150",
            slug="space-gray",
        )

        self.product = Product.objects.create(
            name="MacBook Pro 16",
            slug="macbook-pro-16",
            brand="Apple",
            description="Apple M3 Max powerful laptop.",
        )
        self.product.cat.add(self.category)

        self.variant = ProductVariant.objects.create(
            product=self.product,
            color=self.color,
            size="1TB SSD",
            sku="MBP16-SG-1TB",
            price=2499.00,
        )

        self.stock = Stock.objects.create(
            variant=self.variant,
            quantity=15,
            reserved_quantity=2,
        )

        self.product_image = ProductImage.objects.create(
            product=self.product,
            image="product/gallery/macbook.jpg",
            alt_text="Front view",
        )

        self.review = Review.objects.create(
            user=self.user,
            product=self.product,
            rating=5,
            product_review="Super fast machine, highly recommended!",
        )

    def test_category_serializer(self):
        serializer = CategorySerializer(self.category)
        data = serializer.data
        self.assertEqual(data["name"], "Laptops")
        self.assertEqual(data["slug"], "laptops")
        self.assertEqual(data["product_count"], 1)

    def test_color_serializer(self):
        serializer = ColorSerializer(self.color)
        data = serializer.data
        self.assertEqual(data["name"], "Space Gray")
        self.assertEqual(data["hex_code"], "#535150")
        self.assertEqual(data["slug"], "space-gray")

    def test_stock_serializer(self):
        serializer = StockSerializer(self.stock)
        data = serializer.data
        self.assertEqual(data["quantity"], 15)
        self.assertEqual(data["reserved_quantity"], 2)
        self.assertEqual(data["available_quantity"], 13)

    def test_product_image_serializer(self):
        serializer = ProductImageSerializer(self.product_image)
        data = serializer.data
        self.assertEqual(data["alt_text"], "Front view")
        self.assertIn("image", data)

    def test_review_serializer(self):
        serializer = ReviewSerializer(self.review)
        data = serializer.data
        self.assertEqual(data["username"], "reviewer")
        self.assertEqual(data["user_full_name"], "Review Author")
        self.assertEqual(data["rating"], 5)
        self.assertEqual(data["product_review"], "Super fast machine, highly recommended!")

    def test_review_serializer_validation(self):
        invalid_data = {
            "product": self.product.id,
            "rating": 6,  # Invalid (> 5)
            "product_review": "Great!",
        }
        serializer = ReviewSerializer(data=invalid_data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("rating", serializer.errors)

    def test_product_variant_serializer(self):
        serializer = ProductVariantSerializer(self.variant)
        data = serializer.data
        self.assertEqual(data["sku"], "MBP16-SG-1TB")
        self.assertEqual(float(data["price"]), 2499.00)
        self.assertTrue(data["is_in_stock"])
        self.assertEqual(data["stock_quantity"], 13)
        self.assertEqual(data["color_details"]["name"], "Space Gray")

    def test_product_list_serializer(self):
        serializer = ProductListSerializer(self.product)
        data = serializer.data
        self.assertEqual(data["name"], "MacBook Pro 16")
        self.assertEqual(data["brand"], "Apple")
        self.assertEqual(float(data["price"]), 2499.00)
        self.assertEqual(float(data["min_price"]), 2499.00)
        self.assertEqual(float(data["max_price"]), 2499.00)
        self.assertTrue(data["in_stock"])
        self.assertEqual(data["average_rating"], 5.0)
        self.assertEqual(data["review_count"], 1)
        self.assertEqual(len(data["cat"]), 1)

    def test_product_detail_serializer(self):
        serializer = ProductDetailSerializer(self.product)
        data = serializer.data
        self.assertEqual(data["name"], "MacBook Pro 16")
        self.assertEqual(data["description"], "Apple M3 Max powerful laptop.")
        self.assertEqual(len(data["variants"]), 1)
        self.assertEqual(len(data["images"]), 1)
        self.assertEqual(len(data["reviews"]), 1)

    def test_product_create_update_serializer(self):
        payload = {
            "name": "iPad Pro M4",
            "brand": "Apple",
            "description": "Thinnest Apple product ever.",
            "cat": [self.category.id],
            "is_active": True,
        }
        serializer = ProductCreateUpdateSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        created_product = serializer.save()
        self.assertEqual(created_product.name, "iPad Pro M4")
        self.assertEqual(created_product.cat.first(), self.category)


class ProductAPITests(TestCase):

    def setUp(self):
        self.client = APIClient()

        self.user = User.objects.create_user(
            username="testuser",
            email="testuser@example.com",
            password="Password123!",
            first_name="Test",
            last_name="User",
        )

        self.admin_user = User.objects.create_user(
            username="adminuser",
            email="admin@example.com",
            password="Password123!",
            first_name="Admin",
            last_name="Staff",
            is_staff=True,
            is_superuser=True,
        )

        self.category = Category.objects.create(
            name="Phones",
            slug="phones",
        )

        self.color = Color.objects.create(
            name="Titanium Black",
            hex_code="#1c1c1e",
            slug="titanium-black",
        )

        self.product = Product.objects.create(
            name="iPhone 16 Pro",
            slug="iphone-16-pro",
            brand="Apple",
            description="A18 Pro chip with Apple Intelligence.",
            is_active=True,
        )
        self.product.cat.add(self.category)

        self.variant = ProductVariant.objects.create(
            product=self.product,
            color=self.color,
            size="256GB",
            sku="IP16P-TB-256",
            price=999.00,
            is_active=True,
        )

        self.stock = Stock.objects.create(
            variant=self.variant,
            quantity=20,
            reserved_quantity=5,
        )

    def test_product_list_api(self):
        response = self.client.get("/api/products/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["total_count"], 1)
        self.assertEqual(len(response.data["products"]), 1)
        self.assertEqual(response.data["products"][0]["name"], "iPhone 16 Pro")

    def test_product_list_search(self):
        # Query that matches
        res_match = self.client.get("/api/products/?q=iPhone")
        self.assertEqual(res_match.status_code, status.HTTP_200_OK)
        self.assertEqual(res_match.data["total_count"], 1)

        # Query that doesn't match
        res_empty = self.client.get("/api/products/?q=SamsungGalaxy")
        self.assertEqual(res_empty.status_code, status.HTTP_200_OK)
        self.assertEqual(res_empty.data["total_count"], 0)

    def test_product_list_category_filter(self):
        res = self.client.get("/api/products/?category=phones")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["total_count"], 1)

        res_other = self.client.get("/api/products/?category=laptops")
        self.assertEqual(res_other.status_code, status.HTTP_200_OK)
        self.assertEqual(res_other.data["total_count"], 0)

    def test_product_list_price_filter(self):
        res_in_range = self.client.get("/api/products/?price=500-1500")
        self.assertEqual(res_in_range.status_code, status.HTTP_200_OK)
        self.assertEqual(res_in_range.data["total_count"], 1)

        res_out_range = self.client.get("/api/products/?price=1500-3000")
        self.assertEqual(res_out_range.status_code, status.HTTP_200_OK)
        self.assertEqual(res_out_range.data["total_count"], 0)

    def test_product_list_sorting(self):
        # Create second product with different price
        p2 = Product.objects.create(name="iPhone SE", slug="iphone-se", brand="Apple")
        v2 = ProductVariant.objects.create(product=p2, sku="IPSE-64", price=429.00)

        res_asc = self.client.get("/api/products/?sort=price_low")
        self.assertEqual(res_asc.status_code, status.HTTP_200_OK)
        self.assertEqual(res_asc.data["products"][0]["name"], "iPhone SE")

        res_desc = self.client.get("/api/products/?sort=price_high")
        self.assertEqual(res_desc.status_code, status.HTTP_200_OK)
        self.assertEqual(res_desc.data["products"][0]["name"], "iPhone 16 Pro")

    def test_product_detail_api(self):
        response = self.client.get(f"/api/products/{self.product.slug}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["product"]["name"], "iPhone 16 Pro")
        self.assertEqual(response.data["selected_variant"]["sku"], "IP16P-TB-256")
        self.assertFalse(response.data["is_wishlisted"])

    def test_product_detail_with_authenticated_user_wishlist(self):
        self.client.force_authenticate(user=self.user)
        WishList.objects.create(user=self.user, product=self.product)

        response = self.client.get(f"/api/products/{self.product.slug}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["is_wishlisted"])

    def test_product_detail_canonical(self):
        response = self.client.get(f"/api/products/{self.product.slug}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["product"]["name"], "iPhone 16 Pro")

    def test_product_detail_not_found(self):
        response = self.client.get("/api/products/non-existent-product/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(response.data["success"])

    def test_submit_review_unauthenticated(self):
        response = self.client.post(
            f"/api/products/{self.product.slug}/reviews/",
            {"rating": 5, "product_review": "Amazing camera!"}
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_submit_review_authenticated(self):
        self.client.force_authenticate(user=self.user)

        # 1. Create review
        res_create = self.client.post(
            f"/api/products/{self.product.slug}/reviews/",
            {"rating": 5, "product_review": "Amazing camera!"}
        )
        self.assertEqual(res_create.status_code, status.HTTP_201_CREATED)
        self.assertTrue(res_create.data["success"])
        self.assertEqual(res_create.data["review"]["rating"], 5)

        # 2. Update review
        res_update = self.client.post(
            f"/api/products/{self.product.slug}/reviews/",
            {"rating": 4, "product_review": "Updated: Battery could be better."}
        )
        self.assertEqual(res_update.status_code, status.HTTP_200_OK)
        self.assertEqual(res_update.data["review"]["rating"], 4)
        self.assertEqual(res_update.data["review"]["product_review"], "Updated: Battery could be better.")

        # 3. List reviews
        res_list = self.client.get(f"/api/products/{self.product.slug}/reviews/")
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_list.data["reviews"]), 1)

        # 4. Delete review
        res_del = self.client.delete(f"/api/products/{self.product.slug}/reviews/")
        self.assertEqual(res_del.status_code, status.HTTP_200_OK)
        self.assertEqual(Review.objects.count(), 0)

    def test_category_list_api(self):
        response = self.client.get("/api/categories/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["categories"][0]["name"], "Phones")

    def test_category_detail_api(self):
        response = self.client.get(f"/api/categories/{self.category.slug}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["products_count"], 1)

    def test_color_list_api(self):
        response = self.client.get("/api/colors/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["colors"][0]["name"], "Titanium Black")

    def test_color_detail_api(self):
        response = self.client.get(f"/api/colors/{self.color.slug}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["color"]["name"], "Titanium Black")
        self.assertEqual(response.data["products_count"], 1)

    def test_color_create_permission_denied_for_normal_user(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post("/api/colors/", {"name": "Neon Pink", "hex_code": "#FF1493"})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_color_crud_for_staff_user(self):
        self.client.force_authenticate(user=self.admin_user)

        # Create
        res_create = self.client.post("/api/colors/", {"name": "Crimson Red", "hex_code": "#DC143C"})
        self.assertEqual(res_create.status_code, status.HTTP_201_CREATED)
        self.assertTrue(res_create.data["success"])
        color_slug = res_create.data["color"]["slug"]

        # Detail
        res_detail = self.client.get(f"/api/colors/{color_slug}/")
        self.assertEqual(res_detail.status_code, status.HTTP_200_OK)
        self.assertEqual(res_detail.data["color"]["hex_code"], "#DC143C")

        # Update / Patch
        res_patch = self.client.patch(f"/api/colors/{color_slug}/", {"name": "Ruby Red", "hex_code": "#9B111E"})
        self.assertEqual(res_patch.status_code, status.HTTP_200_OK)
        self.assertEqual(res_patch.data["color"]["name"], "Ruby Red")

        # Delete
        res_del = self.client.delete(f"/api/colors/{color_slug}/")
        self.assertEqual(res_del.status_code, status.HTTP_200_OK)
        self.assertFalse(Color.objects.filter(slug=color_slug).exists())

    def test_category_create_permission_denied_for_normal_user(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post("/api/categories/", {"name": "Tablets"})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_category_crud_for_staff_user(self):
        self.client.force_authenticate(user=self.admin_user)

        # Create
        res_create = self.client.post("/api/categories/", {"name": "Tablets"})
        self.assertEqual(res_create.status_code, status.HTTP_201_CREATED)
        self.assertTrue(res_create.data["success"])
        cat_slug = res_create.data["category"]["slug"]

        # Update / Patch
        res_patch = self.client.patch(f"/api/categories/{cat_slug}/", {"name": "iPads & Tablets"})
        self.assertEqual(res_patch.status_code, status.HTTP_200_OK)
        self.assertEqual(res_patch.data["category"]["name"], "iPads & Tablets")

        # Delete
        res_del = self.client.delete(f"/api/categories/{cat_slug}/")
        self.assertEqual(res_del.status_code, status.HTTP_200_OK)
        self.assertFalse(Category.objects.filter(slug=cat_slug).exists())

    def test_product_create_permission_denied_for_normal_user(self):
        self.client.force_authenticate(user=self.user)
        payload = {"name": "Hacked Product", "brand": "Bad"}
        res = self.client.post("/api/products/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_and_update_product_api(self):
        self.client.force_authenticate(user=self.admin_user)

        # Create
        payload = {
            "name": "AirPods Pro 2",
            "brand": "Apple",
            "description": "Active noise cancellation.",
            "cat": [self.category.id],
        }
        res_create = self.client.post("/api/products/", payload, format="json")
        self.assertEqual(res_create.status_code, status.HTTP_201_CREATED)
        self.assertTrue(res_create.data["success"])
        created_slug = res_create.data["product"]["slug"]

        # Update
        res_patch = self.client.patch(f"/api/products/{created_slug}/", {"brand": "Apple Inc."}, format="json")
        self.assertEqual(res_patch.status_code, status.HTTP_200_OK)
        self.assertEqual(res_patch.data["product"]["brand"], "Apple Inc.")

        # Deactivate / Delete
        res_del = self.client.delete(f"/api/products/{created_slug}/")
        self.assertEqual(res_del.status_code, status.HTTP_200_OK)
        self.assertFalse(Product.objects.filter(slug=created_slug).exists())

    def test_create_product_with_cat_slug_in_body(self):
        self.client.force_authenticate(user=self.admin_user)
        payload = {
            "name": "Google Pixel 9",
            "brand": "Google",
            "cat_slug": "phones",
        }
        res = self.client.post("/api/products/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        p = Product.objects.get(slug=res.data["product"]["slug"])
        self.assertEqual(p.cat.first(), self.category)

    def test_create_product_with_cat_slug_in_query_param(self):
        self.client.force_authenticate(user=self.admin_user)
        payload = {
            "name": "Google Pixel 9 Pro",
            "brand": "Google",
        }
        res = self.client.post("/api/products/?cat_slug=phones", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        p = Product.objects.get(slug=res.data["product"]["slug"])
        self.assertEqual(p.cat.first(), self.category)

    def test_create_product_with_invalid_cat_slug(self):
        self.client.force_authenticate(user=self.admin_user)
        payload = {
            "name": "Bad Product",
            "brand": "Unknown",
            "cat_slug": "non-existent-category-slug",
        }
        res = self.client.post("/api/products/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("cat_slug", res.data["errors"])
