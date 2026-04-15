"""
RTP Handler — Parse and construct RTP packets for ExternalMedia.

ExternalMedia sends/receives standard RTP packets:
  - 12-byte header + payload
  - Format: slin16 (16-bit signed linear PCM, 16kHz, little-endian mono)
  - 20ms frames = 640 bytes payload (320 samples * 2 bytes)

This module provides:
  - RTPReceiver: async UDP socket, yields raw PCM chunks
  - RTPSender: constructs RTP packets from PCM, sends via UDP
"""

import asyncio
import struct
import time


# slin16 at 16kHz, 20ms frames
SAMPLE_RATE = 16000
FRAME_DURATION_MS = 20
SAMPLES_PER_FRAME = SAMPLE_RATE * FRAME_DURATION_MS // 1000  # 320
BYTES_PER_FRAME = SAMPLES_PER_FRAME * 2  # 640 (16-bit)
RTP_HEADER_SIZE = 12

# Payload type for L16/16000 (dynamic, typically 96+)
# ExternalMedia negotiates this — we mirror what Asterisk sends
DEFAULT_PAYLOAD_TYPE = 11  # L16 mono 16kHz is sometimes PT 11


class RTPPacket:
    """Parsed RTP packet."""
    __slots__ = ("version", "padding", "extension", "cc", "marker",
                 "payload_type", "seq", "timestamp", "ssrc", "payload")

    def __init__(self, data: bytes):
        if len(data) < RTP_HEADER_SIZE:
            raise ValueError(f"RTP packet too short: {len(data)} bytes")

        b0, b1, self.seq, self.timestamp, self.ssrc = struct.unpack("!BBHII", data[:12])
        self.version = (b0 >> 6) & 0x3
        self.padding = bool(b0 & 0x20)
        self.extension = bool(b0 & 0x10)
        self.cc = b0 & 0x0F
        self.marker = bool(b1 & 0x80)
        self.payload_type = b1 & 0x7F

        # Skip CSRC and extension headers
        offset = RTP_HEADER_SIZE + self.cc * 4
        if self.extension and len(data) > offset + 4:
            ext_len = struct.unpack("!HH", data[offset:offset + 4])[1]
            offset += 4 + ext_len * 4

        self.payload = data[offset:]


class RTPSender:
    """Constructs and sends RTP packets to Asterisk's ExternalMedia channel."""

    def __init__(self, transport: asyncio.DatagramTransport, remote_addr: tuple):
        self.transport = transport
        self.remote_addr = remote_addr
        self.seq = 0
        self.timestamp = 0
        self.ssrc = 0xDEADBEEF
        self.payload_type = DEFAULT_PAYLOAD_TYPE

    def send(self, pcm_data: bytes):
        """Send raw PCM as one or more RTP packets."""
        offset = 0
        while offset < len(pcm_data):
            chunk = pcm_data[offset:offset + BYTES_PER_FRAME]
            if len(chunk) == 0:
                break

            self.seq = (self.seq + 1) & 0xFFFF
            samples_in_chunk = len(chunk) // 2
            self.timestamp = (self.timestamp + samples_in_chunk) & 0xFFFFFFFF

            header = struct.pack("!BBHII",
                0x80,  # V=2
                self.payload_type,
                self.seq,
                self.timestamp,
                self.ssrc,
            )
            self.transport.sendto(header + chunk, self.remote_addr)
            offset += BYTES_PER_FRAME

    def update_payload_type(self, pt: int):
        """Mirror the payload type from received packets."""
        self.payload_type = pt


class RTPProtocol(asyncio.DatagramProtocol):
    """asyncio UDP protocol for receiving RTP from ExternalMedia."""

    def __init__(self):
        self.transport = None
        self.remote_addr = None
        self.audio_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=500)
        self.packets_received = 0
        self.packets_sent = 0
        self.sender: RTPSender | None = None
        self._first_packet_event = asyncio.Event()

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data: bytes, addr: tuple):
        # Learn remote address from first packet
        if self.remote_addr is None:
            self.remote_addr = addr
            self.sender = RTPSender(self.transport, addr)
            self._first_packet_event.set()

        self.packets_received += 1

        try:
            pkt = RTPPacket(data)
            # Mirror payload type
            if self.sender:
                self.sender.update_payload_type(pkt.payload_type)
            # Queue raw PCM for the pipeline
            try:
                self.audio_queue.put_nowait(pkt.payload)
            except asyncio.QueueFull:
                pass  # Drop oldest if pipeline is slow
        except ValueError:
            pass

    def send_audio(self, pcm_data: bytes):
        """Send PCM audio back to Asterisk."""
        if self.sender:
            self.sender.send(pcm_data)
            self.packets_sent += len(pcm_data) // BYTES_PER_FRAME or 1

    async def wait_for_first_packet(self, timeout=30):
        """Wait until first RTP packet arrives (means ExternalMedia is connected)."""
        try:
            await asyncio.wait_for(self._first_packet_event.wait(), timeout)
            return True
        except asyncio.TimeoutError:
            return False

    def error_received(self, exc):
        print(f"[RTP] Error: {exc}")
