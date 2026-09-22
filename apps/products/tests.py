from django.test import TestCase, Client
from django.urls import reverse
from apps.products.models import Product, Category
from django.test import override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from apps.products.models import ProductImage


class ProductListPaginationTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.category = Category.objects.create(name="Footwear")
        
        # Create 25 active products (2 full pages of 12, plus 1 product on page 3)
        self.products = []
        for i in range(1, 26):
            p = Product.objects.create(
                name=f"Sneaker {i:02d}",
                brand="Nike" if i % 2 == 0 else "Adidas",
                description=f"High performance sneaker model {i}",
                is_active=True
            )
            p.cat.add(self.category)
            self.products.append(p)

    def test_product_list_initial_page_load(self):
        """Initial load renders the first 12 products with Load More button."""
        response = self.client.get(reverse("products"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "product/product_list.html")
        self.assertTemplateUsed(response, "product/partials/product_card.html")

        products_on_page = response.context["products"]
        self.assertEqual(len(products_on_page), 12)
        self.assertTrue(products_on_page.has_next())
        self.assertEqual(products_on_page.next_page_number(), 2)
        self.assertContains(response, 'id="load-more-btn"')

    def test_product_list_ajax_second_chunk(self):
        """AJAX request for page 2 returns JSON with 12 product cards and has_next=True."""
        response = self.client.get(
            reverse("products") + "?page=2",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertIn("html", data)
        self.assertTrue(data["has_next"])
        self.assertEqual(data["next_page"], 3)
        self.assertEqual(data["current_page"], 2)
        self.assertEqual(data["total_pages"], 3)
        self.assertEqual(data["total_count"], 25)
        # Verify rendered HTML contains product card markup
        self.assertIn("product-list-card", data["html"])

    def test_product_list_ajax_last_chunk(self):
        """AJAX request for page 3 (last page) returns has_next=False and next_page=None."""
        response = self.client.get(
            reverse("products") + "?page=3",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertFalse(data["has_next"])
        self.assertIsNone(data["next_page"])
        self.assertEqual(data["current_page"], 3)
        self.assertIn("product-list-card", data["html"])

    def test_product_list_ajax_out_of_bounds(self):
        """AJAX request beyond total pages returns empty HTML and has_next=False."""
        response = self.client.get(
            reverse("products") + "?page=99",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["has_next"])
        self.assertIsNone(data["next_page"])
        self.assertEqual(data["html"], "")

    def test_product_list_preserves_search_filters(self):
        """Search query filters results and paginates only matching items."""
        response = self.client.get(
            reverse("products") + "?q=Nike",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # 12 items matching "Nike"
        self.assertEqual(data["total_count"], 12)
        self.assertFalse(data["has_next"])




User = get_user_model()

# Valid 1x1 pixel transparent PNG byte sequence
TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00"
    b"\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)
class ProductGalleryImageTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.category = Category.objects.create(name="Apparel")
        self.product = Product.objects.create(
            name="Modern Denim Jacket",
            brand="StoreAI Denim",
            description="Premium denim jacket with comfort stretch.",
            is_active=True
        )
        self.product.cat.add(self.category)

        # Create staff user for admin panel tests
        self.staff_user = User.objects.create_user(
            username="staffmanager",
            email="staff@example.com",
            password="staffpassword123",
            is_staff=True,
            is_superuser=True
        )

    def test_product_image_model_creation(self):
        """Verify ProductImage can be created and accessed via related_name 'images'."""
        dummy_img = SimpleUploadedFile("gallery_1.png", TINY_PNG, content_type="image/png")
        product_image = ProductImage.objects.create(
            product=self.product,
            image=dummy_img,
            alt_text="Front angle"
        )
        self.assertEqual(self.product.images.count(), 1)
        self.assertEqual(self.product.images.first().pk, product_image.pk)
        self.assertIn("Modern Denim Jacket Gallery Image", str(product_image))

    def test_product_detail_renders_gallery_thumbnails(self):
        """Verify product detail page includes thumbnail strip when gallery images exist."""
        dummy_img1 = SimpleUploadedFile("g1.png", TINY_PNG, content_type="image/png")
        dummy_img2 = SimpleUploadedFile("g2.png", TINY_PNG, content_type="image/png")
        ProductImage.objects.create(product=self.product, image=dummy_img1)
        ProductImage.objects.create(product=self.product, image=dummy_img2)

        response = self.client.get(reverse("product_detail", kwargs={"slug": self.product.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="detailThumbnailsStrip"')
        self.assertContains(response, 'class="detail-thumb-item')

    def test_admin_product_image_delete(self):
        """Verify staff user can delete a gallery image via admin_product_image_delete."""
        self.client.login(username="staffmanager", password="staffpassword123")
        dummy_img = SimpleUploadedFile("del_img.png", TINY_PNG, content_type="image/png")
        img_to_delete = ProductImage.objects.create(product=self.product, image=dummy_img)

        self.assertEqual(self.product.images.count(), 1)

        response = self.client.get(reverse("admin_product_image_delete", kwargs={"image_id": img_to_delete.id}))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.product.images.count(), 0)

    def test_admin_product_add_with_gallery_images(self):
        """Verify staff user can create product with primary image and multiple gallery images."""
        self.client.login(username="staffmanager", password="staffpassword123")
        main_file = SimpleUploadedFile("cover.png", TINY_PNG, content_type="image/png")
        g1 = SimpleUploadedFile("extra1.png", TINY_PNG, content_type="image/png")
        g2 = SimpleUploadedFile("extra2.png", TINY_PNG, content_type="image/png")

        post_data = {
            "name": "Cargo Joggers",
            "brand": "Urban Wear",
            "description": "Comfortable utility joggers",
            "category": self.category.id,
            "is_active": "on",
            "image": main_file,
            "gallery_images": [g1, g2],
        }

        response = self.client.post(reverse("admin_product_add"), post_data)
        self.assertEqual(response.status_code, 302)

        created_prod = Product.objects.get(name="Cargo Joggers")
        self.assertTrue(bool(created_prod.image))
        self.assertEqual(created_prod.images.count(), 2)

    def test_admin_product_edit_upload_new_gallery_image(self):
        """Verify staff user can add additional gallery images on the edit page."""
        self.client.login(username="staffmanager", password="staffpassword123")
        g_extra = SimpleUploadedFile("extra_angle.png", TINY_PNG, content_type="image/png")

        post_data = {
            "name": self.product.name,
            "brand": self.product.brand,
            "description": self.product.description,
            "category": self.category.id,
            "is_active": "on",
            "gallery_images": [g_extra],
        }

        response = self.client.post(
            reverse("admin_product_edit", kwargs={"slug": self.product.slug}),
            post_data
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.product.images.count(), 1)

