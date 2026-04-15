# routing.py

from django.urls import path
from .consumers import GatewayStatusConsumer

print("Our routing script")
websocket_urlpatterns = [
    path('ws/gateway-status/', GatewayStatusConsumer.as_asgi()),
]
