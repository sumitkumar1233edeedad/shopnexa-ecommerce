# Project Changelog & Bug Fixes (`changing.md`)

This document records recent bug fixes, improvements, and architectural updates made to the **AI Store** application.

---

## 1. Fix: Cloudinary `Invalid image file` (HTTP 500 on Product Creation & Editing)

### 📌 Issue Description
- **Error**: `cloudinary.exceptions.BadRequest: Invalid image file` (HTTP 500 Internal Server Error)
- **URL**: `/adminpanel/products/add/` and `/adminpanel/products/edit/<slug>/`
- **Root Cause**:
  1. `Product.objects.create(..., image=image)` directly passed uploaded files to Cloudinary without pre-validating file structure or format.
  2. Submitting empty, corrupted, or non-image files (e.g., text, document, or 0-byte files) caused Cloudinary's upload API to reject the file with a `BadRequest: Invalid image file`.
  3. The views lacked exception handling around Cloudinary storage calls, resulting in raw 500 server crashes.
  4. Empty dynamic gallery slots created on the frontend submitted empty file inputs to the server.

### 🛠️ Changes Implemented
- **New Image Validator ([`apps/products/validators.py`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/apps/products/validators.py))**:
  - Validates file presence and non-zero size (`size > 0`).
  - Enforces a 10MB maximum file size limit.
  - Whitelists safe raster image extensions (`.jpg`, `.jpeg`, `.png`, `.webp`, `.gif`).
  - Uses Pillow (`PIL.Image.open().verify()`) to check image headers and binary data integrity before attempting upload.
  - Resets file stream cursor (`file.seek(0)`) so subsequent reading by Cloudinary always reads from byte 0.
- **Storage Stream Reset ([`ai_store/storage.py`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/ai_store/storage.py))**:
  - Added `_save` override in `OptimizedMediaCloudinaryStorage` ensuring `content.seek(0)` before dispatching to Cloudinary.
- **Atomic Transactions & Flash Error Handling ([`apps/admin_pannel/views.py`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/apps/admin_pannel/views.py))**:
  - `product_add` and `product_edit` validate main and gallery images.
  - Wrapped database writes and Cloudinary uploads inside `transaction.atomic()` and `try...except Exception as e:`.
  - On failure, user-friendly alert messages (`messages.error`) are shown, and form input values are preserved so admins do not lose entered data.
- **Profile Picture Upload Validation ([`apps/accounts/views.py`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/apps/accounts/views.py))**:
  - Added image validation and `try...except` error handling to profile picture updates.
- **Frontend Enhancements ([`admin_product_add.html`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/templates/adminpanel/admin_product_add.html) & [`admin_product_edit.html`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/templates/adminpanel/admin_product_edit.html))**:
  - Added `accept="image/jpeg,image/png,image/webp,image/gif"` and helper text.
  - Added client-side file size and format validation.
  - Added submit listener to automatically disable empty gallery file inputs so empty file parts are never submitted.

---

## 2. Fix: `ValueError: Field 'id' expected a number but got 'Black'` (Variant Edit)

### 📌 Issue Description
- **Error**: `ValueError: Field 'id' expected a number but got 'Black'.`
- **URL**: `/adminpanel/variants/edit/<slug>/`
- **Root Cause**:
  1. In `admin_variant_edit.html`, Color was rendered as an ordinary text input:
     ```html
     <input name="color" value="{{ variant.color }}">
     ```
     `{{ variant.color }}` rendered the string representation of the Color model (e.g. `"Black"`).
  2. In `variant_edit` in `views.py`, the backend did:
     ```python
     color_id = request.POST.get("color")
     color = get_object_or_404(Color, id=color_id) # Crashed: id='Black'
     ```
     Because Django's `id` field expects an integer primary key, passing `"Black"` threw a `ValueError`.
  3. The Stock field had `value="{{ variant.stock }}"`, which rendered `"SKU - available_qty"`, causing invalid values in the number input.
  4. The edit form had no `is_active` checkbox to toggle variant availability.

