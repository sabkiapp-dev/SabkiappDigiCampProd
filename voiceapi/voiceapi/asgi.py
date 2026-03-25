"""
ASGI config for voiceapi project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/asgi/
"""

import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.layers import get_channel_layer
import api.routing  

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'voiceapi.settings')
print("Our ASGI script")
application = ProtocolTypeRouter({
  "http": get_asgi_application(),  # HTTP requests
  "websocket": URLRouter(
        api.routing.websocket_urlpatterns  # WebSocket connections
    ),
})

