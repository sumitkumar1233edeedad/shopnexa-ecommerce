from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser

User = get_user_model()
from apps.products.models import Product, ProductVariant, Color, Category
from apps.cart.models import Cart, CartItem
from apps.cart.utils import get_cart_count


class CartCountUtilsTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="password123"
        )
        self.category = Category.objects.create(name="Test Category", slug="test-cat")
        self.product = Product.objects.create(name="Test Product", slug="test-product")
        self.color = Color.objects.create(name="Red", hex_code="#FF0000", slug="red")
        self.variant1 = ProductVariant.objects.create(
            product=self.product,
            color=self.color,
            sku="SKU-001",
            price=100.00,
            slug="test-product-v1"
        )
        self.variant2 = ProductVariant.objects.create(
            product=self.product,
            color=self.color,
            sku="SKU-002",
            price=150.00,
            slug="test-product-v2"
        )

    def test_authenticated_user_empty_cart(self):
        request = self.factory.get("/")
        request.user = self.user
        count = get_cart_count(request)
        self.assertEqual(count, 0)

    def test_authenticated_user_with_items(self):
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, product=self.variant1, quantity=2)
        CartItem.objects.create(cart=cart, product=self.variant2, quantity=3)

        request = self.factory.get("/")
        request.user = self.user
        count = get_cart_count(request)
        self.assertEqual(count, 5)

    def test_guest_user_empty_session_cart(self):
        request = self.factory.get("/")
        request.user = AnonymousUser()
        request.session = {}
        count = get_cart_count(request)
        self.assertEqual(count, 0)

    def test_guest_user_with_session_cart_dict(self):
        request = self.factory.get("/")
        request.user = AnonymousUser()
        request.session = {
            "cart": {
                "variant-1": {"quantity": 3},
                "variant-2": {"quantity": 4},
            }
        }
        count = get_cart_count(request)
        self.assertEqual(count, 7)