### 🛠️ Changes Implemented
- **Backend Robust Querying ([`apps/admin_pannel/views.py`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/apps/admin_pannel/views.py))**:
  - Updated `variant_edit` and `variant_add` to handle both numeric IDs, slugs, and string names:
    ```python
    if color_val:
        if color_val.isdigit():
            color = get_object_or_404(Color, id=int(color_val))
        else:
            color = Color.objects.filter(
                Q(slug=color_val) | Q(name__iexact=color_val)
            ).first() or get_object_or_404(Color, slug=color_val)
    ```
  - Added duplicate SKU validation (excluding current variant during edit).
  - Ensured safe Decimal price and integer stock quantity conversion.
  - Supported `is_active` boolean toggle.
  - Wrapped operations in `transaction.atomic()`.
- **Form Template Overhaul ([`templates/adminpanel/admin_variant_edit.html`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/templates/adminpanel/admin_variant_edit.html))**:
  - Replaced the text input with a `<select name="color">` dropdown populated with available colors, pre-selecting `variant.color_id`.
  - Set Stock input value to `{{ variant.stock.quantity|default:0 }}`.
  - Added an **Active variant** checkbox.
- **Form Template Alignment ([`templates/adminpanel/admin_variant_add.html`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/templates/adminpanel/admin_variant_add.html))**:
  - Added the **Active variant** checkbox to match the edit view.

---

---

## 3. Architecture Update: Direct `CustomUser` Email Verification & OTP Handling

### 📌 Requirement & Background
- **Goal**: Handle email verification and temporary OTP directly inside the `CustomUser` model without creating or maintaining a separate OTP model.
- **Removed**: The legacy `EmailOTP` model, its relationships, queries, and administrative views.
- **Required New Fields on `CustomUser`**:
  - `is_email_verified` (BooleanField, default=False)
  - `temp_otp` (CharField, max_length=6, blank=True, null=True)
  - `is_activated` (BooleanField, default=False)
  - `otp_created_at` (DateTimeField, null=True, blank=True, for 10-minute expiry validation)

### 🛠️ Changes Implemented
- **Model Refactoring ([`apps/accounts/models.py`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/apps/accounts/models.py))**:
  - Added `is_email_verified`, `temp_otp`, `is_activated`, and `otp_created_at` to `CustomUser`.
  - Completely deleted the `EmailOTP` model.
- **Admin Configuration ([`apps/accounts/admin.py`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/apps/accounts/admin.py))**:
  - Added `is_email_verified` and `is_activated` to `CustomUserAdmin`'s `list_display` and `list_filter`.
- **Background Tasks & Services ([`apps/accounts/tasks.py`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/apps/accounts/tasks.py))**:
  - Updated `generate_and_send_otp(user, purpose)`:
    - Generates a 6-digit random code.
    - Saves `user.temp_otp = otp_code` and `user.otp_created_at = timezone.now()`.
    - Dispatches async Celery task `send_otp_email_task.delay(...)`.
  - Updated `cleanup_expired_otps_task`:
    - Clears expired `temp_otp` and `otp_created_at` on `CustomUser` where `otp_created_at` > 10 minutes.
- **View Layer Updates ([`apps/accounts/views.py`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/apps/accounts/views.py))**:
  - `register_view`: Explicitly sets `is_active=False`, `is_email_verified=False`, `is_activated=False` on user creation.
  - `verify_otp_view`: Compares `entered_otp == user.temp_otp`, validates 10-minute expiry, and on success sets `is_email_verified = True`, `is_activated = True`, `is_active = True`, and clears `temp_otp = None` / `otp_created_at = None`.
  - `resend_otp_view`: Invokes `generate_and_send_otp` to overwrite `temp_otp` and reset the 10-minute expiry timer.
  - `forgot_password_view`: Sets new `temp_otp` on user and dispatches password reset OTP email.
  - `verify_reset_otp_view`: Validates `user.temp_otp` and clears it upon success.
  - `reset_password_view`: Sets new password, ensures user is activated and email verified, and updates session authentication hash.
  - `login_view`: Checks `if not user_obj.is_active or not user_obj.is_email_verified or not user_obj.is_activated:`, triggering OTP delivery and directing user to verification.
- **Database Migrations ([`apps/accounts/migrations/0003_customuser_is_activated_customuser_is_email_verified_and_more.py`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/apps/accounts/migrations/0003_customuser_is_activated_customuser_is_email_verified_and_more.py))**:
  - Applied schema migration adding new fields and dropping table `accounts_emailotp`.
