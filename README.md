# 🛍️ AI Store — Technical Documentation & Architecture Manual

> **AI Store** is an enterprise-grade, full-stack E-Commerce platform built with **Django 6.0**, **Django Channels (ASGI / WebSockets)**, **Celery**, **Redis**, **PostgreSQL**, **Cloudinary**, **Razorpay Payment Gateway**, and an **Autonomous LangChain AI Shopping Assistant**.

---

## 📑 Table of Contents

1. [System Architecture & Tech Stack](#-system-architecture--tech-stack)
2. [Project Directory Structure](#-project-directory-structure)
3. [Core Application Modules](#-core-application-modules)
   - [Accounts & Authentication](#1-accounts--authentication-appsaccounts)
   - [Product Catalog & Inventory](#2-product-catalog--inventory-appsproducts)
   - [Cart & Checkout](#3-cart--checkout-appscart)
   - [Orders & Fulfillment](#4-orders--fulfillment-appsorder)
   - [Payments & Webhooks (Razorpay)](#5-payments--webhooks-appspayment)
   - [Dynamic Coupon Engine](#6-dynamic-coupon-engine-appscoupons)
   - [Real-Time Customer Support Chat (WebSockets)](#7-real-time-customer-support-chat-appschat)
   - [Admin Panel & Staff Delegation (RBAC)](#8-admin-panel--staff-delegation-appsadmin_pannel)
   - [LangChain AI Shopping Assistant](#9-langchain-ai-shopping-assistant-ai)
4. [Database Structure & Entity Relationships](#-database-structure--entity-relationships)
5. [REST API Documentation & Endpoints Catalog](#-rest-api-documentation--endpoints-catalog)
6. [WebSockets & Real-Time Messaging](#-websockets--real-time-messaging)
7. [Asynchronous Background Tasks (Celery & Redis)](#-asynchronous-background-tasks-celery--redis)
8. [Media Management & Cloudinary Optimization](#-media-management--cloudinary-optimization)
9. [Environment Variables Reference](#-environment-variables-reference)
10. [Docker Setup & Deployment Guide](#-docker-setup--deployment-guide)
11. [Installation & Local Setup Guide](#-installation--local-setup-guide)
12. [Testing & Quality Assurance](#-testing--quality-assurance)
13. [Troubleshooting & FAQ](#-troubleshooting--faq)

---

## 🏗️ System Architecture & Tech Stack

```
                          ┌───────────────────────────────────────┐
                          │         Web Browser / API Client      │
                          └──────────────────┬────────────────────┘
                                             │
                       HTTP / HTTPS (Port 8000)  │  WebSockets (ws://)
                                             │
                          ┌──────────────────▼────────────────────┐
                          │          Daphne ASGI Server           │
                          │   (ProtocolTypeRouter + URLRouter)    │
                          └───────┬───────────────────────┬───────┘
                                  │                       │
                     HTTP Requests│                       │ WebSocket Frames
                                  ▼                       ▼
            ┌─────────────────────────────┐   ┌─────────────────────────────┐
            │     Django 6.0 Core App     │   │      ChatConsumer (ASGI)    │
            │   - Session & Token Auth    │   │  - Slug-based chat rooms    │
            │   - Timezone Middleware     │   │  - Granular permissions     │
            │   - REST Framework APIs     │   │  - Read receipts & status   │
            │   - LangChain AI Assistant  │   │  - channels_redis Layer     │
            └──────────────┬──────────────┘   └──────────────┬──────────────┘
                           │                                 │
           ┌───────────────┼────────────────┐                │
           ▼               ▼                ▼                ▼
┌──────────────────┐ ┌───────────┐ ┌──────────────────────────────────┐
│ PostgreSQL 16 DB │ │Cloudinary │ │        Redis 7 In-Memory         │
│  - Persistent Vol│ │ CDN Media │ │  - Channels Pub/Sub Layer        │
│  - ACID & Locks  │ │ f_auto    │ │  - Celery Message Broker         │
│  - Full Relational│ │ q_auto    │ │  - Celery Result Backend         │
└──────────────────┘ └───────────┘ └─────────────────┬────────────────┘
                                                     │
                                                     │ Celery Tasks
                                                     ▼
                                   ┌──────────────────────────────────┐
                                   │      Celery Worker Process       │
                                   │  - Asynchronous OTP Emails       │
                                   │  - Welcome Emails                │
                                   │  - Bulk Coupon Announcements     │
                                   │  - Expired OTP Cleanup           │
                                   └─────────────────┬────────────────┘
                                                     │
                                                     ▼
                                   ┌──────────────────────────────────┐
                                   │      SMTP Mail Gateway (Gmail)   │
                                   └──────────────────────────────────┘
```

### Core Technologies

| Layer | Component | Version / Description |
| :--- | :--- | :--- |
| **Backend Framework** | Django | `>= 6.0, < 7.0` |
| **ASGI / WebSockets** | Daphne + Django Channels | Daphne `4.2.0`, Channels `4.3.0` |
| **Channel Layer** | `channels_redis` | `>= 4.3.0` (Redis backed) |
| **Database** | PostgreSQL | `16-alpine` (Docker) / SQLite fallback |
| **In-Memory Cache & Broker** | Redis | `7-alpine` |
| **Task Queue** | Celery | `>= 5.6.0` (JSON serialization) |
| **REST APIs** | Django REST Framework (DRF) | `>= 3.15.0` (Token & Session Auth) |
| **AI / Agentic Framework** | LangChain Core / Community | `0.3.x` with OpenAI, Groq, NVIDIA integration |
| **Payment Gateway** | Razorpay SDK | `>= 2.0.0` (HMAC SHA-256 signature verification) |
| **Cloud Media Storage** | Cloudinary Storage | `cloudinary 1.46.0`, `django-cloudinary-storage 0.3.0` |
| **Containerization** | Docker & Docker Compose | Multi-container setup (`db`, `redis`, `web`, `celery`) |

---

## 📁 Project Directory Structure

```
ai_store/
├── .env                              # Active local environment variables
├── .env.example                      # Production & development template
├── .dockerignore                     # Docker build exclusions
├── .gitignore                        # Git repository exclusions
├── Dockerfile                        # Python 3.12-slim container definition
├── docker-compose.yml                # 4-tier service orchestration
├── manage.py                         # Django execution utility
├── requirements.txt                  # Pinned Python package dependencies
├── RUNNING.md                        # Quick command cheatsheet
├── datadump_postgres.json            # Database seed fixture
├── postgres_backup.sql               # Full SQL backup dump
├── media/                            # Local media uploads directory
├── static/                           # Global static assets (CSS, JS, images)
├── templates/                        # Global HTML template overrides
│
├── ai_store/                         # Core Project Configuration
│   ├── __init__.py                   # Celery app export initialization
│   ├── asgi.py                       # ProtocolTypeRouter (HTTP + WebSocket)
│   ├── celery.py                     # Celery application configuration
│   ├── middleware.py                 # Dynamic UserTimezoneMiddleware
│   ├── settings.py                   # Master configuration settings
│   ├── storage.py                    # OptimizedMediaCloudinaryStorage backend
│   ├── urls.py                       # Root URL routing table
│   └── wsgi.py                       # WSGI entry point
│
├── apps/                             # Business Logic & Web Applications
│   ├── accounts/                     # CustomUser, Profile, Address, Wishlist, OTP tasks
│   ├── products/                     # Product, Variant, Category, Color, Stock, Review
│   ├── cart/                         # Cart, CartItem, Guest session merging
│   ├── order/                        # Order, OrderItem, Checkout & placement
│   ├── payment/                      # Payment tracking, Razorpay client & webhooks
│   ├── coupons/                      # Coupon, CouponUsage, Validation service
│   ├── chat/                         # Conversation, Message, ChatConsumer WebSocket
│   └── admin_pannel/                 # Admin dashboard, RBAC, Staff delegation
│
├── api_apps/                         # Django REST Framework Endpoints
│   ├── accounts_api/                 # Auth, Profile, Address, Wishlist APIs
│   ├── products_api/                 # Catalog, Variants, Categories, Reviews APIs
│   ├── cart_api/                     # Cart CRUD & Quantity adjustment APIs
│   ├── orders_api/                   # Order placement, History, Cancellation APIs
│   ├── coupons_api/                  # Coupon validation, Application, Quota APIs
│   ├── payment_api/                  # Razorpay order creation, Verification APIs
│   ├── chat_api/                     # Support tickets, Message history APIs
│   └── admin_api/                    # Staff management & User administration APIs
│
└── ai/                               # Autonomous Dynamic Shopping Agent (LangGraph)
    ├── agent.py                      # LangGraph agent graph factory
    ├── context.py                    # ContextVar thread-safe user injection
    ├── state.py                      # LangGraph AgentState schema
    ├── graph.py                      # Compiled dynamic StateGraph
    ├── nodes.py                      # Agent reasoning & sequential tool executor nodes
    ├── llm.py                        # Model provider router (Groq, OpenAI, NVIDIA NIM)
    ├── prompts.py                    # System prompt with domain instructions & reference resolution
    ├── services.py                   # Synchronous & Async runner services
    ├── views.py                      # /api/ai/chat/ API endpoint
    ├── tools/                        # 18 Deterministic LangChain Tools
    │   ├── products.py               # Search, details, stock, pricing, category, brand
    │   ├── cart.py                   # Get cart, add, remove, update quantities
    │   ├── wishlist.py               # Get wishlist, add, remove, check status
    │   └── orders.py                 # Get orders, order details, track status
    └── tests/                        # Comprehensive unit & integration test suite
```

---

## 🧩 Core Application Modules

### 1. Accounts & Authentication (`apps.accounts`)

#### Data Models:
* **`CustomUser` (`AbstractUser`)**:
  * Inherits from `django.contrib.auth.models.AbstractUser`.
  * `email`: Unique email field (case-insensitive normalized).
  * `is_email_verified`: Boolean flag indicating OTP email confirmation.
  * `temp_otp`: 6-digit one-time password stored directly on the user model.
  * `otp_created_at`: Timestamp tracking OTP issuance (valid strictly for 10 minutes).
  * `is_activated`: Account status flag.
  * `slug`: Dynamic property resolving to `profile.slug` or username.
* **`Profile`**:
  * One-to-one relationship with `CustomUser`.
  * `phone`: Contact telephone number.
  * `profile_picture`: ImageField uploaded to `profile_pic/` (defaults to `default/x.jpg`).
  * `slug`: Auto-generated unique slug.
* **`Address`**:
  * Linked to `CustomUser` (`ForeignKey`).
  * Full shipping details: `name`, `phone`, `pincode`, `locality`, `address_line`, `city`, `state` (36 Indian States & UTs choices), `landmark`, `address_type` (`HOME` / `WORK`), `is_default`.
  * **GPS Geolocation Fields**: `latitude`, `longitude`, `area`, `formatted_address` captured from browser location APIs.
* **`WishList`**:
  * Unique pair constraint: `unique_together = ("user", "product")`.
  * Allows registered users to bookmark products.

#### Authentication Workflow:
1. **Registration**: User submits registration form. Account is created in an unverified state (`is_email_verified=False`).
2. **OTP Dispatch**: A 6-digit numeric OTP is generated and dispatched asynchronously via Celery (`send_otp_email_task`).
3. **Verification**: User inputs OTP at `/verify-otp/`. If valid within 10 minutes, `is_email_verified` becomes `True`, and a welcome email is sent via `send_registration_email.delay(user.id)`.
4. **Password Reset**: Secure forgot-password flow via `/forgot-password/` and `/verify-reset-otp/` using temporary session tokens and email OTPs.
5. **Session Cart Merging**: Upon login, any guest shopping cart stored in `request.session["cart"]` is automatically merged into the user's persistent database cart.

---

### 2. Product Catalog & Inventory (`apps.products`)

#### Data Models:
* **`Category`**: Hierarchical classification with unique auto-generated slug.
* **`Color`**: Product color variation with `name`, `hex_code`, and unique `slug`.
* **`Product`**:
  * Primary product entity linked to multiple categories (`ManyToManyField`).
  * Fields: `name`, `slug`, `image`, `description`, `brand`, `is_active`.
  * Computed properties:
    * `default_variant`: Returns the first active variant.
    * `price`: Price of the default variant.
    * `min_price` / `max_price`: Range across all active variants.
    * `in_stock`: Boolean check whether available stock exceeds zero.
    * `average_rating`: Aggregated star rating (1 to 5) rounded to 1 decimal place.
    * `review_count`: Total approved user reviews.
* **`ProductVariant`**:
  * Concrete SKU unit representing a specific combination of Color and Size.
  * Fields: `product`, `color`, `size`, `sku` (unique), `slug`, `price`, `is_active`.
  * Computed properties: `name` (e.g. `"Product Name (Red / L)"`), `is_in_stock`.
* **`Stock`**:
  * One-to-one link with `ProductVariant`.
  * `quantity`: Total physical units in warehouse.
  * `reserved_quantity`: Units allocated to processing orders.
  * `available_quantity`: Computed property: `max(0, quantity - reserved_quantity)`.
* **`Review`**: Star rating (1 to 5), optional uploaded image (`review_img/`), and review text submitted by verified customers.
* **`ProductImage`**: Supplementary product gallery photos (`product/gallery/`).

---

### 3. Cart & Checkout (`apps.cart`)

#### Storage Mechanisms:
1. **Authenticated Users**: Stored persistently in PostgreSQL tables `Cart` and `CartItem`.
2. **Guest Visitors**: Stored in session storage (`request.session["cart"] = { "<variant_slug>": {"quantity": 2} }`).

#### Cart Features:
* **Atomic Cart Merging**: When a guest logs in, `merge_session_cart_to_user` consolidates guest session items into the user's database cart without losing existing quantities.
* **Stock Validation**: Quantity increases verify that requested units do not exceed `variant.stock.available_quantity`.
* **Subtotal Calculation**: Dynamic computation of item subtotal, discounts, and shipping.

---

### 4. Orders & Fulfillment (`apps.order`)

#### Data Models:
* **`Order`**:
  * `order_number`: Unique business tracking code.
  * `status`: Choices: `pending_payment`, `pending`, `confirmed`, `processing`, `shipped`, `delivered`, `cancelled`.
  * `total_amount`: Final payable amount after discounts and shipping.
  * `coupon`: ForeignKey to `apps.coupons.Coupon` (null on delete).
  * `discount_amount`: Value discounted via applied coupon.
  * Shipping details snapshot: `shipping_name`, `shipping_phone`, `shipping_city`, `shipping_pincode`, `shipping_address`.
* **`OrderItem`**:
  * Line items linking the order to `ProductVariant` with fixed purchase `price` and `quantity`.

#### Shipping Fee Rules:
* If order subtotal $\ge$ **₹500.00** $\rightarrow$ **Free Shipping (₹0.00)**.
* If order subtotal $<$ **₹500.00** $\rightarrow$ **Standard Shipping: ₹50.00**.

---

### 5. Payments & Webhooks (`apps.payment`)

#### Payment Architecture:
* **Supported Gateways**: Cash on Delivery (`cod`) and Razorpay Online (`razorpay` / `online`).
* **Model (`Payment`)**:
  * `order`: One-to-one relationship with `Order`.
  * `payment_method`: `cod`, `online`, `razorpay`, `upi`, `card`, `netbanking`.
  * `transaction_id`: Gateway payment identifier.
  * `gateway_order_id`: Razorpay Order ID (`order_...`).
  * `gateway_payment_id`: Razorpay Payment ID (`pay_...`).
  * `gateway_signature`: Razorpay cryptographic signature.
  * `status`: `pending`, `completed`, `failed`, `refunded`.
  * `paid_at`: Completion timestamp.

#### Razorpay Online Payment Flow:
1. User clicks **"Pay Online"** at `/checkout/`.
2. Backend calls `create_razorpay_order(order)` via `razorpay.Client(auth=(KEY, SECRET))`. The order amount is converted to **paise** ($1 \text{ INR} = 100 \text{ paise}$).
3. Razorpay returns an `order_id`. The client-side Razorpay modal is launched.
4. Upon successful payment on the frontend, payment credentials (`razorpay_order_id`, `razorpay_payment_id`, `razorpay_signature`) are posted to `/payment/verify/`.
5. **Cryptographic Verification**: `client.utility.verify_payment_signature(params_dict)` verifies the HMAC SHA-256 signature.
6. **Atomic Completion (`complete_order_payment`)**:
   * Updates `Payment` record status to `completed` with `paid_at=timezone.now()`.
   * Updates `Order` status to `confirmed`.
   * Automatically deducts purchased quantities from `Stock.quantity`.
   * Idempotently records coupon usage in `CouponUsage`.
   * Clears the user's active shopping cart items.
7. **Webhook Handler (`/payment/webhook/`)**:
   * Validates incoming webhook signature against `RAZORPAY_WEBHOOK_SECRET`.
   * Listens for `payment.captured` and `order.paid` events to ensure orders are confirmed even if the user closes their browser before redirection.

---

### 6. Dynamic Coupon Engine (`apps.coupons`)

#### Data Models:
* **`Coupon`**:
  * `code`: Case-insensitive unique promo code (e.g. `SAVE20`).
  * `discount_type`: `percentage` (%) or `fixed` (₹).
  * `discount_value`: Percentage or fixed amount.
  * `minimum_order_amount`: Minimum subtotal required.
  * `maximum_discount_amount`: Cap for percentage discounts (e.g., max ₹500 off).
  * `valid_from` & `valid_until`: Timezone-aware validity window.
  * `usage_limit`: Maximum total global redemptions across all users.
  * `used_count`: Actual redemption tally.
  * `per_user_limit`: Maximum lifetime redemptions per individual user.
  * `weekly_user_limit`: Maximum redemptions per user within a calendar week (default: 5).
  * `is_active`: Master activation toggle.
* **`CouponConfiguration` (Singleton)**:
  * Global configuration model storing store-wide coupon policy (`weekly_user_limit`).
* **`CouponUsage`**:
  * Audit ledger recording every successful coupon redemption tied to a completed `Order`.
  * Indexed on `[user, used_at]` and `[coupon, user]`.

#### 10-Step Validation Rule Chain (`validate_coupon_for_user`):
1. **User Authentication**: User must be authenticated.
2. **Code Existence**: Code exists in database (case-insensitive lookup).
3. **Active Status**: `coupon.is_active` must be `True`.
4. **Time Window**: Current time falls strictly between `valid_from` and `valid_until`.
5. **Weekly User Limit**: Current week usage count (Monday 00:00:00 to Sunday 23:59:59) is strictly less than `weekly_user_limit`.
6. **Global Usage Cap**: `used_count` has not reached `usage_limit`.
7. **Per-User Lifetime Limit**: Redemptions by this user do not exceed `per_user_limit`.
8. **Minimum Cart Subtotal**: Cart subtotal $\ge$ `minimum_order_amount`.
9. **Discount Calculation**: Computes percentage or fixed discount, applying `maximum_discount_amount` cap if defined.
10. **Cart Ceiling**: Ensures discount does not exceed cart subtotal (total cannot be negative).

---

### 7. Real-Time Customer Support Chat (`apps.chat`)

#### Architecture:
* Built on **Django Channels** and **ASGI** using `channels_redis`.
* URL Pattern: `ws://<host>/ws/chat/<conversation_slug>/`.
* Protocol: Asynchronous JSON WebSocket frames handled by `ChatConsumer`.

#### Data Models:
* **`Conversation`**: Customer ticket thread with `user`, `status` (`open`, `pending`, `resolved`, `closed`), and unique `slug` (e.g. `ticket-username-a1b2c3d4`).
* **`Message`**: Individual message record with `conversation`, `sender`, `message`, `is_read`, and `created_at`.

#### Granular Role-Based Permissions in Chat:
* **Superusers**: Full authorization to join any room, reply, and change status.
* **Staff with `chat.view_conversation`**: Can monitor all customer rooms.
* **Staff with `chat.add_message`**: Can send replies to customer rooms.
* **Staff with `chat.change_conversation`**: Can change ticket status (e.g., mark as `resolved` or `closed`).
* **Normal Customers**: Strictly restricted to their own conversation thread (attempts to access other rooms result in WebSocket close code `4003`).
* **Unauthenticated Visitors**: Connection rejected with close code `4001`.

#### WebSocket Actions & Events:
* `action: "message"` $\rightarrow$ Dispatches `chat_message` to channel group.
* `action: "status_change"` $\rightarrow$ Updates ticket status and dispatches `status_broadcast`.
* `action: "mark_read"` $\rightarrow$ Marks incoming messages as read and dispatches `read_broadcast`.

---

### 8. Admin Panel & Staff Delegation (`apps.admin_pannel`)

#### Custom Admin Dashboard:
* Dedicated dashboard at `/adminpanel/dashboard/` providing real-time metrics:
  * Total revenue, orders breakdown, customer registrations.
  * Low stock alerts and pending order notifications.
  * Direct CRUD management for Products, Variants, Categories, Colors, Coupons, and Orders.

#### Granular Staff RBAC System:
* Store owners can designate non-staff users as **Staff Members** and assign granular Django permissions without giving them superuser privileges.
* Managed permissions encompass:
  * `products.*` (`add_product`, `change_product`, `delete_product`, etc.)
  * `coupons.*` (`add_coupon`, `change_coupon`, `delete_coupon`, etc.)
  * `order.*` (`change_order`, `view_order`, etc.)
  * `chat.*` (`view_conversation`, `add_message`, `change_conversation`)
  * `accounts.*` (`view_customuser`, etc.)
* Enforced across custom views via `@staff_perm_required('perm_name')` and `@superuser_required`.

---

### 9. LangChain AI Shopping Assistant (`ai`)

#### Architecture:
* **Framework**: LangChain 0.3 tool-calling agent created via `langchain.agents.create_agent`.
* **Model Providers (`ai/llm.py`)**:
  * **Groq** (`ChatGroq`): e.g. `llama-3.3-70b-versatile` (Ultra-low latency inference).
  * **OpenAI** (`ChatOpenAI`): e.g. `gpt-4o-mini`.
  * **NVIDIA NIM** (`ChatNVIDIA` or `ChatOpenAI` with NVIDIA Base URL): e.g. `meta/llama-3.3-70b-instruct`.
* **Thread-Safe Context Isolation (`ai/context.py`)**:
  * Uses Python's standard `contextvars.ContextVar` to inject the authenticated Django `request.user` into the execution context.
  * Tools dynamically call `get_current_user()` to interact with the database on behalf of the user without exposing user IDs in LLM prompts.

#### The 18 LangChain Tools:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        LangChain Tool Registry                         │
├──────────────────┬─────────────────┬──────────────────┬────────────────┤
│  Product Tools   │   Cart Tools    │  Wishlist Tools  │  Order Tools   │
├──────────────────┼─────────────────┼──────────────────┼────────────────┤
│ search_products  │ get_cart        │ get_wishlist     │ get_orders     │
│ get_product_det. │ add_to_cart     │ add_to_wishlist  │ get_order_det. │
│ check_stock      │ remove_from_cart│ remove_from_wish │ get_order_stat.│
│ get_product_price│ update_cart     │ check_wishlist   │                │
│ search_category  │                 │                  │                │
│ search_by_brand  │                 │                  │                │
│ search_by_price  │                 │                  │                │
└──────────────────┴─────────────────┴──────────────────┴────────────────┘
```

#### Dynamic LangGraph Orchestration & Sequential Execution:
* **Fully Dynamic Tool Decision Loop:** The LangGraph agent inspects user intent, dynamically chains required tools step-by-step (e.g., brand search $\rightarrow$ price check $\rightarrow$ stock validation $\rightarrow$ add to cart), and decides when enough information is gathered to formulate the final answer.
* **Strictly Sequential Execution:** Tools execute sequentially one-by-one with structured error checking (no `asyncio.gather()` or parallel concurrency).
* **Conversational Context & State:** Tracks `messages`, `current_product`, and `tool_results` in `AgentState` to resolve natural follow-ups such as *"that one"*, *"the cheapest one"*, or *"add it to my cart"*.
* **ContextVar Security:** Scopes all authenticated operations (cart, wishlist, orders) to Django's `request.user` without accepting `user_id` from client payloads.

---

## 🗄️ Database Structure & Entity Relationships

```mermaid
erDiagram
    CustomUser ||--o| Profile : "has one"
    CustomUser ||--o{ Address : "owns many"
    CustomUser ||--o{ WishList : "saves many"
    CustomUser ||--o| Cart : "has active"
    CustomUser ||--o{ Order : "places many"
    CustomUser ||--o{ Payment : "initiates"
    CustomUser ||--o{ Conversation : "starts"
    CustomUser ||--o{ CouponUsage : "redeems"

    Product ||--|{ Category : "categorized by"
    Product ||--|{ ProductVariant : "has variants"
    Product ||--o{ Review : "reviewed by"
    Product ||--o{ ProductImage : "gallery images"

    ProductVariant ||--o| Color : "has color"
    ProductVariant ||--|| Stock : "has inventory"
    ProductVariant ||--o{ CartItem : "in cart items"
    ProductVariant ||--o{ OrderItem : "in order items"

    Cart ||--o{ CartItem : "contains items"

    Order ||--o{ OrderItem : "contains items"
    Order ||--o| Payment : "settled by"
    Order ||--o| Coupon : "applies"
    Order ||--o| CouponUsage : "recorded in"

    Conversation ||--o{ Message : "contains"
    Coupon ||--o{ CouponUsage : "tracks redemptions"
```

---

## 🔌 REST API Documentation & Endpoints Catalog

All API endpoints are prefixed with `/api/` and support JSON request/response payloads.

### Authentication Headers
For protected endpoints requiring `IsAuthenticated`:
```http
Authorization: Token <your_auth_token_here>
Content-Type: application/json
```
*(Session authentication via cookies is also supported when browsing via web clients).*

---

### 1. Authentication & User APIs (`api_apps.accounts_api`)

| Method | Endpoint | Description | Auth Required |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/login/` | Authenticate user, return auth token & merge session cart | No |
| `POST` | `/api/logout/` | Invalidate DRF auth token and clear session | Yes |
| `POST` | `/api/register/` | Register new customer account (dispatches OTP) | No |
| `POST` | `/api/verify-otp/` | Confirm 6-digit registration OTP code | No |
| `POST` | `/api/forgot-password/` | Send 6-digit password reset OTP email | No |
| `POST` | `/api/verify-reset-otp/`| Validate password reset OTP | No |
| `POST` | `/api/resend-reset-otp/`| Resend password reset OTP code | No |
| `POST` | `/api/reset-password/` | Finalize password reset with new password | No |
| `GET` / `PUT` | `/api/profile/` | Retrieve or update current user profile | Yes |
| `GET` | `/api/wishlist/` | List all wishlisted products for logged-in user | Yes |
| `POST` | `/api/wishlist/toggle/` | Add/remove product from wishlist (body: `{"product_id": 1}`) | Yes |
| `POST` | `/api/wishlist/toggle/<slug>/`| Toggle product in wishlist by slug | Yes |
| `DELETE`| `/api/wishlist/remove/<slug>/`| Remove item from wishlist by slug | Yes |
| `GET` / `POST` | `/api/address/` | List addresses or create a new shipping address | Yes |
| `GET` / `PUT` / `DELETE` | `/api/address/<slug>/` | Retrieve, update, or delete shipping address | Yes |
| `POST` | `/api/address/<slug>/set-default/` | Designate address as the default shipping address | Yes |

#### Sample Login Request & Response:
```bash
curl -X POST http://127.0.0.1:8000/api/login/ \
  -H "Content-Type: application/json" \
  -d '{"username": "customer1", "password": "password123"}'
```
```json
{
  "token": "9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b",
  "user_id": 4,
  "username": "customer1",
  "email": "customer1@example.com",
  "is_staff": false,
  "cart_count": 3
}
```

---

### 2. Catalog & Products APIs (`api_apps.products_api`)

| Method | Endpoint | Description | Auth Required |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/products/` | Filterable product list (`?q=`, `?category=`, `?min_price=`, `?sort=`) | No |
| `GET` | `/api/product/<slug>/` | Detailed product info with all variants, colors, and stock | No |
| `GET` / `POST` | `/api/products/<slug>/reviews/` | List reviews or submit a new verified review | GET: No / POST: Yes |
| `GET` | `/api/categories/` | List all active product categories | No |
| `GET` | `/api/categories/<slug>/` | Get category details with nested products | No |
| `GET` | `/api/colors/` | List all product color variations | No |
| `GET` | `/api/colors/<slug>/` | Get color details and associated variants | No |

---

### 3. Shopping Cart APIs (`api_apps.cart_api`)

| Method | Endpoint | Description | Auth Required |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/cart/` | Retrieve active cart contents, item counts, and totals | Optional |
| `POST` | `/api/cart/` | Add variant to cart (`{"variant_slug": "...", "quantity": 1}`) | Optional |
| `DELETE`| `/api/cart/` | Empty active shopping cart completely | Optional |
| `PATCH` | `/api/cart/items/<variant_slug>/` | Adjust quantity (`action`: `increase`, `decrease`, `set`) | Optional |
| `DELETE`| `/api/cart/items/<variant_slug>/` | Remove item from cart | Optional |

---

### 4. Orders & Checkout APIs (`api_apps.orders_api`)

| Method | Endpoint | Description | Auth Required |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/orders/` | List user order history (supports `?status=delivered`) | Yes |
| `POST` | `/api/orders/` | Create order from cart (`shipping_address_id`, `payment_method`) | Yes |
| `GET` | `/api/orders/<identifier>/` | Get order details by `order_number` or `slug` | Yes |
| `POST` | `/api/orders/<identifier>/cancel/` | Cancel order (allowed if status is pending/confirmed) | Yes |

---

### 5. Dynamic Coupon APIs (`api_apps.coupons_api`)

| Method | Endpoint | Description | Auth Required |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/coupons/` | List available coupons and estimated discounts for user | Optional |
| `POST` | `/api/coupons/apply/` | Apply coupon code to active session/order (`{"code": "SAVE20"}`) | Yes |
| `POST` | `/api/coupons/remove/` | Remove currently applied coupon | Yes |
| `POST` | `/api/coupons/check/` | Stateless coupon eligibility check (`code`, `order_amount`) | Yes |
| `GET` | `/api/coupons/weekly-status/`| Get user's remaining weekly coupon redemption quota | Yes |
| `GET` | `/api/coupons/<identifier>/` | Retrieve coupon terms by code or slug | Optional |

---

### 6. Payments & Webhooks APIs (`api_apps.payment_api`)

| Method | Endpoint | Description | Auth Required |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/payments/` | List user payment history | Yes |
| `GET` | `/api/payments/process/<order_slug>/` | Generate Razorpay order payload (`amount`, `currency`, `key`) | Yes |
| `POST` | `/api/payments/verify/` | Verify Razorpay HMAC signature & confirm order | Yes |
| `POST` | `/api/payments/webhook/` | Razorpay webhook callback endpoint (HMAC signed) | No (Signature) |
| `GET` | `/api/payments/<identifier>/`| Get payment status by transaction ID or order number | Yes |

---

### 7. Real-Time Chat & Support Ticket APIs (`api_apps.chat_api`)

| Method | Endpoint | Description | Auth Required |
| :--- | :--- | :--- | :--- |
| `GET` / `POST` | `/api/chat/conversations/` | List support tickets or open a new conversation thread | Yes |
| `GET` | `/api/chat/stats/` | Overview stats: total open, pending, unread messages | Staff/Admin |
| `GET` / `PATCH`| `/api/chat/conversations/<slug>/` | Get ticket details or update status (`open`, `resolved`, etc.) | Yes |
| `GET` / `POST` | `/api/chat/conversations/<slug>/messages/` | List messages or post a new message to thread | Yes |
| `POST` | `/api/chat/conversations/<slug>/mark-read/` | Mark all unread messages in conversation as read | Yes |

---

### 8. Admin & Staff Delegation APIs (`api_apps.admin_api`)

| Method | Endpoint | Description | Auth Required |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/admin/staff/` | List all staff members and their active permissions | Superuser |
| `POST` | `/api/admin/staff/add/` | Promote user to staff and assign initial permissions | Superuser |
| `GET` | `/api/admin/staff/candidates/` | List non-staff users eligible for staff promotion | Superuser |
| `GET` / `PUT` | `/api/admin/staff/<user_id>/permissions/` | Inspect or update granular permissions for a staff member | Superuser |
| `POST` | `/api/admin/staff/<user_id>/remove/` | Revoke staff status and remove all delegated permissions | Superuser |
| `GET` | `/api/admin/permissions/` | List all delegable permissions for products, coupons, orders, chat | Superuser |
| `GET` / `POST` | `/api/admin/users/` | List users (with search/filter) or create admin account | Superuser |
| `GET` / `PUT` / `DELETE`| `/api/admin/users/<user_id>/` | View, update, or deactivate user account | Superuser |

---

### 9. AI Shopping Assistant API (`ai`)

| Method | Endpoint | Description | Auth Required |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/ai/chat/` | Interact with autonomous LangChain shopping assistant | Yes |

#### Sample AI Request:
```bash
curl -X POST http://127.0.0.1:8000/api/ai/chat/ \
  -H "Authorization: Token 9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Do you have any Nike shoes in stock under 5000?",
    "chat_history": []
  }'
```
#### Sample AI Response:
```json
{
  "response": "We have the **Nike Air Zoom Pegasus** available in Black and White for ₹4,499.00! Stock is currently available in sizes 8, 9, and 10. Would you like me to add a pair to your shopping cart?"
}
```

---

## ⚡ WebSockets & Real-Time Messaging

The real-time customer support subsystem utilizes Django Channels and ASGI static handling via Daphne.

### WebSocket Connection Lifecycle:

```mermaid
sequenceDiagram
    participant Client as Web / Mobile Client
    participant ASGI as Daphne / Channels Router
    participant Consumer as ChatConsumer
    participant Redis as Redis Channel Layer
    participant DB as PostgreSQL DB

    Client->>ASGI: Connect to ws://127.0.0.1:8000/ws/chat/<slug>/
    ASGI->>Consumer: connect() with AuthMiddlewareStack scope
    alt User Unauthenticated
        Consumer-->>Client: Close Code 4001 (Unauthorized)
    else User Not Permitted (Not owner & No staff perm)
        Consumer-->>Client: Close Code 4003 (Forbidden)
    else Authorized
        Consumer->>Redis: group_add("chat_<slug>", channel_name)
        Consumer-->>Client: Accept Connection
    end

    Client->>Consumer: Send JSON {"action": "message", "message": "Help!"}
    Consumer->>DB: Save Message
    Consumer->>Redis: group_send("chat_<slug>", event: chat_message)
    Redis-->>Consumer: Broadcast to group subscribers
    Consumer-->>Client: Receive JSON {"type": "message", "message": "Help!", ...}
```

### WebSocket Frame Specification:

#### 1. Send Message:
```json
{
  "action": "message",
  "message": "Hello, when will order #ORD-10293 be shipped?"
}
```

#### 2. Update Status (Staff only):
```json
{
  "action": "status_change",
  "status": "resolved"
}
```

#### 3. Mark Read:
```json
{
  "action": "mark_read"
}
```

---

## ⏱️ Asynchronous Background Tasks (Celery & Redis)

Celery 5.6 handles high-latency I/O operations asynchronously to ensure sub-millisecond web response times.

```
Celery Broker:         redis://ai_store_redis:6379 (or REDIS_URL)
Celery Result Backend: redis://ai_store_redis:6379 (or REDIS_URL)
Task Serializer:       JSON
Result Serializer:     JSON
```

### Registered Tasks (`apps/accounts/tasks.py`):

1. **`apps.accounts.tasks.send_otp_email_task`**:
   * Dispatches email with 6-digit verification code for registrations and password resets.
   * Renders HTML template `accounts/otp_email.html` with fallback plain-text email.
   * Auto-retries up to 3 times on transient SMTP failures with exponential backoff.
2. **`apps.accounts.tasks.send_registration_email`**:
   * Sends welcome email upon successful account activation.
3. **`apps.accounts.tasks.broadcast_coupon_announcement_task`**:
   * Admin can broadcast a promotional coupon announcement to all active registered customers with a single click.
   * Loops through active users, renders `adminpanel/coupon_broadcast.html`, tracks delivered vs failed metrics, and logs the result.
4. **`apps.accounts.tasks.cleanup_expired_otps_task`**:
   * Maintenance task to nullify `temp_otp` older than 10 minutes from database records.

---

## ☁️ Media Management & Cloudinary Optimization

All media assets (product images, variant galleries, user profile pictures, review attachments) are stored using **Cloudinary**.

### Custom Optimized Backend (`ai_store/storage.py`):
```python
class OptimizedMediaCloudinaryStorage(MediaCloudinaryStorage):
    """
    Subclass of MediaCloudinaryStorage delivering automatic modern optimizations:
    - fetch_format='auto' (f_auto): Automatically delivers AVIF or WebP based on browser support.
    - quality='auto' (q_auto): Dynamic perceptual compression without visible quality degradation.
    """
```

* **Zero Template Changes**: Works seamlessly with standard Django image fields (`{{ product.image.url }}`).
* **Local Development Fallback**: If Cloudinary credentials are not supplied, media can be saved locally to `/media/` and served through Django in `DEBUG=True` mode.

---

## 🔐 Environment Variables Reference

| Variable Name | Required | Default Value | Description |
| :--- | :---: | :--- | :--- |
| `SECRET_KEY` | **Yes** | `django-insecure-...` | Cryptographic secret for session and token signing |
| `DEBUG` | No | `False` | Toggle Django debugging mode (`True` / `False`) |
| `ALLOWED_HOSTS` | No | `*` | Comma-separated list of allowed hostnames/IPs |
| `CSRF_TRUSTED_ORIGINS`| No | `http://localhost:8000`| Origins allowed for state-modifying requests |
| `SITE_URL` | No | `http://127.0.0.1:8000`| Public base URL for email links and webhooks |
| **Database** | | | |
| `DB_ENGINE` | No | `sqlite` | Database engine: `postgresql` or `sqlite` |
| `DB_NAME` | No | `ai_store_db` | PostgreSQL database name |
| `DB_USER` | No | `ai_store_user` | PostgreSQL database username |
| `DB_PASSWORD` | No | `ai_store_password` | PostgreSQL database password |
| `DB_HOST` | No | `localhost` / `db` | Database hostname (`db` in Docker, `localhost` locally) |
| `DB_PORT` | No | `5432` | Database port |
| `DATABASE_URL` | No | *(Empty)* | Standard database URL string (used on Railway/Heroku) |
| **Redis & Celery** | | | |
| `REDIS_URL` | No | *(Empty)* | Redis connection URL (e.g. `redis://127.0.0.1:6379`) |
| `CELERY_BROKER_URL` | No | `${REDIS_URL}` | Message broker URL for Celery task queuing |
| `CELERY_RESULT_BACKEND`| No| `${REDIS_URL}` | Storage backend for Celery task return values |
| **Email (SMTP)** | | | |
| `EMAIL_BACKEND` | No | `smtp.EmailBackend` | Django email backend class |
| `EMAIL_HOST` | No | `smtp.gmail.com` | SMTP server hostname |
| `EMAIL_PORT` | No | `587` | SMTP port (587 for TLS, 465 for SSL) |
| `EMAIL_USE_TLS` | No | `True` | Enable TLS encryption |
| `EMAIL_USE_SSL` | No | `False` | Enable SSL encryption |
| `EMAIL_HOST_USER` | No | *(Empty)* | Sender email address |
| `EMAIL_HOST_PASSWORD`| No | *(Empty)* | Gmail 16-character App Password (no spaces) |
| `DEFAULT_FROM_EMAIL`| No | `${EMAIL_HOST_USER}` | Display address in outbound emails |
| **Cloudinary** | | | |
| `CLOUDINARY_CLOUD_NAME`| No| *(Empty)* | Cloudinary account cloud name |
| `CLOUDINARY_API_KEY` | No | *(Empty)* | Cloudinary 15-digit API key |
| `CLOUDINARY_API_SECRET`| No| *(Empty)* | Cloudinary API secret |
| **Razorpay Gateway** | | | |
| `RAZORPAY_KEY_ID` | No | *(Empty)* | Razorpay API Key ID (`rzp_test_...`) |
| `RAZORPAY_KEY_SECRET` | No | *(Empty)* | Razorpay Secret Key |
| `RAZORPAY_WEBHOOK_SECRET`|No| *(Empty)* | Webhook secret for validating webhook signatures |
| **AI Assistant** | | | |
| `AI_PROVIDER` | No | *(Empty)* | Default AI provider: `groq`, `openai`, or `nvidia` |
| `GROQ_API_KEY` | No | *(Empty)* | Groq Cloud API Key (`gsk_...`) |
| `GROQ_MODEL_NAME` | No | `llama-3.3-70b-versatile` | Groq model identifier |
| `OPENAI_API_KEY` | No | *(Empty)* | OpenAI API Key (`sk-...`) |
| `OPENAI_MODEL_NAME` | No | `gpt-4o-mini` | OpenAI chat model identifier |
| `NVIDIA_API_KEY` | No | *(Empty)* | NVIDIA NIM API Key (`nvapi-...`) |
| `NVIDIA_MODEL_NAME` | No | `meta/llama-3.3-70b-instruct` | NVIDIA NIM model name |
| `NVIDIA_BASE_URL` | No | `https://integrate.api.nvidia.com/v1` | NVIDIA NIM API base URL |

---

## 🐳 Docker Setup & Deployment Guide

The project includes a production-ready `Dockerfile` and `docker-compose.yml` orchestrating 4 services:

```
┌────────────────────────────────────────────────────────┐
│                   Docker Compose Stack                 │
├────────────────────┬───────────┬──────────────┬────────┤
│ Container Name     │ Service   │ Image / Base │ Port   │
├────────────────────┼───────────┼──────────────┼────────┤
│ ai_store_postgres  │ db        │ postgres:16  │ 5432   │
│ ai_store_redis     │ redis     │ redis:7      │ 6379   │
│ ai_store_web       │ web       │ python:3.12  │ 8000   │
│ ai_store_celery    │ celery    │ python:3.12  │ -      │
└────────────────────┴───────────┴──────────────┴────────┘
```

### Persistent Volumes:
* `postgres_data`: Preserves all PostgreSQL tables, indexes, and records across container restarts and builds.
* `redis_data`: Preserves Redis caches and Celery state.

---

## 🚀 Installation & Local Setup Guide

### Method A: Full Docker Workflow (Recommended)

1. **Clone and enter the directory**:
   ```bash
   git clone <repository_url>
   cd ai_store
   ```

2. **Configure Environment Variables**:
   Copy `.env.example` to `.env` and configure your credentials:
   ```bash
   cp .env.example .env
   ```

3. **Start All Containers**:
   ```bash
   docker compose up -d
   ```

4. **Run Database Migrations & Load Initial Fixture**:
   ```bash
   # Apply migrations
   docker compose exec web python manage.py migrate

   # Load pre-configured sample products, categories, and colors
   docker compose exec web python manage.py loaddata datadump_postgres.json
   ```

5. **Create Superuser (Admin)**:
   ```bash
   docker compose exec web python manage.py createsuperuser
   ```

6. **Access the Application**:
   * Storefront: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
   * Custom Admin Panel: [http://127.0.0.1:8000/adminpanel/dashboard/](http://127.0.0.1:8000/adminpanel/dashboard/)
   * Django Admin: [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/)

---

### Method B: Hybrid Local Development Mode (PowerShell on Windows)

In hybrid mode, you run PostgreSQL & Redis inside Docker while running Django and Celery locally in your virtual environment:

1. **Spin up only Postgres and Redis**:
   ```powershell
   docker compose up -d db redis
   ```

2. **Configure `.env` for localhost**:
   ```env
   DB_ENGINE=postgresql
   DB_HOST=localhost
   DB_PORT=5432
   REDIS_URL=redis://127.0.0.1:6379
   ```

3. **Activate Virtual Environment & Install Dependencies**:
   ```powershell
   python -m venv myvenv
   .\myvenv\Scripts\activate
   pip install -r requirements.txt
   ```

4. **Apply Migrations**:
   ```powershell
   python manage.py migrate
   ```

5. **Terminal 1: Start Celery Worker (Windows requires `--pool=solo`)**:
   ```powershell
   celery -A ai_store worker --loglevel=info --pool=solo
   ```

6. **Terminal 2: Start Django ASGI Server**:
   ```powershell
   python manage.py runserver
   ```

---

## 🧪 Testing & Quality Assurance

The codebase includes comprehensive automated test suites covering models, views, API permissions, WebSockets, coupon validation rules, and AI tools:

```bash
# Run the entire test suite across all apps:
python manage.py test

# Run specific app test suites:
python manage.py test apps.coupons.tests       # 20+ tests: coupon boundaries, quotas, weekly limits
python manage.py test apps.chat.tests          # WebSocket authentication, permissions, messages
python manage.py test apps.admin_pannel.tests  # RBAC, staff permissions, dashboard access
python manage.py test apps.products.tests      # Catalog filtering, search, pricing calculations
python manage.py test apps.accounts.tests      # User creation, OTP validation, address management
python manage.py test ai                 # Dynamic LangGraph agent, 18 tools, ContextVar security, sequential execution
```

To run tests inside Docker:
```bash
docker compose exec web python manage.py test
```

---

## 🛠️ Troubleshooting & FAQ

### 1. Celery Worker Freezes or Throws `PermissionError` on Windows
* **Cause**: Celery defaults to `prefork` process pooling, which is unsupported on Windows.
* **Fix**: Always specify `--pool=solo` when running Celery on Windows:
  ```powershell
  celery -A ai_store worker -l info --pool=solo
  ```
  *(Inside Docker Linux containers, this flag is not needed).*

### 2. WebSocket Connection Fails with Code 4001 or 4003
* **Code `4001`**: The user is unauthenticated. Ensure the user is logged in before attempting to connect to `ws://.../ws/chat/<slug>/`.
* **Code `4003`**: The user does not own this conversation and lacks the `chat.view_conversation` permission. Only superusers or authorized staff may inspect customer rooms.

### 3. Razorpay Signature Verification Failed
* Ensure `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` match your active Razorpay Dashboard mode (Test vs. Live).
* Verify that the amount passed to Razorpay order creation is in **paise** ($100 \times \text{INR}$).

### 4. OTP Emails Are Not Being Delivered
* Verify `EMAIL_HOST_USER` and `EMAIL_HOST_PASSWORD` in `.env`.
* If using Gmail, you **must** use a 16-character **Google App Password** generated under 2-Step Verification, not your regular Gmail account password. Remove any whitespace.
* Check Celery worker logs to inspect the task execution status:
  ```bash
  docker compose logs -f celery
  ```

### 5. AI Assistant Returns `No AI model provider configured`
* You must configure at least one valid LLM provider in `.env` (e.g. `GROQ_API_KEY=gsk_...` or `OPENAI_API_KEY=sk-...`).
* Ensure `AI_PROVIDER` is set to `groq`, `openai`, or `nvidia`.

### 6. Database Connection Refused
* When running via Docker Compose, `DB_HOST` in `.env` must be set to `db` (the service name).
* When running Django locally on Windows, `DB_HOST` must be set to `localhost`.

---

## 📄 License & Maintainers

* **Project**: AI Store (ShopNexa E-Commerce)
* **Author**: Sumit Kumar
* **Framework**: Django 6.0 | Daphne | Channels | Celery | LangChain | PostgreSQL | Redis
