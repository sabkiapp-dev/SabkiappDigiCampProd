# Rename Migration Guide

All old project names have been replaced across `SabkiappDigiCampProd`. This document lists every breaking change so dependent services can be updated.

---

## Directory Renames

| Old | New |
|---|---|
| `voiceapi/` | `DigiCampServer/` |
| `voiceapi/voiceapi/` (project root) | `DigiCampServer/digicamp/` |
| `voiceapi/voiceapi/voiceapi/` (settings module) | `DigiCampServer/digicamp/digicamp_server/` |
| `MachineStatus/` | `32GSMgatewayServer/` |
| `MachineStatus/machine_status/` (project root) | `32GSMgatewayServer/gateway/` |
| `MachineStatus/machine_status/machine_status/` (settings module) | `32GSMgatewayServer/gateway/gsm_gateway/` |

---

## Django Settings Module

| Project | Old `DJANGO_SETTINGS_MODULE` | New |
|---|---|---|
| DigiCampServer | `voiceapi.settings` | `digicamp_server.settings` |
| 32GSMgatewayServer | `machine_status.settings` | `gsm_gateway.settings` |

---

## API Endpoint Changes (32GSMgatewayServer)

| Old Endpoint | New Endpoint | Method |
|---|---|---|
| `/machine_status` | `/gateway_status` | GET |
| `/Documents/MachineStatus.zip` | `/Documents/32GSMgatewayServer.zip` | GET |

All other endpoints (`/send_sms`, `/receive_sms`, `/make_call`, `/save_dial_plan`, `/reboot`, `/update_code`, `/gsm-info`, etc.) are unchanged.

---

## API Endpoint Changes (DigiCampServer)

| Old Endpoint | New Endpoint | Method |
|---|---|---|
| `get_all_machine_status` | `get_all_gateway_status` | GET |
| `ws/machine-status/` | `ws/gateway-status/` | WebSocket |

All other endpoints are unchanged.

---

## Python Class/Function Renames

### 32GSMgatewayServer

| Old | New | File |
|---|---|---|
| `class MachineStatus` | `class GatewayStatus` | `gateway/src/gateway_status.py` (was `machine_status.py`) |
| `def machine_status(request)` | `def gateway_status(request)` | `gateway/status/views.py` |
| `def get_machine_status()` | `def get_gateway_status()` | `gateway/status/views.py` |
| `from src.machine_status import MachineStatus` | `from src.gateway_status import GatewayStatus` | `gateway/status/views.py` |

### DigiCampServer

| Old | New | File |
|---|---|---|
| `def fetch_machine_status()` | `def fetch_gateway_status()` | `api/views/gateway_status.py` (was `machine_status.py`) |
| `def get_all_machine_status()` | `def get_all_gateway_status()` | `api/views/gateway_status.py` |
| `def merge_sim_information(machine_status)` | `def merge_sim_information(gateway_status)` | `api/views/gateway_status.py` |
| `class MachineStatusConsumer` | `class GatewayStatusConsumer` | `api/consumers.py` |
| `def get_machine_status()` | `def get_gateway_status()` | `src/get_gateway_status.py` (was `get_machine_status.py`) |
| `def get_machine_status()` | `def get_gateway_status()` | `phone_dialer.py` |

---

## File Renames

| Old Path | New Path |
|---|---|
| `32GSMgatewayServer/gateway/src/machine_status.py` | `gateway/src/gateway_status.py` |
| `DigiCampServer/digicamp/api/views/machine_status.py` | `api/views/gateway_status.py` |
| `DigiCampServer/digicamp/src/get_machine_status.py` | `src/get_gateway_status.py` |

---

## Settings Variable Renames

| Old | New | File |
|---|---|---|
| `VOICE_API_CREDENTIALS` | `DIGICAMP_CREDENTIALS` | `DigiCampServer/digicamp/digicamp_server/settings.py` |

---

## Systemd Service Renames (deploy_manager)

| Old | New |
|---|---|
| `machinestatus.service` | `32gsmgateway.service` |

---

## Deployment Path Changes

All RPi paths changed from `/home/pi/Documents/MachineStatus/` to `/home/pi/Documents/32GSMgatewayServer/`.

Affected scripts: `run_server.sh`, `dtmf.sh`, `update_code.sh`, `ami_listener.py`, `check_server.py`, `sync_to_rpi.sh`, `setup_asterisk.sh`, `asterisk_dialplan.conf`, `extensions.conf`.

---

## Dependent Service Action Items

Any service that calls these endpoints must update:

1. **Central VPS calling host**: `GET /machine_status` -> `GET /gateway_status`
2. **Flutter app (DigiCampInterface)**: `get_all_machine_status` -> `get_all_gateway_status`, `ws/machine-status/` -> `ws/gateway-status/`
3. **Any script importing from old module paths**: Update imports per tables above
4. **Pickle files**: `machine_status_fetch_time.pkl` -> `gateway_status_fetch_time.pkl` (auto-created, safe to delete old)