- **Unit & Integration Tests ([`apps/accounts/tests.py`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/apps/accounts/tests.py))**:
  - Full suite of 12 tests covering OTP generation, replacement, model defaults, and end-to-end registration/verification/reset HTTP flows. All tests passing (`OK`).

---

---

## 4. Enhancement & Fix: `ProfileAPIView` & `ProfileSerializer` in REST API (`api_apps/accounts_api`)

### 📌 Requirement & Background
- **Goal**: Ensure `ProfileAPIView` cleanly resolves user profiles, properly handles custom slugs (both own profile and administrative access for other user profiles), passes serializer context for hyperlinked/media assets, and supports profile updates via `PUT`/`PATCH`.
- **Identified Issues**:
  1. `ProfileSerializer` crashed with `AssertionError: The .update() method does not support writable dotted-source fields by default` when `first_name` and `last_name` (`source='name.first_name'`, `source='name.last_name'`) were passed in update requests.
  2. In `ProfileAPIView.get(slug=...)`, when a staff member requested another user's profile slug, the view bypassed the permission check but returned the staff member's own profile and data instead of the target user's data.
  3. Non-existent slugs returned the logged-in user's profile instead of a proper 404 response.
  4. Serializers (`ProfileSerializer`, `AddressSerializer`, `WishListSerializer`) lacked `context={'request': request}`, preventing DRF from building fully qualified image URLs for `profile_picture` and `product.image`.
  5. `ProfileAPIView` lacked `PUT` and `PATCH` methods to allow users to update their profile details and profile picture.

### 🛠️ Changes Implemented
- **ProfileSerializer Update ([`api_apps/accounts_api/serializers.py`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/api_apps/accounts_api/serializers.py))**:
  - Implemented an explicit `.update(instance, validated_data)` method that cleanly handles nested `name.first_name` and `name.last_name` updates on the underlying `CustomUser` model without throwing DRF dotted-source assertion errors.
- **ProfileAPIView Refactoring ([`api_apps/accounts_api/views.py`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/api_apps/accounts_api/views.py))**:
  - Added helper method `_resolve_target(request, slug)`:
    - Resolves `target_user` and `target_profile`.
    - If `slug` matches the requester's own profile (via slug, username, or user ID), returns their own profile.
    - If `slug` belongs to another user and requester is not staff, returns `403 Forbidden` (`{"success": False, "message": "You can only access your own profile.", "profile_slug": profile.slug}`).
    - If requester is staff, looks up the target user's profile by `slug`, `username`, or `id`. Returns `404 Not Found` if the profile does not exist.
  - Added `context={"request": request}` to all serializers (`ProfileSerializer`, `AddressSerializer`, `WishListSerializer`).
  - Implemented `put` and `patch` handlers:
    - Allows updating `first_name`, `last_name`, `phone`, and `profile_picture`.
    - Validates uploaded images with `validate_uploaded_image` before processing.
- **Logout API Implementation ([`api_apps/accounts_api/views.py`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/api_apps/accounts_api/views.py) & [`api_apps/accounts_api/urls.py`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/api_apps/accounts_api/urls.py))**:
  - Implemented `LogoutAPIView` (`permission_classes = [IsAuthenticated]`):
    - Deletes the active DRF authentication token from `Token` table.
    - Flushes the Django session (`logout(request)`).
    - Returns `{"success": True, "message": "Logged out successfully."}` with `200 OK`.
    - Wired up endpoint `/api/logout/`.
- **Package Init ([`api_apps/__init__.py`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/api_apps/__init__.py))**:
  - Added `__init__.py` to `api_apps` directory to support Django test runner module discovery.
- **Comprehensive API Tests ([`api_apps/accounts_api/tests.py`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/api_apps/accounts_api/tests.py))**:
  - Added `ProfileAPITests` and `LogoutAPITests` verifying: unauthenticated access (401), own profile retrieval (200), own profile with slug (200), unauthorized other user profile access (403), staff viewing other user profiles (200), staff viewing non-existent profiles (404), partial profile update via `PATCH` (200), and token deletion/invalidation on logout (200). All 9 tests passing (`OK`).

---

