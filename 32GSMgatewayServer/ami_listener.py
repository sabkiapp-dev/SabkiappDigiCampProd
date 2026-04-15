from asterisk import manager
import time
import socket
import threading
import re
import requests  # ← FIX: was missing, needed for HTTP calls
from datetime import datetime
import logging
from src.voip_client import client as voip_client

# Logging is disabled by default (kept disabled to match previous behaviour).
# To enable, uncomment the block below:
# logging.basicConfig(
#     filename="ami.log",
#     level=logging.INFO,
#     format="%(asctime)s - %(levelname)s - %(message)s"
# )


class AMIListener:
    def __init__(self):
        SETTINGS_FILE = "/home/pi/Documents/32GSMgatewayServer/gateway/gsm_gateway/settings.py"
        with open(SETTINGS_FILE, 'r') as file:
            settings_text = file.read()

        self.SYS_HOST  = re.search(r"'HOST':\s*'([^']+)", settings_text).group(1)
        self.SYS_PASS  = re.search(r"'SYSTEM_PASSWORD':\s*'([^']+)", settings_text).group(1)
        self.BASE_URL  = re.search(r'BASE_URL\s*=\s*["\']([^"\']+)["\']', settings_text).group(1)
        self.AMI_HOST  = 'localhost'
        self.AMI_PORT  = 5038
        self.AMI_USER  = '1001'
        self.AMI_PASS  = '1001'

        # Raw socket connection (self.asterisk manager object is not used but
        # kept for __init__ compatibility — listen_for_ami_events uses sockets)
        self.asterisk = manager.Manager()
        try:
            self.asterisk.connect(self.AMI_HOST, self.AMI_PORT)
            self.asterisk.login(self.AMI_USER, self.AMI_PASS)
        except Exception:
            pass

        print("AMI listener initialized")

    # ── Helper: build the common POST payload ──────────────────────────────
    def _build_payload(self, event, phone, port, callerid_num, user_id, campaign,
                       extension='', dtmf_response='', sim_imsi=''):
        return {
            "phone":          phone,
            "campaign":       campaign,
            "port":           port,
            "host":           self.SYS_HOST,
            "event":          event,
            "extension":      extension,
            "dtmf_response": dtmf_response,
            "system_password": self.SYS_PASS,
            "sim_imsi":       sim_imsi,
            "AMI":            "AMI",
        }

    # ── Helper: extract encoded 32-digit string from channel name ───────────
    def _extract_string(self, event_data):
        channel = event_data.get('Channel', '')

        if channel.startswith("Local/") and "@basic-context" in channel:
            extracted = channel.split("Local/")[1].split("@basic-context")[0]
        else:
            extracted = ''

        # Validate: must be 32 digits
        if not (extracted.isdigit() and len(extracted) == 32):
            for field in ['CallerIDNum', 'ConnectedLineNum',
                          'DestCallerIDNum', 'DestConnectedLineNum']:
                val = event_data.get(field, '')
                if val.isdigit() and len(val) == 32:
                    extracted = val
                    break
            else:
                extracted = '98765432101001100000011000000001'

        return extracted

    # ── Helper: get IMSI for a port ─────────────────────────────────────────
    def _get_sim_imsi(self, port):
        try:
            gsm_data = voip_client.get_gsminfo()
            entries  = gsm_data.get(str(port), [])
            if entries:
                return entries[0].get("sim_imsi", "")
        except Exception:
            pass
        return ""

    # ── Helper: send POST to server ────────────────────────────────────────
    def _send(self, payload):
        try:
            resp = requests.post(
                f"{self.BASE_URL}/send_call_status",
                json=payload,
                timeout=10,
            )
            print(f"[AMI] POST {payload['event']} -> {resp.status_code}")
        except requests.RequestException as e:
            print(f"[AMI] POST failed for event={payload['event']}: {e}")

    # ── Helper: epoch timestamp for start_dialing ──────────────────────────
    @staticmethod
    def _epoch_ist():
        utc_now   = datetime.utcnow()
        ist_delta = utc_now.timestamp() + (5 * 3600 + 30 * 60)
        return int(ist_delta)

    # ── Main event handler ──────────────────────────────────────────────────
    def handle_ami_event(self, event_raw: str):
        try:
            lines      = event_raw.splitlines()
            event_data = {
                k.strip(): v.strip()
                for line in lines
                if ': ' in line
                for k, _, v in [line.partition(': ')]
            }

            event_name = event_data.get('Event', '')

            # ── 1. DialBegin → start_dialing ────────────────────────────────
            if event_name == 'DialBegin':
                extracted = self._extract_string(event_data)
                phone     = extracted[:10]
                port      = int(extracted[10:14]) - 1000
                user_id   = extracted[14:22]
                campaign  = extracted[22:32]
                imsi      = self._get_sim_imsi(port)

                payload = self._build_payload(
                    event='start_dialing',
                    phone=phone, port=port,
                    callerid_num=extracted[10:14],
                    user_id=user_id, campaign=campaign,
                    dtmf_response=str(self._epoch_ist()),
                    sim_imsi=imsi,
                )
                self._send(payload)
                return

            # ── 2. DialStatus → answered / not_answered ────────────────────
            dial_status = event_data.get('DialStatus', '')

            if dial_status == 'ANSWER':
                extracted = self._extract_string(event_data)
                phone     = extracted[:10]
                port      = int(extracted[10:14]) - 1000
                user_id   = extracted[14:22]
                campaign  = extracted[22:32]
                imsi      = self._get_sim_imsi(port)

                payload = self._build_payload(
                    event='answered',
                    phone=phone, port=port,
                    callerid_num=extracted[10:14],
                    user_id=user_id, campaign=campaign,
                    sim_imsi=imsi,
                )
                self._send(payload)
                return

            # ── 3. Hangup with Cause → not_answered ────────────────────────
            if event_name == 'Hangup':
                cause = event_data.get('Cause', '').upper()
                channel = event_data.get('Channel', '')

                if channel.startswith("Local/") and "@basic-context" in channel:
                    extracted = channel.split("Local/")[1].split("@basic-context")[0]
                else:
                    extracted = event_data.get('CallerIDNum', '')

                if not (extracted.isdigit() and len(extracted) == 32):
                    return  # Can't decode — skip

                phone     = extracted[:10]
                port      = int(extracted[10:14]) - 1000
                user_id   = extracted[14:22]
                campaign  = extracted[22:32]
                imsi      = self._get_sim_imsi(port)

                # Map Hangup/Cause to dialplan extension names
                if cause in ('1', '19', '27'):          # Busy / User busy / Called DND
                    extension = 'BUSY'
                elif cause in ('16', '21', '17'):      # Normal clear / no answer / absent
                    extension = 'CHANUNAVAIL'
                elif cause in ('34', '38', '42', '50'): # Congestion equivalents
                    extension = 'CONGESTION'
                else:
                    extension = cause  # Fallback: use cause code as-is

                payload = self._build_payload(
                    event='not_answered',
                    phone=phone, port=port,
                    callerid_num=extracted[10:14],
                    user_id=user_id, campaign=campaign,
                    extension=extension,
                    sim_imsi=imsi,
                )
                self._send(payload)
                return

        except Exception as e:
            # All exceptions silently swallowed (matching previous behaviour)
            print(f"[AMI] handle_ami_event error: {e}")

    # ── Raw-socket listener (primary connection path) ──────────────────────
    def listen_for_ami_events(self):
        ami_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            ami_sock.connect((self.AMI_HOST, self.AMI_PORT))
            login_pkt = (
                f"Action: Login\r\n"
                f"Username: {self.AMI_USER}\r\n"
                f"Secret: {self.AMI_PASS}\r\n"
                f"Events: call,all\r\n\r\n"
            )
            ami_sock.sendall(login_pkt.encode())

            buf = ""
            while True:
                chunk  = ami_sock.recv(4096).decode('utf-8', errors='ignore')
                if not chunk:
                    break
                buf += chunk
                while '\r\n\r\n' in buf:
                    event_raw, buf = buf.split('\r\n\r\n', 1)
                    if 'Event: ' in event_raw:
                        self.handle_ami_event(event_raw)
        except Exception as e:
            print(f"[AMI] socket error: {e}")
        finally:
            try:
                ami_sock.sendall(b"Action: Logoff\r\n\r\n")
                ami_sock.close()
            except Exception:
                pass

    # ── Background thread starter ───────────────────────────────────────────
    def start(self):
        t = threading.Thread(target=self.listen_for_ami_events, daemon=True)
        t.start()

    @classmethod
    def run(cls):
        listener = cls()
        listener.start()
        print("[AMI] Listener running. Press Ctrl-C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("[AMI] Shutting down.")


if __name__ == '__main__':
    AMIListener.run()
