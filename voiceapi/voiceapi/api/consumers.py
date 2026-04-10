from channels.generic.websocket import AsyncWebsocketConsumer
import json
import random
import asyncio
import logging
from websockets.exceptions import ConnectionClosedOK

logger = logging.getLogger(__name__)

class MachineStatusConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()
        self.keep_running = True  # Flag to control the loop
        while self.keep_running:
            try:
                # Send random data at random intervals
                await asyncio.sleep(random.randint(1, 5))  # Random delay
                data = {'status': random.choice(['Running', 'Stopped', 'Idle'])}
                await self.send(json.dumps(data))
            except ConnectionClosedOK:
                # Normal closure, not an error
                logger.info("WebSocket connection closed normally.")
                break
            except asyncio.CancelledError:
                # Handle cancellation of the loop
                logger.info("WebSocket sending loop cancelled.")
                break
            except Exception as e:
                # Handle other exceptions
                logger.error(f"Error in WebSocket: {e}")
                break

    async def disconnect(self, close_code):
        # Handle disconnection
        self.keep_running = False  # Ensure the loop is stopped on disconnect
        logger.info(f"Disconnected with close code {close_code}")

    async def receive(self, text_data=None, bytes_data=None):
        # Handle received message from WebSocket
        logger.info(f"Received message: {text_data}")

    async def close(self, code=None):
        # Optional: Override close method to handle closing the connection
        logger.info(f"Closing WebSocket with code {code}")
        await super().close(code)