## 5. Implementation: Unified WishList REST API (`api_apps/accounts_api`)

Consolidated wishlist views into a single, elegant `WishListAPIView` that handles listing, toggling, and removal with standard HTTP verbs:

### Endpoints Created
1. **Unified RESTful Routes**:
   - `GET /api/wishlist/`: List all wishlist items for authenticated user.
   - `POST /api/wishlist/<slug:slug>/`: Toggle product in wishlist (adds if absent with 201, removes if present with 200).
   - `DELETE /api/wishlist/<slug:slug>/`: Explicitly remove product from wishlist (returns 404 if not found).
2. **Backwards-Compatible Action Routes**:
   - `POST /api/wishlist/toggle/<slug:slug>/` and `POST /api/wishlist/toggle/`
   - `DELETE /api/wishlist/remove/<slug:slug>/`, `POST /api/wishlist/remove/<slug:slug>/`, and `/api/wishlist/remove/`


### Postman Testing Guide
- **Headers**:
  ```http
  Authorization: Token <YOUR_AUTH_TOKEN>
  Content-Type: application/json
  ```
- **List Wishlist**:
  - `GET http://127.0.0.1:8000/api/wishlist/`
- **Toggle Wishlist (Add / Remove)**:
  - `POST http://127.0.0.1:8000/api/wishlist/toggle/iphone-16-pro/`
  - Or `POST http://127.0.0.1:8000/api/wishlist/toggle/` with body:
    ```json
    { "slug": "iphone-16-pro" }
    ```
- **Remove from Wishlist**:
  - `DELETE http://127.0.0.1:8000/api/wishlist/remove/iphone-16-pro/`

### Automated Verification
- Added `WishListAPITests` covering:
  - Unauthenticated access rejection (401 for GET, POST, DELETE).
  - Empty wishlist retrieval (200 with empty list).
  - Toggling items (201 added, 200 removed).
  - Toggling via request body (`{"slug": ...}`, `{"product_id": ...}`).
  - Toggling fallback to numeric product ID.
  - 404 on nonexistent products.
  - 400 on missing identifier.
  - Removal via both `DELETE` and `POST`.
  - Removal by wishlist item slug.
  - 404 when removing item not in user's wishlist.
- **Results**: Ran all 19 tests in `api_apps.accounts_api`, all passed (`OK`).

---

## 6. Implementation: Unified Address REST API (`api_apps/accounts_api`)

Consolidated all address endpoints into a single, clean `AddressAPIView` class handling collection listing/creation, single item retrieval/updating/deletion, and default address switching:

### Endpoints Created
1. **List & Add Addresses**:
   - `GET /api/address/`: Returns all shipping/billing addresses for authenticated user ordered by `["-is_default", "-id"]`.
   - `POST /api/address/` or `POST /api/address/add/`: Creates an address with validation and automated default address management.
   - **Permission**: `IsAuthenticated`
   - **Features**:
     - Automatically maps `full_name` to `name` if passed from web forms.
     - Flexible state resolution: accepts either state code (e.g. `"MH"`) or full state name (e.g. `"Maharashtra"`).
     - Automatically designates the user's first address as `is_default=True`.
     - When `is_default=True` is provided, atomicity resets existing addresses to `is_default=False`.
2. **Address Detail, Update & Delete**:
   - `GET /api/address/<slug:slug>/` (or by numeric ID `id`): Retrieves address details.
   - `PUT` / `PATCH /api/address/<slug:slug>/`: Updates address details (partial or full).
   - `DELETE /api/address/<slug:slug>/`: Deletes the address. If the deleted address was default, the next latest address is automatically promoted to default.
   - `POST` / `DELETE /api/address/<slug:slug>/delete/` (and `/api/address/delete/<slug:slug>/`): Dedicated delete endpoints matching template views.
3. **Set Default Address**:
   - `POST /api/address/<slug:slug>/set-default/`: Atomically switches the default address for the user.

### Postman Testing Guide
- **Headers**:
  ```http
  Authorization: Token <YOUR_AUTH_TOKEN>
  Content-Type: application/json
  ```
- **List Addresses**:
  - `GET http://127.0.0.1:8000/api/address/`
