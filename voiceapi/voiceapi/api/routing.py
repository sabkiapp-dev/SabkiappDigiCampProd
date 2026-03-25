# routing.py

from django.urls import path
from .consumers import MachineStatusConsumer

print("Our routing script")
websocket_urlpatterns = [
    path('ws/machine-status/', MachineStatusConsumer.as_asgi()),
]
