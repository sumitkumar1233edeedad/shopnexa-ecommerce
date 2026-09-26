import json
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.products.models import Product, ProductVariant, Category, Stock
from apps.cart.models import Cart, CartItem
from apps.accounts.models import WishList
from apps.order.models import Order, OrderItem

from ai.context import set_current_user, reset_current_user
from ai.tools.products import (
    search_products,
    get_product_details,
    check_stock,
    get_product_price,
    search_category,
    search_by_brand,
    search_by_price,
)
from ai.tools.cart import (
    get_cart,
    add_to_cart,
    remove_from_cart,
    update_cart,
)
from ai.tools.wishlist import (
    get_wishlist,
    add_to_wishlist,
    remove_from_wishlist,
    check_wishlist,
)
from ai.tools.orders import (
    get_orders,
    get_order_details,
    get_order_status,
)

User = get_user_model()


class ShoppingToolsComprehensiveTestCase(TestCase):
    """
    Comprehensive tests for all 17 LangChain tools across Product, Cart, Wishlist, and Order domains.
    Validates structured response contracts, stock checking, and user isolation.
    """

    def setUp(self):
        # Users
        self.user_a = User.objects.create_user(
            username="user_a",
            email="usera@example.com",
            password="Password123!",
            is_email_verified=True,
            is_activated=True,
        )
        self.user_b = User.objects.create_user(
            username="user_b",
            email="userb@example.com",
            password="Password123!",
            is_email_verified=True,
            is_activated=True,
        )

        # Category & Products
        self.category = Category.objects.create(name="Running Shoes", slug="running-shoes")

        self.product = Product.objects.create(
            name="Nike Air Max 2026",
            slug="nike-air-max-2026",
            brand="Nike",
            description="High performance athletic running sneakers.",
            is_active=True,
        )
        self.product.cat.add(self.category)

        self.variant = ProductVariant.objects.create(
            product=self.product,
            sku="NK-AM26-BLK-42",
            slug="nike-air-max-2026-black-42",
            price=Decimal("120.00"),
            size="42",
            is_active=True,
        )
        self.stock = Stock.objects.create(
            variant=self.variant,
            quantity=10,
            reserved_quantity=2,  # Available = 8
        )

        self.product_adidas = Product.objects.create(
            name="Adidas Ultraboost",
            slug="adidas-ultraboost",
            brand="Adidas",
            description="Everyday running sneakers with boost foam.",
            is_active=True,
        )
        self.product_adidas.cat.add(self.category)

        self.variant_adidas = ProductVariant.objects.create(
            product=self.product_adidas,
            sku="AD-UB-WHT-41",
            slug="adidas-ultraboost-white-41",
            price=Decimal("180.00"),
            size="41",
            is_active=True,
        )
        self.stock_adidas = Stock.objects.create(
            variant=self.variant_adidas,
            quantity=5,
            reserved_quantity=0,  # Available = 5
        )

        # Orders for User A and User B
        self.order_a = Order.objects.create(
            user=self.user_a,
            order_number="ORD-A1001",
            slug="order-ord-a1001",
            total_amount=Decimal("240.00"),
            status="confirmed",
            shipping_name="User A",
            shipping_address="123 Alpha Street",
            shipping_city="Metropolis",
            shipping_pincode="110001",
        )
        OrderItem.objects.create(
            order=self.order_a,
            variant=self.variant,
            quantity=2,
            price=Decimal("120.00"),
            slug="ord-a1001-item-1",
        )

        self.order_b = Order.objects.create(
            user=self.user_b,
            order_number="ORD-B2002",
            slug="order-ord-b2002",
            total_amount=Decimal("180.00"),
            status="shipped",
            shipping_name="User B",
            shipping_address="456 Beta Avenue",
            shipping_city="Gotham",
            shipping_pincode="220002",
        )
        OrderItem.objects.create(
            order=self.order_b,
            variant=self.variant_adidas,
            quantity=1,
            price=Decimal("180.00"),
            slug="ord-b2002-item-1",
        )

    # =========================================================================
    # PRODUCT TOOLS
    # =========================================================================
    def test_search_products(self):
        """Test search_products returns structured results with success flag."""
        res_raw = search_products.invoke({"query": "Nike"})
        data = json.loads(res_raw)
        self.assertTrue(data.get("success"))
        self.assertIn("results", data)
        self.assertGreaterEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["slug"], "nike-air-max-2026")

        # Empty search query returns structured error
        empty_res = json.loads(search_products.invoke({"query": ""}))
        self.assertFalse(empty_res.get("success"))
        self.assertIn("error", empty_res)

    def test_get_product_details(self):
        """Test get_product_details returns comprehensive product and variant data."""
        res_raw = get_product_details.invoke({"product_slug": "nike-air-max-2026"})
        data = json.loads(res_raw)
        self.assertTrue(data.get("success"))
        self.assertEqual(data["name"], "Nike Air Max 2026")
        self.assertEqual(data["brand"], "Nike")
        self.assertEqual(len(data["variants"]), 1)
        self.assertEqual(data["variants"][0]["available_stock"], 8)

        # Non-existent slug returns structured error
        missing = json.loads(get_product_details.invoke({"product_slug": "non-existent-item"}))
        self.assertFalse(missing.get("success"))
        self.assertIn("error", missing)

    def test_check_stock(self):
        """Test check_stock returns available quantity."""
        res_raw = check_stock.invoke({"product_slug": "nike-air-max-2026"})
        data = json.loads(res_raw)
        self.assertTrue(data.get("success"))
        self.assertEqual(data["total_available_stock"], 8)
        self.assertTrue(data["is_in_stock"])

    def test_get_product_price(self):
        """Test get_product_price returns current pricing."""
        res_raw = get_product_price.invoke({"product_slug": "nike-air-max-2026"})
        data = json.loads(res_raw)
        self.assertTrue(data.get("success"))
        self.assertEqual(data["price"], "120.00")

    def test_search_category(self):
        """Test search_category filters by category."""
        res_raw = search_category.invoke({"category_name": "Running Shoes"})
        data = json.loads(res_raw)
        self.assertTrue(data.get("success"))
        self.assertGreaterEqual(data["count"], 2)

    def test_search_by_brand(self):
        """Test search_by_brand filters by brand name."""
        res_raw = search_by_brand.invoke({"brand": "Nike"})
        data = json.loads(res_raw)
        self.assertTrue(data.get("success"))
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["name"], "Nike Air Max 2026")

    def test_search_by_price(self):
        """Test search_by_price filters within range."""
        res_raw = search_by_price.invoke({"min_price": 100.0, "max_price": 150.0})
        data = json.loads(res_raw)
        self.assertTrue(data.get("success"))
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["slug"], "nike-air-max-2026")

    # =========================================================================
    # CART TOOLS
    # =========================================================================
    def test_cart_operations(self):
        """Test get_cart, add_to_cart, update_cart, and remove_from_cart scoped to user."""
        token = set_current_user(self.user_a)
        try:
            # 1. Initial cart empty
            init = json.loads(get_cart.invoke({}))
            self.assertTrue(init.get("success"))
            self.assertEqual(init["total_items"], 0)

            # 2. Add 2 units of Nike Air Max (available = 8)
            add_res = json.loads(add_to_cart.invoke({"product_slug": "nike-air-max-2026", "quantity": 2}))
            self.assertTrue(add_res.get("success"))
            self.assertEqual(add_res["cart_quantity"], 2)

            # 3. Add exceeding stock (trying to add 10 more when only 6 remaining available)
            overstock = json.loads(add_to_cart.invoke({"product_slug": "nike-air-max-2026", "quantity": 10}))
            self.assertFalse(overstock.get("success"))
            self.assertIn("error", overstock)

            # 4. View cart
            cart_view = json.loads(get_cart.invoke({}))
            self.assertEqual(cart_view["total_items"], 2)
            self.assertEqual(cart_view["total_price"], "240.00")

            # 5. Update cart quantity to 4
            upd_res = json.loads(update_cart.invoke({"product_slug": "nike-air-max-2026", "quantity": 4}))
            self.assertTrue(upd_res.get("success"))
            self.assertEqual(upd_res["quantity"], 4)

            # 6. Remove from cart
            rem_res = json.loads(remove_from_cart.invoke({"product_slug": "nike-air-max-2026"}))
            self.assertTrue(rem_res.get("success"))

            final_cart = json.loads(get_cart.invoke({}))
            self.assertEqual(final_cart["total_items"], 0)
        finally:
            reset_current_user(token)

    # =========================================================================
    # WISHLIST TOOLS
    # =========================================================================
    def test_wishlist_operations(self):
        """Test get_wishlist, add_to_wishlist, check_wishlist, and remove_from_wishlist."""
        token = set_current_user(self.user_a)
        try:
            init = json.loads(get_wishlist.invoke({}))
            self.assertTrue(init.get("success"))
            self.assertEqual(init["count"], 0)

            add_res = json.loads(add_to_wishlist.invoke({"product_slug": "nike-air-max-2026"}))
            self.assertTrue(add_res.get("success"))

            # Duplicate prevention
            dup_res = json.loads(add_to_wishlist.invoke({"product_slug": "nike-air-max-2026"}))
            self.assertTrue(dup_res.get("success"))
            self.assertIn("already in your wishlist", dup_res["message"])

            # Check wishlist
            chk = json.loads(check_wishlist.invoke({"product_slug": "nike-air-max-2026"}))
            self.assertTrue(chk["is_in_wishlist"])

            # Remove
            rem = json.loads(remove_from_wishlist.invoke({"product_slug": "nike-air-max-2026"}))
            self.assertTrue(rem.get("success"))

            chk_after = json.loads(check_wishlist.invoke({"product_slug": "nike-air-max-2026"}))
            self.assertFalse(chk_after["is_in_wishlist"])
        finally:
            reset_current_user(token)

    # =========================================================================
    # ORDER TOOLS & IDOR SECURITY
    # =========================================================================
    def test_order_isolation_and_idor_prevention(self):
        """
        Verify:
        User A can access User A's orders.
        User A CANNOT access User B's orders (IDOR prevention).
        """
        token = set_current_user(self.user_a)
        try:
            # 1. User A lists own orders
            orders_res = json.loads(get_orders.invoke({}))
            self.assertTrue(orders_res.get("success"))
            self.assertEqual(orders_res["count"], 1)
            self.assertEqual(orders_res["orders"][0]["order_number"], "ORD-A1001")

            # 2. User A views own order details
            detail_res = json.loads(get_order_details.invoke({"order_identifier": "ORD-A1001"}))
            self.assertTrue(detail_res.get("success"))
            self.assertEqual(detail_res["order_number"], "ORD-A1001")

            # 3. User A views own order status
            status_res = json.loads(get_order_status.invoke({"order_identifier": "ORD-A1001"}))
            self.assertTrue(status_res.get("success"))
            self.assertEqual(status_res["raw_status"], "confirmed")

            # 4. IDOR ATTEMPT: User A attempts to view User B's order
            idor_res = json.loads(get_order_details.invoke({"order_identifier": "ORD-B2002"}))
            self.assertFalse(idor_res.get("success"))
            self.assertIn("Unauthorized access", idor_res.get("error", ""))
            self.assertFalse(idor_res.get("authorized", True))

            # 5. IDOR ATTEMPT on status
            idor_status = json.loads(get_order_status.invoke({"order_identifier": "ORD-B2002"}))
            self.assertFalse(idor_status.get("success"))
            self.assertIn("Unauthorized access", idor_status.get("error", ""))
        finally:
            reset_current_user(token)