- **Add Address**:
  - `POST http://127.0.0.1:8000/api/address/` (or `/api/address/add/`) with body:
    ```json
    {
      "name": "John Doe",
      "phone": "9876543210",
      "address_line": "Flat 402, Sunset Towers",
      "locality": "Andheri West",
      "city": "Mumbai",
      "state": "Maharashtra",
      "pincode": "400053",
      "address_type": "HOME",
      "is_default": true
    }
    ```
- **Update Address**:
  - `PATCH http://127.0.0.1:8000/api/address/<slug>/` with body:
    ```json
    {
      "phone": "9123456789"
    }
    ```
- **Delete Address**:
  - `DELETE http://127.0.0.1:8000/api/address/<slug>/`
  - Or `POST http://127.0.0.1:8000/api/address/<slug>/delete/`
- **Set as Default**:
  - `POST http://127.0.0.1:8000/api/address/<slug>/set-default/`

### Automated Verification
- Added `AddressAPITests` covering:
  - 401 unauthenticated access rejection.
  - Empty address list retrieval.
  - Automatic `is_default` assignment for the user's first address.
  - `full_name` alias and full state name resolution ("Maharashtra" -> "MH").
  - Default address switching when a second default address is saved.
  - Retrieval by both `slug` and numeric `id`.
  - Partial updates via `PATCH`.
  - Deletion via standard `DELETE` and explicit `/delete/` POST endpoint.
  - Setting default address via `/set-default/`.
- **Results**: Ran all 29 tests in `api_apps.accounts_api` and all 41 tests across `apps.accounts` + `api_apps.accounts_api`, 100% passing (`OK`).

---

## 7. Summary of Files Modified & Created

| File | Status | Description |
|---|---|---|
| [`api_apps/accounts_api/views.py`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/api_apps/accounts_api/views.py) | **Modified** | Implemented `AddressListCreateAPIView`, `AddressDetailAPIView`, `AddressDeleteAPIView`, `SetDefaultAddressAPIView`, `WishListAPIView`, `ToggleWishListAPIView`, `RemoveFromWishListAPIView`, `LogoutAPIView`, and refactored `ProfileAPIView`. |
| [`api_apps/accounts_api/urls.py`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/api_apps/accounts_api/urls.py) | **Modified** | Registered `/api/address/`, `/api/address/add/`, `/api/address/<slug>/`, `/api/address/<slug>/delete/`, `/api/address/delete/<slug>/`, and `/api/address/<slug>/set-default/`. |
| [`api_apps/accounts_api/serializers.py`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/api_apps/accounts_api/serializers.py) | **Modified** | Enhanced `AddressSerializer` with `to_internal_value` for `full_name` alias, GPS coordinate sanitization, and state code/name normalization. |
| [`api_apps/accounts_api/tests.py`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/api_apps/accounts_api/tests.py) | **Modified** | Added comprehensive unit tests for `AddressAPITests`, `WishListAPITests`, `LogoutAPITests`, and `ProfileAPITests` (29 passing tests in app, 41 passing in project). |
| [`api_apps/__init__.py`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/api_apps/__init__.py) | **Created** | Package initialization file for `api_apps`. |
| [`apps/accounts/models.py`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/apps/accounts/models.py) | **Modified** | Added `is_email_verified`, `temp_otp`, `is_activated`, and `otp_created_at` to `CustomUser`. Removed `EmailOTP`. |
| [`apps/accounts/admin.py`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/apps/accounts/admin.py) | **Modified** | Added verification & activation fields to `CustomUserAdmin`. |
| [`apps/accounts/tasks.py`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/apps/accounts/tasks.py) | **Modified** | Stored OTP directly on `CustomUser`, updated cleanup task. |
| [`apps/accounts/views.py`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/apps/accounts/views.py) | **Modified** | Replaced `EmailOTP` queries with `user.temp_otp` validation across all authentication views. |
| [`apps/accounts/tests.py`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/apps/accounts/tests.py) | **Modified** | Added unit and integration tests for CustomUser OTP and verification flow. |
| [`apps/accounts/migrations/0003_...py`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/apps/accounts/migrations/0003_customuser_is_activated_customuser_is_email_verified_and_more.py) | **Created** | Database migration for new user fields and removal of `EmailOTP`. |
| [`README.md`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/README.md) | **Modified** | Updated architecture documentation to reflect `temp_otp` on `CustomUser`. |
| [`apps/products/validators.py`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/apps/products/validators.py) | **Created** | Comprehensive image validation (Pillow verification, 10MB limit, extensions, cursor reset). |
| [`ai_store/storage.py`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/ai_store/storage.py) | **Modified** | Added stream reset (`content.seek(0)`) in `_save` before Cloudinary upload. |
| [`apps/admin_pannel/views.py`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/apps/admin_pannel/views.py) | **Modified** | Added validation, atomic transactions, error messages, and flexible ID/slug/name resolution. |
| [`templates/adminpanel/admin_product_add.html`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/templates/adminpanel/admin_product_add.html) | **Modified** | Preserved form data, added client-side image validation, disabled empty gallery inputs on submit. |
| [`templates/adminpanel/admin_product_edit.html`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/templates/adminpanel/admin_product_edit.html) | **Modified** | Added client-side image validation and disabled empty gallery inputs on submit. |
| [`templates/adminpanel/admin_variant_edit.html`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/templates/adminpanel/admin_variant_edit.html) | **Modified** | Color `<select>` dropdown, stock quantity binding, and `is_active` checkbox toggle. |
| [`templates/adminpanel/admin_variant_add.html`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/templates/adminpanel/admin_variant_add.html) | **Modified** | Added `is_active` checkbox toggle. |
| [`api_apps/products_api/serializers.py`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/api_apps/products_api/serializers.py) | **Created** | DRF Serializers for `Category`, `Color`, `Stock`, `ProductImage`, `Review`, `ProductVariant`, and `Product` (List, Detail, Create/Update). |
| [`api_apps/products_api/tests.py`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/api_apps/products_api/tests.py) | **Created** | 10 comprehensive unit tests verifying data integrity, validations, and nested representations for product serializers. |
| [`changing.md`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/changing.md) | **Modified** | Comprehensive documentation of recent fixes and architectural changes. |

