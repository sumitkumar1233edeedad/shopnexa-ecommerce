"""
ASGI config for ai_store project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

import os
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ai_store.settings')

# Initialize Django ASGI application early to ensure the AppRegistry
# is populated before importing code that may import ORM models.
django_asgi_app = get_asgi_application()

from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import apps.chat.routing

application = ProtocolTypeRouter({
    "http": ASGIStaticFilesHandler(django_asgi_app),
    "websocket": AuthMiddlewareStack(
        URLRouter(
            apps.chat.routing.websocket_urlpatterns
        )
    ),
})

