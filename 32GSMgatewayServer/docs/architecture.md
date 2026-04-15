# 32GSMgatewayServer — Architectural Documentation

## Abstract

32GSMgatewayServer is a remote monitoring and management system for a multi-SIM VoIP GSM gateway deployed on a Raspberry Pi. It exposes a REST API for centralized control of SIM cards, SMS, voice calls, and USSD operations across multiple cellular ports, enabling a remote VPS server to query and manage the gateway.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      Remote VPS (sabkiapp.com)                  │
│                 (Central API server / tunnel endpoint)          │
└──────────────┬──────────────────────────────────┬───────────────┘
               │  Cloudflare Tunnel              │
               │  (cloudflared)                  │
┌──────────────▼──────────────────────────────────▼───────────────┐
│                    Raspberry Pi (RPi)                          │
│                                                                │
│  ┌──────────────────┐  ┌─────────────────┐  ┌───────────────┐  │
│  │  Django API      │  │  AMI Listener   │  │  Watchdog     │  │
│  │  (port 9000)     │  │  (Daemon)       │  │  check_server │  │
│  └────────┬─────────┘  └────────┬────────┘  └───────┬───────┘  │
│           │                     │                    │          │
│           ▼                     ▼                    │          │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │               Business Logic (src/)                      │   │
│  │  32GSMgatewayServer · PortData · VoipGatewayClient · SMS ·    │   │
│  │  USSD · VoiceGenerator · CallMaker · DialplanCreator     │   │
│  └──────────────────────────────────────────────────────────┘   │
│           │                     │                              │
│           ▼                     ▼                              │
│  ┌──────────────────┐  ┌──────────────────┐                   │
│  │  GSM VoIP        │  │  Asterisk PBX    │                   │
│  │  Gateway         │  │  (AMI port 5038) │                   │
│  │  192.168.8.50    │  │                  │                   │
│  └──────────────────┘  └──────────────────┘                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## System Topology

| Component | Location | Role |
|---|---|---|
| GSM VoIP Gateway | `192.168.8.50` (LAN) | Hardware with N SIM ports; exposes HTTP API for SIM management, SMS, USSD, calls |
| Asterisk PBX | RPi localhost | VoIP PBX managing SIP channels; connects to GSM gateway |
| Django API | RPi `0.0.0.0:9000` | REST facade over business logic |
| AMI Listener | RPi (daemon) | Listens to Asterisk events; reports call status to remote VPS |
| Watchdog | RPi (daemon) | Monitors tunnel and service health; restarts crashed processes |
| Remote VPS | `asterisk.sabkiapp.com` | Central server; receives status updates, call/SMS events |
| Connectivity | Cloudflare Tunnel (cloudflared) | Exposes RPi services via cloudflared tunnel |

---

## Technology Stack

| Layer | Technology |
|---|---|
| Web Framework | Django 5.0.1 + Django REST Framework 3.14.0 |
| Language | Python 3.12 |
| Protocols | Asterisk AMI, HTTP, Cloudflare Tunnel |
| VoIP | Asterisk PBX, SIP |
| Persistence | Pickle files (`*.pkl`) — no database |
| TTS | gTTS (female), Remote API (male) |
| Audio | pydub (MP3→WAV conversion, resampling) |
| Serial | pyst2 (GSM port communication) |
| System | psutil (disk), subprocess, Bash scripts |
| Deployment | Custom shell scripts; no Docker or package manager |

---

## Data Flow

### Port Status Query
```
Remote VPS  →  GET /gateway_status  →  Django views.py
                                       ├─ VoipGatewayClient.get_gsminfo()  →  GSM Gateway
                                       ├─ VirtualStorage.fetch_data()       →  Remote API / pickle
                                       ├─ 32GSMgatewayServer.compute_status()
                                       └─ USSD background thread (new/rechargeless SIMs)
                                       →  JSON response
```

### SMS Send
```
Remote VPS  →  POST /send_sms  →  SmsSender  →  GSM Gateway HTTP API
                                     └─ update_database() → Remote API + pickle
```

### Voice Call
```
Remote VPS  →  POST /make_call  →  TTS generation (gTTS/API)
                                   →  DialplanCreator (Asterisk config)
                                   →  CallMaker.originate()  →  Asterisk AMI
                                   →  Asterisk dials SIP → GSM gateway → PSTN
                                   →  dtmf.sh / AMI Listener → Remote API
```

### USSD
```
Background thread  →  SendUssd  →  GSM Gateway USSD endpoint
                        ↓
                    GSM Gateway calls back  →  /receive_sms  →  DecodeMessage
                        ↓
                    update_database()  →  Remote API + pickle
```