---

## 8. Products Model DRF Serializers (`api_apps/products_api/serializers.py`)

### 📌 Overview
Created DRF ModelSerializers tailored directly to the models in [`apps/products/models.py`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/apps/products/models.py):

1. **`CategorySerializer`**:
   - Fields: `id`, `name`, `slug`, `product_count`.
   - `product_count`: SerializerMethodField returning the count of active products.

2. **`ColorSerializer`**:
   - Fields: `id`, `name`, `hex_code`, `slug`.

3. **`StockSerializer`**:
   - Fields: `id`, `variant`, `quantity`, `reserved_quantity`, `available_quantity`, `slug`.
   - `available_quantity`: read-only property returning `max(0, quantity - reserved_quantity)`.

4. **`ProductImageSerializer`**:
   - Fields: `id`, `product`, `image`, `alt_text`, `created_at`.

5. **`ReviewSerializer`**:
   - Fields: `id`, `user`, `username`, `user_full_name`, `product`, `rating`, `image`, `product_review`, `slug`, `created_at`.
   - Rating validation (1 to 5 stars).

6. **`ProductVariantSerializer`**:
   - Fields: `id`, `product`, `product_name`, `color`, `color_details`, `size`, `sku`, `slug`, `price`, `name`, `is_active`, `is_in_stock`, `stock_quantity`.
   - Nested `color_details` via `ColorSerializer`.

7. **`ProductListSerializer`**:
   - Optimized for catalog/listing views.
   - Includes computed model properties: `price`, `min_price`, `max_price`, `in_stock`, `average_rating`, `review_count`, and nested categories `cat`.

8. **`ProductDetailSerializer` (aliased as `ProductSerializer`)**:
   - Full product representation with nested `variants`, `images`, `reviews`, and `cat`.

9. **`ProductCreateUpdateSerializer`**:
   - Handles write operations for products.
   - Image validation using `validate_uploaded_image`.

### 🧪 Testing
- **Test Suite**: [`api_apps/products_api/tests.py`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/api_apps/products_api/tests.py)
- **Results**: 10 out of 10 tests passed (`OK` in 3.35s).

---

## 9. Products REST API Implementation (`api_apps/products_api/views.py` & `urls.py`)

