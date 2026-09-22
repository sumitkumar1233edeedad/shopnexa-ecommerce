from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from apps.accounts.models import Profile, Address, WishList
from apps.products.models import Product, ProductVariant, Color
from apps.cart.models import Cart, CartItem


User = get_user_model()


class ProfileAPITests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser",
            email="testuser@example.com",
            password="Password123!",
            first_name="Test",
            last_name="User",
            is_active=True,
            is_email_verified=True,
            is_activated=True,
        )
        self.profile, _ = Profile.objects.get_or_create(name=self.user)

        self.other_user = User.objects.create_user(
            username="otheruser",
            email="otheruser@example.com",
            password="Password123!",
            first_name="Other",
            last_name="Person",
            is_active=True,
            is_email_verified=True,
            is_activated=True,
        )
        self.other_profile, _ = Profile.objects.get_or_create(name=self.other_user)

        self.staff_user = User.objects.create_superuser(
            username="adminuser",
            email="admin@example.com",
            password="Password123!",
        )

    def test_unauthenticated_access_denied(self):
        response = self.client.get("/api/profile/")
        self.assertEqual(response.status_code, 401)

    def test_get_own_profile(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/profile/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["profile"]["username"], "testuser")
        self.assertIn("addresses", response.data)
        self.assertIn("wishlist_items", response.data)
        self.assertIn("counts", response.data)

    def test_get_own_profile_with_slug(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(f"/api/profile/{self.profile.slug}/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["profile"]["username"], "testuser")

    def test_non_staff_access_other_profile_forbidden(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(f"/api/profile/{self.other_profile.slug}/")
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["profile_slug"], self.profile.slug)

    def test_staff_access_other_profile_allowed(self):
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get(f"/api/profile/{self.other_profile.slug}/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["profile"]["username"], "otheruser")

    def test_staff_access_nonexistent_profile_not_found(self):
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get("/api/profile/completely-nonexistent-slug/")
        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.data["success"])

    def test_patch_own_profile(self):
        self.client.force_authenticate(user=self.user)
        payload = {
            "first_name": "UpdatedFirst",
            "last_name": "UpdatedLast",
            "phone": "9876543210",
        }
        response = self.client.patch("/api/profile/", payload, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["profile"]["first_name"], "UpdatedFirst")
        self.assertEqual(response.data["profile"]["last_name"], "UpdatedLast")
        self.assertEqual(response.data["profile"]["phone"], "9876543210")

        self.user.refresh_from_db()
        self.profile.refresh_from_db()
        self.assertEqual(self.user.first_name, "UpdatedFirst")
        self.assertEqual(self.profile.phone, "9876543210")


class LogoutAPITests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="logoutuser",
            email="logoutuser@example.com",
            password="Password123!",
            is_active=True,
            is_email_verified=True,
            is_activated=True,
        )

    def test_unauthenticated_logout_fails(self):
        response = self.client.post("/api/logout/")
        self.assertEqual(response.status_code, 401)

    def test_logout_deletes_token(self):
        from rest_framework.authtoken.models import Token
        token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        response = self.client.post("/api/logout/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["message"], "Logged out successfully.")

        # Token is deleted
        self.assertFalse(Token.objects.filter(key=token.key).exists())

        # Subsequent request with old token is unauthorized
        subsequent_resp = self.client.get("/api/profile/")
        self.assertEqual(subsequent_resp.status_code, 401)


class WishListAPITests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="wishuser",
            email="wishuser@example.com",
            password="Password123!",
            is_active=True,
            is_email_verified=True,
            is_activated=True,
        )
        self.client.force_authenticate(user=self.user)

        self.product1 = Product.objects.create(
            name="MacBook Pro M3",
            slug="macbook-pro-m3",
            brand="Apple",
        )
        self.product2 = Product.objects.create(
            name="iPhone 16 Pro",
            slug="iphone-16-pro",
            brand="Apple",
        )

    def test_unauthenticated_access_denied(self):
        unauth_client = APIClient()
        resp_get = unauth_client.get("/api/wishlist/")
        self.assertEqual(resp_get.status_code, 401)

        resp_toggle = unauth_client.post(f"/api/wishlist/toggle/{self.product1.slug}/")
        self.assertEqual(resp_toggle.status_code, 401)

        resp_remove = unauth_client.delete(f"/api/wishlist/remove/{self.product1.slug}/")
        self.assertEqual(resp_remove.status_code, 401)

    def test_get_empty_wishlist(self):
        response = self.client.get("/api/wishlist/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["count"], 0)
        self.assertEqual(response.data["wishlist_items"], [])

    def test_toggle_wishlist_add_and_remove(self):
        # 1. Add to wishlist
        response_add = self.client.post(f"/api/wishlist/toggle/{self.product1.slug}/")
        self.assertEqual(response_add.status_code, 201)
        self.assertTrue(response_add.data["success"])
        self.assertTrue(response_add.data["is_in_wishlist"])
        self.assertEqual(response_add.data["action"], "added")
        self.assertTrue(WishList.objects.filter(user=self.user, product=self.product1).exists())

        # Check list now contains 1 item
        resp_list = self.client.get("/api/wishlist/")
        self.assertEqual(resp_list.data["count"], 1)
        self.assertEqual(resp_list.data["wishlist_items"][0]["product_slug"], self.product1.slug)

        # 2. Toggle again to remove
        response_remove = self.client.post(f"/api/wishlist/toggle/{self.product1.slug}/")
        self.assertEqual(response_remove.status_code, 200)
        self.assertTrue(response_remove.data["success"])
        self.assertFalse(response_remove.data["is_in_wishlist"])
        self.assertEqual(response_remove.data["action"], "removed")
        self.assertFalse(WishList.objects.filter(user=self.user, product=self.product1).exists())

    def test_toggle_wishlist_by_product_id(self):
        # Test numeric ID fallback
        response = self.client.post(f"/api/wishlist/toggle/{self.product2.id}/")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["is_in_wishlist"])
        self.assertTrue(WishList.objects.filter(user=self.user, product=self.product2).exists())

    def test_toggle_wishlist_via_request_body(self):
        # Test body slug parameter
        response = self.client.post("/api/wishlist/toggle/", {"slug": self.product1.slug}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["is_in_wishlist"])

        # Test body product_id parameter
        response_id = self.client.post("/api/wishlist/toggle/", {"product_id": self.product2.id}, format="json")
        self.assertEqual(response_id.status_code, 201)
        self.assertTrue(response_id.data["is_in_wishlist"])

    def test_toggle_wishlist_nonexistent_product(self):
        response = self.client.post("/api/wishlist/toggle/nonexistent-slug-xyz/")
        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.data["success"])

    def test_toggle_wishlist_missing_identifier(self):
        response = self.client.post("/api/wishlist/toggle/", {}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data["success"])

    def test_remove_from_wishlist_delete_and_post(self):
        # Add item first
        wish_item = WishList.objects.create(user=self.user, product=self.product1)

        # Remove via DELETE
        response_delete = self.client.delete(f"/api/wishlist/remove/{self.product1.slug}/")
        self.assertEqual(response_delete.status_code, 200)
        self.assertTrue(response_delete.data["success"])
        self.assertFalse(WishList.objects.filter(user=self.user, product=self.product1).exists())

        # Add second item and remove via POST
        WishList.objects.create(user=self.user, product=self.product2)
        response_post = self.client.post(f"/api/wishlist/remove/{self.product2.slug}/")
        self.assertEqual(response_post.status_code, 200)
        self.assertTrue(response_post.data["success"])
        self.assertFalse(WishList.objects.filter(user=self.user, product=self.product2).exists())

    def test_remove_from_wishlist_by_wishlist_slug(self):
        wish_item = WishList.objects.create(user=self.user, product=self.product1)
        response = self.client.delete(f"/api/wishlist/remove/{wish_item.slug}/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertFalse(WishList.objects.filter(user=self.user, product=self.product1).exists())

    def test_remove_from_wishlist_not_in_wishlist(self):
        response = self.client.delete(f"/api/wishlist/remove/{self.product1.slug}/")
        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.data["success"])

    def test_direct_restful_endpoints(self):
        # 1. Direct POST /api/wishlist/<slug>/ toggles on
        resp_toggle_on = self.client.post(f"/api/wishlist/{self.product1.slug}/")
        self.assertEqual(resp_toggle_on.status_code, 201)
        self.assertTrue(resp_toggle_on.data["is_in_wishlist"])

        # 2. Direct DELETE /api/wishlist/<slug>/ deletes
        resp_delete = self.client.delete(f"/api/wishlist/{self.product1.slug}/")
        self.assertEqual(resp_delete.status_code, 200)
        self.assertFalse(resp_delete.data["is_in_wishlist"])



