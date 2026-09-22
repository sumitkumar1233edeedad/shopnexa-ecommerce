# AI Store — Quick Run & Command Guide

This guide contains all copy-pasteable commands to run, inspect, and manage the **AI Store** application.

---

## 🌐 Quick Links (When Running)

- **Store Homepage:** [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- **Register Page:** [http://127.0.0.1:8000/register/](http://127.0.0.1:8000/register/)
- **Unified Login:** [http://127.0.0.1:8000/login/](http://127.0.0.1:8000/login/)
- **Admin Dashboard:** [http://127.0.0.1:8000/adminpanel/dashboard/](http://127.0.0.1:8000/adminpanel/dashboard/)
- **Django Built-in Admin:** [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/)

---

## 🚀 1. Primary Workflow: Running with Docker (Recommended)

Ensure **Docker Desktop** is running on your Windows machine.

### ▶️ Start All Services (Background Mode)
```powershell
docker compose up -d
```
Starts all 4 services:
1. `ai_store_postgres` (PostgreSQL 16 on port 5432)
2. `ai_store_redis` (Redis 7 on port 6379)
3. `ai_store_web` (Django/Daphne on port 8000)
4. `ai_store_celery` (Celery background worker)

### 📊 Check Running Status
```powershell
docker compose ps
```

### 📜 View Live Logs
```powershell
# Web server logs (HTTP requests, print statements, errors):
docker compose logs -f web

# Celery logs (OTP emails, coupon broadcasts):
docker compose logs -f celery

# All logs combined:
docker compose logs -f
```
*(Press `Ctrl + C` anytime to exit logs without stopping the containers)*

### ⏹️ Stop All Services
```powershell
docker compose down
```
> **Data Persistence:** Your PostgreSQL data is stored in the Docker volume `postgres_data` and is **never** lost when stopping or rebuilding containers.

### 🔄 Rebuild Containers (After changing requirements.txt or Dockerfile)
```powershell
docker compose up -d --build
```

---

## ⚙️ 2. Django Management Commands Inside Docker

Run any Django command using `docker compose exec web python manage.py <command>`:

### 👤 Create Admin Superuser
```powershell
docker compose exec web python manage.py createsuperuser
```

### 🗄️ Database Migrations
```powershell
# Check migration status:
docker compose exec web python manage.py showmigrations

# Create new migrations:
docker compose exec web python manage.py makemigrations

# Apply migrations to PostgreSQL:
docker compose exec web python manage.py migrate
```

### 🐍 Django Interactive Shell
```powershell
docker compose exec web python manage.py shell
```

### 🧪 Run Automated Tests
```powershell
docker compose exec web python manage.py test
```

---

## 🛠️ 3. PostgreSQL Database Commands

### Connect to PostgreSQL CLI (`psql`)
```powershell
docker compose exec db psql -U ai_store_user -d ai_store_db
```
Useful psql commands once connected:
- `\dt` — List all tables
- `\d table_name` — Describe table columns
- `SELECT count(*) FROM accounts_customuser;`
- `\q` — Quit psql

---

## 💻 4. Alternative: Hybrid Development Mode (Local PowerShell)

If you prefer to run `runserver` directly in your local PowerShell terminal while keeping PostgreSQL & Redis in Docker:

1. **Start only Postgres and Redis in Docker:**
   ```powershell
   docker compose up -d db redis
   ```
2. **In `.env`, point to localhost:**
   ```env
   DB_HOST=localhost
   REDIS_HOST=127.0.0.1
   ```
3. **In Terminal 1: Run Celery Worker:**
   ```powershell
   .\myvenv\Scripts\celery.exe -A ai_store worker --loglevel=info --pool=solo
   ```
4. **In Terminal 2: Run Django Server:**
   ```powershell
   .\myvenv\Scripts\python.exe manage.py runserver
   ```
