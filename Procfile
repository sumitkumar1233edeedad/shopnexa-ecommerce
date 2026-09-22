web: python manage.py migrate && python manage.py load_railway_data && python -m daphne -b 0.0.0.0 -p $PORT ai_store.asgi:application
worker: celery -A ai_store worker -l info
