from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

from apps.products.models import Product, ProductVariant, Category, Color, Stock
from apps.cart.models import Cart, CartItem

User = get_user_model()


class CartAPITests(TestCase):

    def setUp(self):
        self.client = APIClient()

        self.user = User.objects.create_user(
            username="cartuser",
            email="cartuser@example.com",
            password="Password123!",
            first_name="Cart",
            last_name="Tester",
        )

        self.category = Category.objects.create(name="Phones", slug="phones")
        self.color = Color.objects.create(name="Midnight Black", hex_code="#000000", slug="midnight-black")

        self.product = Product.objects.create(
            name="iPhone 16",
            slug="iphone-16",
            brand="Apple",
            description="Next-gen smartphone",
        )
        self.product.cat.add(self.category)

        self.variant = ProductVariant.objects.create(
            product=self.product,
            color=self.color,
            size="128GB",
            sku="IPHONE-16-BLK-128",
            slug="iphone-16-black-128",
            price=Decimal("999.00"),
            is_active=True,
        )

        self.stock = Stock.objects.create(
            variant=self.variant,
            quantity=10,
        )

    # =========================================================
    # GUEST (SESSION) CART TESTS
    # =========================================================

    def test_guest_empty_cart_get(self):
        res = self.client.get("/api/cart/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["success"])
        self.assertEqual(res.data["cart"]["total_items"], 0)
        self.assertEqual(len(res.data["cart"]["items"]), 0)

    def test_guest_add_to_cart_and_get(self):
        # 1. Add item
        payload = {"variant_slug": self.variant.slug, "quantity": 2}
        res_add = self.client.post("/api/cart/", payload, format="json")
        self.assertEqual(res_add.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_add.data["cart"]["total_items"], 2)
        self.assertEqual(res_add.data["cart"]["subtotal"], "1998.00")

        # 2. Get cart
        res_get = self.client.get("/api/cart/")
        self.assertEqual(res_get.status_code, status.HTTP_200_OK)
        self.assertEqual(res_get.data["cart"]["total_items"], 2)
        self.assertEqual(len(res_get.data["cart"]["items"]), 1)
        self.assertEqual(res_get.data["cart"]["items"][0]["variant_slug"], self.variant.slug)

    def test_guest_increase_and_decrease_quantity(self):
        # Add initial item
        self.client.post("/api/cart/", {"variant_slug": self.variant.slug, "quantity": 2}, format="json")

        # Increase
        res_inc = self.client.patch(
            f"/api/cart/items/{self.variant.slug}/",
            {"action": "increase"},
            format="json"
        )
        self.assertEqual(res_inc.status_code, status.HTTP_200_OK)
        self.assertEqual(res_inc.data["cart"]["total_items"], 3)

        # Decrease
        res_dec = self.client.patch(
            f"/api/cart/items/{self.variant.slug}/",
            {"action": "decrease"},
            format="json"
        )
        self.assertEqual(res_dec.status_code, status.HTTP_200_OK)
        self.assertEqual(res_dec.data["cart"]["total_items"], 2)

    def test_guest_remove_item_and_clear_cart(self):
        self.client.post("/api/cart/", {"variant_slug": self.variant.slug, "quantity": 2}, format="json")

        # Remove single item
        res_del_item = self.client.delete(f"/api/cart/items/{self.variant.slug}/")
        self.assertEqual(res_del_item.status_code, status.HTTP_200_OK)
        self.assertEqual(res_del_item.data["cart"]["total_items"], 0)

        # Add again then clear whole cart
        self.client.post("/api/cart/", {"variant_slug": self.variant.slug, "quantity": 1}, format="json")
        res_clear = self.client.delete("/api/cart/")
        self.assertEqual(res_clear.status_code, status.HTTP_200_OK)
        self.assertEqual(res_clear.data["cart"]["total_items"], 0)

    # =========================================================
    # AUTHENTICATED USER CART TESTS
    # =========================================================

    def test_authenticated_user_cart_flow(self):
        self.client.force_authenticate(user=self.user)

        # 1. Add item
        payload = {"variant_slug": self.variant.slug, "quantity": 1}
        res_add = self.client.post("/api/cart/", payload, format="json")
        self.assertEqual(res_add.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_add.data["cart"]["total_items"], 1)

        # Verify DB model
        cart_obj = Cart.objects.get(user=self.user)
        self.assertEqual(cart_obj.items.count(), 1)
        self.assertEqual(cart_obj.items.first().quantity, 1)

        # 2. Set explicit quantity
        res_set = self.client.patch(
            f"/api/cart/items/{self.variant.slug}/",
            {"quantity": 4},
            format="json"
        )
        self.assertEqual(res_set.status_code, status.HTTP_200_OK)
        self.assertEqual(res_set.data["cart"]["total_items"], 4)
        self.assertEqual(res_set.data["cart"]["subtotal"], "3996.00")

        # 3. Clear cart
        res_clear = self.client.delete("/api/cart/")
        self.assertEqual(res_clear.status_code, status.HTTP_200_OK)
        self.assertEqual(cart_obj.items.count(), 0)

    # =========================================================
    # VALIDATION & OUT OF STOCK TESTS
    # =========================================================

    def test_add_non_existent_variant_returns_404(self):
        res = self.client.post("/api/cart/", {"variant_slug": "non-existent-slug"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_add_quantity_exceeding_stock_fails(self):
        res = self.client.post(
            "/api/cart/",
            {"variant_slug": self.variant.slug, "quantity": 999},
            format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("available in stock", res.data["message"])
