# AI Store - Architecture & System Guide

Welcome to the **AI Store** documentation. This guide explains how **Celery**, **Redis**, the **Email OTP Authentication System**, and the **Coupon Engine (Weekly Limits & Background Broadcasts)** work together.

---

## Table of Contents
1. [Core Architecture: Django, PostgreSQL, Redis & Celery](#1-core-architecture-django-postgresql-redis--celery)
2. [How Background Tasks Work (.delay())](#2-how-background-tasks-work-delay)
3. [Email OTP Authentication System](#3-email-otp-authentication-system)
4. [Coupon Engine & Weekly Usage Limits](#4-coupon-engine--weekly-usage-limits)
5. [Promotional Coupon Broadcast System](#5-promotional-coupon-broadcast-system)
6. [Active Coupon Codes in the Store](#6-active-coupon-codes-in-the-store)
7. [Timezone Handling](#7-timezone-handling)
8. [Docker & PostgreSQL Setup (Persistent Storage)](#8-docker--postgresql-setup-persistent-storage)
9. [Step-by-Step Guide to Run the Project](#9-step-by-step-guide-to-run-the-project)
10. [How to Test Everything](#10-how-to-test-everything)
11. [Troubleshooting & FAQs](#11-troubleshooting--faqs)

---

## 1. Core Architecture: Django, PostgreSQL, Redis & Celery

In a traditional web application, when a customer signs up or places an order, if the web server sends emails synchronously, the user's browser hangs for 3 to 10 seconds waiting for Gmail or an external SMTP server to reply. If the connection fails, the user sees an error screen.

To solve this, **AI Store** uses an asynchronous background processing architecture powered by Docker, PostgreSQL, and Redis:

```text
┌──────────────────────────────────────────────────────────────┐
│                    Django Web Application                    │
│   Handles user requests, WebSocket chat, renders frontend    │
└──────────────┬───────────────────────────────┬───────────────┘
               │                               │
               │ Reads / Writes                │ 1. Dispatches background task
               ▼                               ▼    via task.delay(args)
┌──────────────────────────────┐ ┌──────────────────────────────┐
│    PostgreSQL 16 Database    │ │    Redis 7 (Message Broker)  │
│ (Persistent Docker Volume)   │ │  In-memory task queue & cache│
└──────────────────────────────┘ └─────────────┬────────────────┘
                                               │
                                               │ 2. Worker listens on queue
                                               ▼
                                 ┌──────────────────────────────┐
                                 │   Celery Background Worker   │
                                 │ Executes tasks asynchronously│
                                 └─────────────┬────────────────┘
                                               │
                                               │ 3. Delivers emails via SMTP
                                               ▼
                                 ┌──────────────────────────────┐
                                 │       Customer Mailbox       │
                                 └──────────────────────────────┘
```

### What Each Component Does:
1. **Django:** Handles HTTP requests from browsers (login, products, cart, checkout). It delegates slow tasks (sending emails) to Celery so user pages load in milliseconds.
2. **Redis:** A fast in-memory key-value store acting as the **Message Broker**. Django puts task instructions (e.g. *"send OTP 123456 to user@example.com"*) into Redis.
3. **Celery Worker:** A separate Python process that continuously reads tasks from Redis, executes them in the background, connects to Gmail SMTP, and logs results.

---

## 2. How Background Tasks Work (`.delay()`)

When you call a Celery task with `.delay()`:

```python
# In your Django view:
send_otp_email_task.delay(user.email, user_display, otp_code, purpose)
```

1. Django **does not** send the email right now.
2. Django serializes the parameters (`user.email`, `otp_code`, etc.) into a JSON message and pushes it into the `celery` queue in Redis.
3. The function returns **immediately** to the user. The user sees the next page instantly.
4. The **Celery worker** (running in another terminal) picks up the message, runs `send_otp_email_task`, connects to SMTP, and sends the email.

---

## 3. Email OTP Authentication System

The OTP system protects customer accounts during **Registration**, **Login (unverified users)**, and **Password Reset**.

### Life Cycle of an OTP:
```text
User Submits Form (Register / Forgot Password)
                    ↓
   Generate random 6-digit code (e.g. 849201)
                    ↓
   Store directly on CustomUser:
   - user.temp_otp = '849201'
   - user.otp_created_at = timezone.now()
                    ↓
  Call send_otp_email_task.delay(...)
                    ↓
  Customer enters code on /verify-otp/
                    ↓
       ┌────────────────────────┐
       │   Validation Checks    │
       ├────────────────────────┤
        │ 1. Matches temp_otp?   │ ── No  ──> "Invalid OTP code"
        │ 2. Past 10 minutes?    │ ── Yes ──> "This OTP has expired"
        └───────────┬────────────┘
                    │ Pass
                    ▼
   1. Clear OTP: user.temp_otp = None, user.otp_created_at = None
   2. Activate & Verify:
      - user.is_email_verified = True
      - user.is_activated = True
      - user.is_active = True
   3. Create Profile: Profile.objects.get_or_create(...)
   4. Auto-login customer & redirect to Home
```

### Key Security Features:
* **Strict 10-minute lifetime:** Checked against `user.otp_created_at`.
* **Single-use guarantee:** `temp_otp` is cleared (`None`) immediately upon successful verification.
* **Direct on User Model:** No overhead or complexity from separate OTP models.
* **Safe Logging:** OTP codes and passwords are **never** logged to server logs.
* **Automatic Cleanup:** `cleanup_expired_otps_task` clears expired `temp_otp` values older than 10 minutes.

---

## 4. Coupon Engine & Weekly Usage Limits

Coupons allow customers to receive percentage or flat discounts on eligible orders.

### The Critical Rule: Session vs. Database Usage
> **Applying a coupon does NOT create a usage record!**

```text
Customer enters Coupon Code at Cart/Checkout
                    ↓
Backend validates coupon against Database:
  ├─ Is active?
  ├─ Within valid_from and valid_until dates?
  ├─ Cart subtotal >= minimum_order_amount?
  └─ Weekly usages in current calendar week < weekly_user_limit (5)?
                    ↓
Code saved in request.session['applied_coupon_code']
  (NO database CouponUsage created yet!)
                    ↓
Customer completes checkout & places order
                    ↓
Order created & confirmed in database
                    ↓
record_coupon_usage() runs in an atomic transaction:
  ├─ Creates CouponUsage attached to Order
  ├─ Increments coupon.used_count
  └─ Clears session['applied_coupon_code']
```

This prevents users from exhausting their limits by repeatedly applying or removing coupons in their cart.

### How the Weekly Limit Works (5 per week):
* The week starts on **Monday at 00:00:00** and ends on **Sunday at 23:59:59**.
* Calculated using timezone-aware bounds:
  ```python
  # In apps/coupons/services.py:
  start_of_week, end_of_week = get_current_week_bounds()
  usage_count = CouponUsage.objects.filter(
      user=user,
      used_at__gte=start_of_week,
      used_at__lte=end_of_week
  ).count()
  ```
* **Order 1 to 5:** Allowed.
* **Order 6:** Blocked with the message:
  *"Weekly coupon limit reached. You can use coupons up to 5 times per week."*

---

## 5. Promotional Coupon Broadcast System

Store admins can broadcast new coupons to all active registered customers with a single click.

### Broadcast Architecture:
```text
Admin clicks "Broadcast to Customers" on Coupon Detail page
                          ↓
Django Admin View calls: broadcast_coupon_announcement_task.delay(coupon.id)
                          ↓
Admin view immediately responds with:
"Coupon '<CODE>' broadcast has been queued. Emails are being processed in the background."
                          ↓
Celery Worker receives task:
  1. Retrieves coupon details from database
  2. Queries active users with valid email addresses
  3. Builds responsive HTML email using dynamic settings.SITE_URL
  4. Delivers emails individually with per-recipient try/except
  5. Uses msg.send(fail_silently=False) so errors are accurately caught
  6. Tracks sent_count and failed_count
  7. Logs summary: "Coupon '<CODE>' broadcast finished. Successful: X, Failed: Y."
```

---

## 6. Active Coupon Codes in the Store

All 10 coupons are pre-configured in your database and valid for 1 year:

| Code | Type | Discount Value | Minimum Cart Value | Maximum Discount Cap | Weekly Limit |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`WELCOME10`** | Percentage | **10% OFF** | ₹500 | ₹200 | 5 |
| **`SAVE20`** | Percentage | **20% OFF** | ₹1,000 | ₹500 | 5 |
| **`FLAT100`** | Fixed | **₹100 FLAT OFF** | ₹799 | No cap | 5 |
| **`FLAT250`** | Fixed | **₹250 FLAT OFF** | ₹1,499 | No cap | 5 |
| **`FESTIVE30`** | Percentage | **30% OFF** | ₹2,500 | ₹1,000 | 5 |
| **`MEGA500`** | Fixed | **₹500 FLAT OFF** | ₹2,999 | No cap | 5 |
| **`SUPER50`** | Percentage | **50% OFF** | ₹3,999 | ₹1,500 | 5 |
| **`TECH15`** | Percentage | **15% OFF** | ₹1,200 | ₹600 | 5 |
| **`STYLE25`** | Percentage | **25% OFF** | ₹1,800 | ₹750 | 5 |
| **`WEEKEND20`** | Percentage | **20% OFF** | ₹999 | ₹400 | 5 |

---

## 7. Timezone Handling

AI Store uses **`UserTimezoneMiddleware`** (`ai_store/middleware.py`) to activate the correct regional timezone:

### Hierarchy:
1. **User Profile Preference:** User's preferred timezone stored in database (if logged in).
2. **Browser Cookie:** `user_timezone` or `django_timezone` cookie set by client browser JavaScript (e.g. `Asia/Kolkata`, `America/New_York`).
3. **Server Default:** `settings.TIME_ZONE` (`Asia/Kolkata`).

### Safety Rules Implemented:
* **Resilient Cookie Parsing:** If an invalid timezone cookie is received (e.g., malformed text), the middleware safely catches the error and falls back to `Asia/Kolkata` without crashing the request.
* **Timezone Aware:** Always uses `timezone.now()` instead of `datetime.now()`.
* **Celery Workers:** Middleware does not run inside background Celery tasks; tasks explicitly access `timezone.now()`.

---

## 8. Docker & PostgreSQL Setup (Persistent Storage)

AI Store runs on a synchronized multi-container Docker architecture orchestrated by `docker-compose.yml`:

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        Docker Compose Stack                            │
├──────────────────┬─────────────────┬──────────────────┬────────────────┤
│   PostgreSQL 16  │     Redis 7     │ Django Web App   │ Celery Worker  │
│   (Database)     │ (Broker/Cache)  │ (Daphne/ASGI)    │ (Async Tasks)  │
│   Port: 5432     │ Port: 6379      │ Port: 8000       │                │
├──────────────────┴─────────────────┴──────────────────┴────────────────┤
│                      Persistent Named Volumes                          │
│     postgres_data (Database Files)  │  redis_data (Task State)         │
└────────────────────────────────────────────────────────────────────────┘
```

### Why Database Data is 100% Persistent:
PostgreSQL stores all database tables, users, products, and records inside `/var/lib/postgresql/data`.
We bind this directory to a Docker named volume:
```yaml
services:
  db:
    image: postgres:16-alpine
    volumes:
      - postgres_data:/var/lib/postgresql/data
...
volumes:
  postgres_data:
    driver: local
```
**Your data is completely safe.** Stopping, restarting, or rebuilding containers (`docker compose down` / `docker compose up`) will **never erase** your PostgreSQL database.

---

### Key Services:
1. **`db` (PostgreSQL 16)**: Database service with automatic healthcheck using `pg_isready`. Exposes port `5432:5432`.
2. **`redis` (Redis 7)**: Fast in-memory message queue for Celery & Django Channels. Exposes port `6379:6379`.
3. **`web` (Django + Daphne)**: Runs `python manage.py runserver 0.0.0.0:8000`, handles HTTP and WebSockets, serves static files, and mounts `.:/app` for live code auto-reloading. Exposes port `8000:8000`.
4. **`celery`**: Dedicated worker process running asynchronously in the background to deliver OTP emails and broadcasts.

---

## 9. Step-by-Step Guide to Run the Project

### Option A: Running with Docker (Recommended)

Make sure **Docker Desktop** is open and running on your computer.

#### 1. Start the Containers (Background Mode)
```powershell
docker compose up -d
```
*(If you make changes to `requirements.txt` or `Dockerfile`, rebuild using `docker compose up -d --build`)*

#### 2. Check Container Health
```powershell
docker compose ps
```
You will see `ai_store_postgres`, `ai_store_redis`, `ai_store_web`, and `ai_store_celery` all running.

#### 3. Run Database Migrations (Creates Tables in PostgreSQL)
```powershell
docker compose exec web python manage.py migrate
```

#### 4. Create an Admin Superuser
```powershell
docker compose exec web python manage.py createsuperuser
```

#### 5. Open in Your Browser
- **Store Homepage:** [http://127.0.0.1:8000](http://127.0.0.1:8000)
- **Django Admin:** [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/)

#### 6. Useful Docker Commands
- **View live server logs:**
  ```powershell
  docker compose logs -f web
  ```
- **View live Celery logs:**
  ```powershell
  docker compose logs -f celery
  ```
- **Stop all containers:**
  ```powershell
  docker compose down
  ```
- **Open PostgreSQL command line (psql):**
  ```powershell
  docker compose exec db psql -U ai_store_user -d ai_store_db
  ```

---

### Option B: Running Locally in PowerShell (Hybrid Mode)

If you prefer to run `python manage.py runserver` in your local PowerShell terminal while keeping PostgreSQL and Redis inside Docker:

1. **Start only Postgres and Redis in Docker:**
   ```powershell
   docker compose up -d db redis
   ```
2. **In `.env`, set hosts to localhost:**
   ```env
   DB_HOST=localhost
   REDIS_HOST=127.0.0.1
   ```
3. **Run Celery worker in Terminal 1:**
   ```powershell
   celery -A ai_store worker --loglevel=info --pool=solo
   ```
4. **Run Django in Terminal 2:**
   ```powershell
   python manage.py runserver
   ```

---

## 10. How to Test Everything

### A. Testing OTP Registration:
1. Go to `http://127.0.0.1:8000/register/`.
2. Fill in username, email, and password. Submit.
3. Observe that Django redirects immediately to `/verify-otp/`.
4. Look at Celery logs (`docker compose logs -f celery`):
   ```text
   Task started: Sending OTP email to user@example.com
   Task completed: OTP email sent successfully to user@example.com
   ```
5. Check your email inbox for the 6-digit code.
6. Enter the OTP to activate your account.

### B. Testing Coupon Broadcast:
1. Log in to the Admin Panel at `http://127.0.0.1:8000/adminpanel/coupons/`.
2. Click any coupon (e.g., `SAVE20`).
3. Click the **📢 Broadcast to Customers** button.
4. You will see:
   ```text
   Coupon 'SAVE20' broadcast has been queued. Emails are being processed in the background.
   ```
5. Check Celery logs: observe the broadcast task sending emails to all active registered users.

### C. Testing the 5-Per-Week Coupon Limit:
1. Log in as a customer.
2. Add items to cart and apply a coupon (e.g. `WELCOME10`).
3. Place order 1. `CouponUsage` is now recorded.
4. Repeat for orders 2, 3, 4, and 5.
5. On order 6, the system will block the coupon:
   *"Weekly coupon limit reached. You can use coupons up to 5 times per week."*

### D. Running Automated Tests:
To verify the entire test suite inside Docker:
```powershell
docker compose exec web python manage.py test apps.accounts apps.coupons
```

---

## 11. Troubleshooting & FAQs

### Q: Why didn't I receive the OTP email?
1. **Is the Celery Worker running?** Check `docker compose logs -f celery`. Tasks sit in Redis queue until a worker processes them.
2. **Is the Gmail App Password valid?** Check `EMAIL_HOST_PASSWORD` in `.env`. Ensure it is an active 16-character Google App Password (not your normal Gmail login password).

### Q: How do I verify PostgreSQL data persistence?
1. Create a user or product at `http://127.0.0.1:8000/`.
2. Stop all containers with `docker compose down`.
3. Start them back up with `docker compose up -d`.
4. Refresh the page: all your created users, products, and tables are preserved!

### Q: How do I clear stuck tasks in Redis?
Run:
```powershell
docker compose exec redis redis-cli flushdb
```