---

## API Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/gateway_status` | GET | Full port status, SIM states, SMS balances |
| `/send_sms` | POST | Send SMS via a GSM port |
| `/receive_sms` | GET | Gateway callback for incoming SMS/USSD |
| `/gsm-info` | GET | Raw GSM port data from VoIP gateway |
| `/make_call` | POST | Initiate voice call with TTS |
| `/save_dial_plan` | POST | Create Asterisk dialplan for a campaign |
| `/upload_audio` | POST | Download campaign audio files |
| `/disk_space` | GET | ext4 disk usage |
| `/tunnel_status` | GET | Health check (always returns True) |
| `/start_ssh_tunnel` | GET | Establish reverse SSH tunnel |
| `/start_eroll_tunnels` | GET | Establish multiple tunnels |
| `/change_host_password` | POST | Update credentials in settings.py |
| `/reboot` | POST | Reboot the Raspberry Pi |
| `/update_code` | POST | Pull code from zip URL, reboot |
| `/zip_entire_code` | GET | Package code as password-protected zip |
| `/Documents/32GSMgatewayServer.zip` | GET | Download packaged zip |

---

## Key Components

### `src/gateway_status.py` — Status Aggregator
Central orchestrator. Fetches live GSM port data, merges with cached/virtual data, computes final SIM status, and spawns USSD requests for new or rechargeless SIMs.

### `src/voip_client.py` — GSM Gateway Client
Singleton HTTP session manager with cookie-based auth. Provides `get_gsminfo()` for per-port data (IMSI, signal, operator, state, phone number, SMS balance).

### `src/virtual_data.py` — Remote Data Cache
Wraps `virtual_ram_data.pkl`. Falls back to remote API (`/sim_information`) when cache is empty.

### `src/send_ussd.py` + `ussd_cache.py` — USSD Flow
Sends USSD requests via GSM gateway. `UssdCache` tracks per-port state with 30-second deduplication to prevent duplicate requests.

### `src/sms_sender.py` — SMS Dispatcher
Validates Indian phone numbers (10-digit, prefix 6–9), checks SMS balance, segments messages using GSM 7-bit encoding, sends via gateway HTTP API.

### `src/call_maker.py` + `ami_listener.py` — Call Origination
`CallMaker` sends AMI `originate` commands to Asterisk. `AMIListener` daemon listens for `DialBegin`, `Hangup`, `DialEnd` events and reports call status to remote VPS.

### `src/voice_generator.py` + `audio_manager.py` — TTS
Generates voice prompts: male via remote API, female via gTTS. `AudioManager` downloads and caches campaign audio files.

### `src/dialplan_creator.py` — Dynamic Dialplan
Creates Asterisk extension entries for campaigns, appended to `asterisk_dialplan.conf` and included from `extensions.conf`.

### `src/final_status.py` — SIM State Machine
`FinalStatus` enum: `NO_SIM` → `NO_SIGNAL` → `NEW_SIM` → `RECHARGELESS` → `READY` → `BUSY`.

### `check_server.py` — Watchdog
Polling health checks on Django endpoint. Restarts Django and `ami_listener.py` on failure. Monitors process liveness.

---

## Persistence Model

No relational database. All state is stored in pickle files:

| File | Content |
|---|---|
| `virtual_ram_data.pkl` | Cached remote SIM data (phone numbers, validity) |
| `ussd_cache.pkl` | Per-port USSD request state machine |
| `voip_gateway_cookies.pkl` | GSM gateway session cookies |
| `password.pkl` | Zip download password |

---

## Security Posture

- **No database** — no Django ORM, no sessions, no user model
- **Auth** — shared `host` + `system_password` query parameters on every request
- **Hardcoded credentials** — plaintext in `settings.py` (gateway, SMS, USSD, sudo)
- **DEBUG=True, ALLOWED_HOSTS=['*']** — exposed to all origins
- **No HTTPS enforcement** on the GSM gateway or Asterisk AMI local connections
- **Remote code execution** — `update_code` endpoint pulls and executes arbitrary zip content

---

## Deployment Model

- **Target path**: `/home/pi/Documents/32GSMgatewayServer` (hardcoded throughout)
- **Startup**: `run_server.sh` — starts Django, AMI listener, watchdog (cloudflared runs as a separate systemd service)
- **Remote deploy**: `update_code` view downloads zip → extracts → copies → reboots
- **Code distribution**: `zip_entire_code` creates password-protected zip for download
- **No CI/CD, no Docker, no systemd** — raw shell scripts and manual operation
