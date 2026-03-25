# machine_status/src/voip_client.py

import os
import pickle
import random
import requests

from django.conf import settings
import time
class VoipGatewayClient:
    """
    Centralized login + cookie management for the VoIP gateway.
    """
    LOGIN_PATH    = "/cgi-bin/php/login.php"
    STATUS_PATH   = "/cgi-bin/php/system-status.php"
    GSM_PATH      = "/service?action=get_gsminfo"
    ERROR_SNIPPET = "alert('System Error! Please Contact Administor!')"

    def __init__(self):
        # read creds & cookie path from Django settings
        self.base        = settings.MACHINE_URL.rstrip("/")
        self.user        = settings.MACHINE_USERNAME
        self.pw          = settings.MACHINE_PASSWORD
        self.COOKIE_FILE = settings.MACHINE_COOKIE_FILE

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64)",
            "Referer":    f"{self.base}{self.LOGIN_PATH}"
        })
        self._load_cookies()

    def _full(self, path):
        return f"{self.base}{path}"

    def _load_cookies(self):
        if os.path.exists(self.COOKIE_FILE):
            with open(self.COOKIE_FILE, "rb") as f:
                self.session.cookies.update(pickle.load(f))

    def _save_cookies(self):
        with open(self.COOKIE_FILE, "wb") as f:
            pickle.dump(self.session.cookies, f)

    def _is_logged_in(self):
        try:
            r = self.session.get(
                self._full(self.STATUS_PATH),
                allow_redirects=False,
                timeout=5
            )
        except requests.RequestException:
            return False

        if r.status_code >= 500:
            return False
        text = r.text or ""
        if self.ERROR_SNIPPET in text:
            return False
        return "System Status" in text

    def _do_login(self):
        payload = {
            "username":     self.user,
            "password":     self.pw,
            "submit_login": "Login",
            "error_report": ""
        }
        r = self.session.post(
            self._full(self.LOGIN_PATH),
            data=payload,
            allow_redirects=True,
            timeout=5
        )
        r.raise_for_status()
        # ensure we actually landed on the status page
        if "System Status" not in (r.text or "") or self.ERROR_SNIPPET in r.text:
            raise RuntimeError("Login failed or server error after login")

    def ensure_login(self):
        if not self._is_logged_in():
            print("➜ Session invalid, re‑logging in…")
            self._do_login()
            self._save_cookies()
            print("✅ Logged in and cookies saved.")

    def _request(self, method, path, **kwargs):
        # Try to fetch data without login check first
        url = self._full(path)
        r = self.session.request(method, url, **kwargs)

        # Handle server errors or session issues
        if r.status_code >= 500 or (self.ERROR_SNIPPET in (r.text or "")):
            print("⚠️ Server error detected, refreshing session…")
            # Now perform login and try again
            self._do_login()
            self._save_cookies()
            r = self.session.request(method, url, **kwargs)
            
        r.raise_for_status()
         
        return r

    def get_status(self) -> dict:
        """Return the HTML of the system-status page or an error dict."""
        try:
            html = self._request("GET", self.STATUS_PATH).text
            return {"status": "ok", "data": html}
        except Exception as e:
            return {"status": "error", "message": f"VoIP gateway unreachable: {e}"}

    def get_gsminfo(self) -> dict:
        """
        Return the parsed JSON from the protected GSM info endpoint or an error dict.
        """
        rnd = random.random()
        try:
            return self._request(
                "GET",
                f"{self.GSM_PATH}&random={rnd}"
            ).json()
        except Exception as e:
            return {"status": "error", "message": f"VoIP gateway unreachable: {e}"}


# a module‑level singleton, import wherever you need it:
client = VoipGatewayClient()