### 📌 Overview
Built a production-grade REST API for products matching the architecture of [`apps/products/views.py`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/apps/products/views.py) and DRF standards:

1. **`ProductListAPIView` (`/api/products/`, `/api/products/list/`)**:
   - **`GET`**: Catalog listing with filters:
     - Search: `?q=<term>` (matches name, description, brand, category name).
     - Category filter: `?category=<slug_or_id>`.
     - Brand filter: `?brand=<name>`.
     - Price range: `?price=min-max` or single value `?price=val`, plus `?min_price=` and `?max_price=`.
     - Sorting: `?sort=` (`price_low`, `price_high`, `name`, `name_desc`, `newest`).
     - Pagination: `?page=1&page_size=12` (DRF pagination metadata with `total_count`, `total_pages`, `current_page`, `has_next`, `has_previous`).
     - Includes `wishlist_product_ids` for authenticated users.
   - **`POST`**: Create product using `ProductCreateUpdateSerializer` (requires authentication).

2. **`ProductDetailAPIView` (`/api/products/<slug>/` & `/api/product/<slug>/`)**:
   - **`GET`**: Full product details including:
     - `product`: serialized by `ProductDetailSerializer` (all fields, gallery images, variants, reviews).
     - `selected_variant`: specified by `?variant=<slug_or_id>` or defaults to first active variant.
     - `is_wishlisted`: whether the authenticated user has wishlisted the product.
     - `user_has_reviewed`: whether the authenticated user has already reviewed the product.
     - `related_products`: top 4 active products in the same category.
   - **`PUT` / `PATCH`**: Update product details (requires `IsStaffOrSuperuser`).
   - **`DELETE`**: Deactivate/soft-delete product (requires `IsStaffOrSuperuser`).

3. **`ProductReviewAPIView` (`/api/products/<slug>/reviews/`)**:
   - **`GET`**: Lists reviews for the product, with average rating, review count, and user's existing review.
   - **`POST`**: Submit or update review (requires authentication):
     - Validates rating (1–5).
     - Validates uploaded images with Pillow header verification.
     - Performs `Review.objects.get_or_create(...)` to allow clean review updates.
   - **`DELETE`**: Deletes the user's review for the product.

4. **`CategoryListAPIView` & `CategoryDetailAPIView` (`/api/categories/`, `/api/categories/<slug>/`)**:
   - **`GET`**: Public read access to all categories or category with active products.
   - **`POST`**: Create new category (strictly restricted to `IsStaffOrSuperuser`).
   - **`PUT` / `PATCH`**: Update category name/slug (strictly restricted to `IsStaffOrSuperuser`).
   - **`DELETE`**: Delete category (strictly restricted to `IsStaffOrSuperuser`).

5. **`ColorListAPIView` & `ColorDetailAPIView` (`/api/colors/`, `/api/colors/<slug>/`)**:
   - **`GET /api/colors/`**: Public read access to list all colors with hex codes.
   - **`POST /api/colors/`**: Create a new color (restricted to `IsStaffOrSuperuser`).
   - **`GET /api/colors/<slug>/`**: Public read access to single color detail with count and list of active products available in that color.
   - **`PUT` / `PATCH /api/colors/<slug>/`**: Update color name or hex code (restricted to `IsStaffOrSuperuser`).
   - **`DELETE /api/colors/<slug>/`**: Delete color (restricted to `IsStaffOrSuperuser`).

### 🔒 Security & Flexible Features
- **`cat_slug` & Slug Resolution**: `ProductCreateUpdateSerializer` and `ProductListAPIView.post` flexibly support passing category slugs instead of raw database IDs:
  - via JSON payload: `"cat_slug": "smartphones-tablets"` or `"cat_slug": ["phones", "laptops"]`
  - via URL query parameter: `POST /api/products/?cat_slug=smartphones-tablets`
  - Supports comma-separated strings (`"phones,tablets"`), slug strings, and numeric IDs with automatic resolution and clear validation errors.
- **`IsStaffOrSuperuser` Permission**: Normal customers can only read (`GET`) or submit reviews (`POST /api/products/<slug>/reviews/`). Only accounts with `user.is_staff=True` or `user.is_superuser=True` are permitted to create, update, or delete products, categories, and colors. Unauthorized attempts return `HTTP 403 Forbidden`.