class AddressAPITests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="addruser",
            email="addruser@example.com",
            password="Password123!",
            is_active=True,
            is_email_verified=True,
            is_activated=True,
        )
        self.client.force_authenticate(user=self.user)

    def test_unauthenticated_address_access(self):
        unauth = APIClient()
        resp = unauth.get("/api/address/")
        self.assertEqual(resp.status_code, 401)

        resp_post = unauth.post("/api/address/", {})
        self.assertEqual(resp_post.status_code, 401)

    def test_get_empty_address_list(self):
        resp = self.client.get("/api/address/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["success"])
        self.assertEqual(resp.data["count"], 0)
        self.assertEqual(resp.data["addresses"], [])

    def test_create_first_address_auto_default(self):
        payload = {
            "name": "John Doe",
            "phone": "9876543210",
            "address_line": "123 Marine Drive",
            "locality": "Nariman Point",
            "city": "Mumbai",
            "state": "MH",
            "pincode": "400021",
            "address_type": "HOME",
        }
        resp = self.client.post("/api/address/", payload, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.data["success"])
        self.assertEqual(resp.data["address"]["name"], "John Doe")
        self.assertTrue(resp.data["address"]["is_default"])  # Auto-default on first address

    def test_create_address_with_full_name_and_state_label(self):
        payload = {
            "full_name": "Jane Smith",
            "phone": "9123456780",
            "address_line": "456 Park Avenue",
            "locality": "Bandra",
            "city": "Mumbai",
            "state": "Maharashtra",  # State full name should map to "MH"
            "pincode": "400050",
            "address_type": "WORK",
        }
        resp = self.client.post("/api/address/add/", payload, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["address"]["name"], "Jane Smith")
        self.assertEqual(resp.data["address"]["state"], "MH")

    def test_default_address_switch(self):
        addr1 = Address.objects.create(
            user=self.user,
            name="Address 1",
            phone="9000000001",
            address_line="Line 1",
            city="Mumbai",
            state="MH",
            pincode="400001",
            is_default=True,
        )

        payload2 = {
            "name": "Address 2",
            "phone": "9000000002",
            "address_line": "Line 2",
            "city": "Mumbai",
            "state": "MH",
            "pincode": "400002",
            "is_default": True,
        }
        resp = self.client.post("/api/address/", payload2, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.data["address"]["is_default"])

        # Check addr1 is no longer default
        addr1.refresh_from_db()
        self.assertFalse(addr1.is_default)

    def test_get_address_detail_by_slug_and_id(self):
        addr = Address.objects.create(
            user=self.user,
            name="Office",
            phone="9000000003",
            address_line="Tech Park",
            city="Bengaluru",
            state="KA",
            pincode="560001",
        )

        # By slug
        resp_slug = self.client.get(f"/api/address/{addr.slug}/")
        self.assertEqual(resp_slug.status_code, 200)
        self.assertEqual(resp_slug.data["address"]["name"], "Office")

        # By ID
        resp_id = self.client.get(f"/api/address/{addr.id}/")
        self.assertEqual(resp_id.status_code, 200)
        self.assertEqual(resp_id.data["address"]["name"], "Office")

    def test_patch_address(self):
        addr = Address.objects.create(
            user=self.user,
            name="Old Name",
            phone="9000000004",
            address_line="Old Line",
            city="Delhi",
            state="DL",
            pincode="110001",
        )

        resp = self.client.patch(f"/api/address/{addr.slug}/", {"name": "New Name", "city": "New Delhi"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["address"]["name"], "New Name")
        self.assertEqual(resp.data["address"]["city"], "New Delhi")

        addr.refresh_from_db()
        self.assertEqual(addr.name, "New Name")

    def test_delete_address(self):
        addr = Address.objects.create(
            user=self.user,
            name="To Delete",
            phone="9000000005",
            address_line="Delete Line",
            city="Pune",
            state="MH",
            pincode="411001",
        )

        resp = self.client.delete(f"/api/address/{addr.slug}/")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Address.objects.filter(id=addr.id).exists())

    def test_delete_address_via_post_endpoint(self):
        addr = Address.objects.create(
            user=self.user,
            name="To Delete Post",
            phone="9000000006",
            address_line="Delete Line 2",
            city="Pune",
            state="MH",
            pincode="411002",
        )

        resp = self.client.post(f"/api/address/{addr.slug}/delete/")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Address.objects.filter(id=addr.id).exists())

    def test_set_default_address(self):
        addr1 = Address.objects.create(
            user=self.user,
            name="Addr 1",
            phone="9000000007",
            address_line="Line 1",
            city="Jaipur",
            state="RJ",
            pincode="302001",
            is_default=True,
        )
        addr2 = Address.objects.create(
            user=self.user,
            name="Addr 2",
            phone="9000000008",
            address_line="Line 2",
            city="Jaipur",
            state="RJ",
            pincode="302002",
            is_default=False,
        )

        resp = self.client.post(f"/api/address/{addr2.slug}/set-default/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["address"]["is_default"])

        addr1.refresh_from_db()
        addr2.refresh_from_db()
        self.assertFalse(addr1.is_default)
        self.assertTrue(addr2.is_default)


class LoginAndCartMergeAPITests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="shopper",
            email="shopper@example.com",
            password="Password123!",
            is_active=True,
            is_email_verified=True,
            is_activated=True,
        )

        self.color = Color.objects.create(name="Deep Blue", hex_code="#00008B", slug="deep-blue")
        self.product = Product.objects.create(name="Pixel 9 Pro", slug="pixel-9-pro", brand="Google")
        self.variant = ProductVariant.objects.create(
            product=self.product,
            color=self.color,
            sku="PIXEL-9-BLU",
            slug="pixel-9-pro-blue",
            price=Decimal("899.00"),
            is_active=True,
        )

    def test_standard_login(self):
        res = self.client.post(
            "/api/login/",
            {"username": "shopper", "password": "Password123!"},
            format="json"
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["success"])
        self.assertIn("token", res.data)
        self.assertEqual(res.data["user"]["username"], "shopper")
        self.assertIn("cart", res.data)

    def test_login_with_cart_payload_merges_into_db_cart(self):
        # User sends guest cart in login payload (e.g. from mobile app / local storage)
        payload = {
            "username": "shopper",
            "password": "Password123!",
            "cart": [
                {"variant_slug": self.variant.slug, "quantity": 2}
            ]
        }
        res = self.client.post("/api/login/", payload, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["success"])
        self.assertEqual(res.data["cart"]["total_items"], 2)
        self.assertEqual(res.data["cart"]["total_price"], "1798.00")

        # Verify in DB
        cart_obj = Cart.objects.get(user=self.user)
        self.assertEqual(cart_obj.items.count(), 1)
        self.assertEqual(cart_obj.items.first().quantity, 2)