### 🧪 Verification
- **Automated Tests**: Updated `ProductAPITests` in [`api_apps/products_api/tests.py`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/api_apps/products_api/tests.py).
- **Results**:
  - `api_apps.products_api`: **34/34 tests passing (`OK` in 24.05s)**.
  - Full API suite (`api_apps.accounts_api` + `api_apps.products_api`): **64/64 tests passing (`OK` in 36.71s)**.

---

## 10. Implementation: Unified Cart REST API (`api_apps/cart_api`)

Consolidated all 6 template cart views (`cart`, `add_to_cart`, `increase_quantity`, `decrease_quantity`, `remove_from_cart`, `clear_cart`) into **only 2 clean, unified REST API classes**:

### Architecture & Classes
1. **`CartAPIView` (`/api/cart/`)**:
   - **`GET`**: View full cart with items, count, subtotal, shipping fee calculation (free shipping over ₹500), and coupon discounts. Seamlessly supports both **logged-in database carts** and **guest session carts**.
   - **`POST`**: Add an item to the cart by `variant_slug` (with Product slug fallback) and `quantity`. Validates stock availability.
   - **`DELETE`**: Clear all items from the cart.

2. **`CartItemAPIView` (`/api/cart/items/<slug:variant_slug>/`)**:
   - **`PATCH`**: Update item quantity. Supports:
     - By action: `{"action": "increase"}` or `{"action": "decrease"}` (automatically removes item if quantity reaches 0).
     - By explicit target quantity: `{"quantity": 3}`.
   - **`DELETE`**: Remove a specific item from the cart.

### Serializers Created (`api_apps/cart_api/serializers.py`)
- **`CartItemSerializer`**: Flattened representation including `product_name`, `product_slug`, `variant_name`, `variant_slug`, `brand`, `color`, `color_hex`, `size`, `price`, `total_price`, and `image`.
- **`CartSerializer`**: Cart metadata and nested items list.
- **`CartActionSerializer`**: Unified validator for all cart operations (`variant_slug`, `quantity`, `action`).

### 🧪 Automated Verification
- Added `CartAPITests` in [`api_apps/cart_api/tests.py`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/api_apps/cart_api/tests.py) covering:
  - Guest empty cart retrieval.
  - Guest add-to-cart, view, increase quantity, decrease quantity, remove item, and clear cart.
  - Authenticated database cart creation, quantity updating, and database persistence.
  - 404 on non-existent variant.
  - Stock validation (preventing adding more units than available in `Stock`).
- **Results**: **7/7 tests passing (`OK` in 2.05s)**.

---

## 11. Implementation: Guest Cart Merge on Login (`api_apps/accounts_api`)

Added automatic cart merge into [`LoginAPIView`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/api_apps/accounts_api/views.py#L26) and [`VerifyOTPAPIView`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/api_apps/accounts_api/views.py#L295):

### Features & Capabilities
1. **Web Browser Session Cart Merge**:
   - Reads `request.session["cart"]` and merges all items into the user's database `Cart`.
   - Clears session cart upon successful merge.
2. **Mobile App & SPA LocalStorage Cart Merge**:
   - Accepts an optional `cart` array or object directly in the `POST /api/login/` body:
     ```json
     {
       "username": "...",
       "password": "...",
       "cart": [
         {"variant_slug": "iphone-16-black-128", "quantity": 2}
       ]
     }
     ```
3. **Instant Cart Summary in Login Response**:
   - Returns the updated `total_items` and `total_price` directly in the login response payload so frontend badges update with zero extra API requests:
     ```json
     {
       "success": true,
       "token": "...",
       "user": {...},
       "cart": {
         "total_items": 2,
         "total_price": "1998.00"
       }
     }
     ```

### 🧪 Automated Verification
- Added `LoginAndCartMergeAPITests` in [`api_apps/accounts_api/tests.py`](file:///c:/Users/sumit/OneDrive/Desktop/ai_store/api_apps/accounts_api/tests.py):
  - Verified standard credential login.
  - Verified cart payload merge into database `CartItem` models.
- **Results**: `api_apps.accounts_api`: **32/32 tests passing (`OK` in 15.00s)**.


