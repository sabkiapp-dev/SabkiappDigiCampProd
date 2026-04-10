#!/usr/bin/env python3
"""
GSM Gateway Host Deployment Manager
PyQt5 GUI for managing Phase 1 (SD card prep) and Phase 2 (RPi post-boot setup)
"""

import sys
import os
import re
import json
import subprocess
import tempfile
import shutil
from dataclasses import dataclass, asdict, field
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QFormLayout, QGroupBox, QLineEdit, QSpinBox, QComboBox, QPlainTextEdit,
    QPushButton, QProgressBar, QLabel, QMessageBox, QFileDialog, QCheckBox,
    QListWidget, QListWidgetItem, QRadioButton, QButtonGroup, QSplitter,
    QSizePolicy, QStatusBar, QAction, QMenuBar, QFrame, QScrollArea,
    QInputDialog, QStackedWidget
)
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QFont, QColor, QPalette, QTextCursor, QValidator

TEMPLATES_DIR = Path(__file__).parent
CONFIG_PATH = Path.home() / ".config" / "gsm-gateway-deployer" / "config.json"

PHASE2_STEPS = [
    "Step 1: Copy MachineStatus from PC via SCP",
    "Step 2: Install Cloudflare Tunnel",
    "Step 3: Remove token from script for security",
    "Step 4: System update + Install Asterisk",
    "Step 5: Write extensions.conf",
    "Step 6: Write pjsip.conf",
    "Step 7: Create asterisk user + fix permissions",
    "Step 8: Configure /etc/default/asterisk",
    "Step 9: Enable and restart Asterisk",
]


# ─────────────────────────────────────────────
#  Theme
# ─────────────────────────────────────────────

DARK_STYLESHEET = """
QWidget {
    background-color: #0d1117;
    color: #c9d1d9;
    font-family: "Segoe UI", "SF Pro Display", "Ubuntu", "Cantarell", sans-serif;
    font-size: 13px;
}
QMainWindow { background-color: #0d1117; }
QMenuBar {
    background-color: #0d1117;
    color: #c9d1d9;
    border-bottom: 1px solid #30363d;
    padding: 2px 0;
}
QMenuBar::item { padding: 6px 12px; border-radius: 4px; background: transparent; }
QMenuBar::item:selected { background-color: #21262d; }
QMenu {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 6px;
}
QMenu::item { padding: 8px 24px 8px 12px; border-radius: 4px; }
QMenu::item:selected { background-color: #1f2937; color: #58a6ff; }
QMenu::separator { height: 1px; background-color: #30363d; margin: 4px 8px; }
QStatusBar {
    background-color: #0d1117;
    color: #8b949e;
    border-top: 1px solid #30363d;
    font-size: 12px;
    padding: 2px 8px;
}
QGroupBox {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    margin-top: 18px;
    padding: 16px 14px 14px 14px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 3px 10px;
    background-color: #1f2937;
    border: 1px solid #30363d;
    border-radius: 4px;
    color: #58a6ff;
    font-size: 11px;
    font-weight: 600;
}
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit {
    background-color: #0d1117;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 7px 11px;
    color: #c9d1d9;
    selection-background-color: #264f78;
    min-height: 18px;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus { border-color: #58a6ff; }
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled, QPlainTextEdit:disabled {
    background-color: #161b22;
    color: #484f58;
    border-color: #21262d;
}
QComboBox::drop-down { border: none; width: 20px; }
QComboBox::down-arrow {
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #8b949e;
    margin-right: 6px;
}
QComboBox QAbstractItemView {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 6px;
    selection-background-color: #1f2937;
    color: #c9d1d9;
    padding: 4px;
    outline: none;
}
QPushButton {
    background-color: #21262d;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 7px 16px;
    color: #c9d1d9;
    font-weight: 500;
    min-height: 18px;
}
QPushButton:hover { background-color: #30363d; border-color: #8b949e; }
QPushButton:pressed { background-color: #1c2128; }
QPushButton:disabled { background-color: #161b22; color: #484f58; border-color: #21262d; }
QPushButton:checked { background-color: #264f78; border-color: #58a6ff; color: #58a6ff; }
QPushButton#primaryBtn {
    background-color: #238636; border-color: #2ea043; color: #fff; font-weight: 600;
}
QPushButton#primaryBtn:hover { background-color: #2ea043; border-color: #3fb950; }
QPushButton#primaryBtn:disabled { background-color: #1a3028; color: #3fb950; border-color: #1a3028; }
QPushButton#dangerBtn {
    background-color: #da3633; border-color: #f85149; color: #fff; font-weight: 600;
}
QPushButton#dangerBtn:hover { background-color: #f85149; border-color: #ff7b72; }
QPushButton#dangerBtn:disabled { background-color: #3d1c1c; color: #f85149; border-color: #3d1c1c; }
QPushButton#accentBtn {
    background-color: #1f6feb; border-color: #388bfd; color: #fff; font-weight: 600;
}
QPushButton#accentBtn:hover { background-color: #388bfd; border-color: #58a6ff; }
QPushButton#navBtn {
    background-color: transparent;
    border: none;
    border-left: 2px solid transparent;
    border-radius: 0;
    padding: 10px 14px;
    color: #8b949e;
    text-align: left;
    font-weight: 400;
    font-size: 13px;
}
QPushButton#navBtn:hover { background-color: #1f2937; color: #c9d1d9; }
QPushButton#navBtn:checked {
    background-color: #1f2937;
    color: #58a6ff;
    border-left-color: #58a6ff;
    font-weight: 500;
}
QPushButton#collapseBtn {
    background-color: transparent;
    border: none;
    border-top: 1px solid #30363d;
    border-radius: 0;
    padding: 10px;
    color: #8b949e;
    text-align: center;
    font-size: 14px;
    min-height: 16px;
}
QPushButton#collapseBtn:hover { color: #c9d1d9; background-color: #1f2937; }
QProgressBar {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 6px;
    text-align: center;
    color: #c9d1d9;
    min-height: 22px;
    font-size: 12px;
    font-weight: 500;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1f6feb, stop:1 #58a6ff);
    border-radius: 5px;
}
QScrollArea { border: none; background-color: transparent; }
QScrollArea > QWidget > QWidget { background-color: transparent; }
QScrollBar:vertical {
    background-color: #0d1117; width: 8px; border-radius: 4px; margin: 0;
}
QScrollBar::handle:vertical {
    background-color: #30363d; border-radius: 4px; min-height: 24px;
}
QScrollBar::handle:vertical:hover { background-color: #484f58; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    height: 0; background: none;
}
QScrollBar:horizontal {
    background-color: #0d1117; height: 8px; border-radius: 4px; margin: 0;
}
QScrollBar::handle:horizontal {
    background-color: #30363d; border-radius: 4px; min-width: 24px;
}
QScrollBar::handle:horizontal:hover { background-color: #484f58; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    width: 0; background: none;
}
QLabel { color: #c9d1d9; background-color: transparent; }
QListWidget {
    background-color: #0d1117; border: 1px solid #30363d;
    border-radius: 6px; padding: 4px; outline: none;
}
QListWidget::item { padding: 6px 8px; border-radius: 4px; }
QListWidget::item:selected { background-color: #1f2937; color: #58a6ff; }
QListWidget::item:hover { background-color: #161b22; }
QCheckBox, QRadioButton { spacing: 8px; color: #c9d1d9; background: transparent; }
QToolTip {
    background-color: #1f2937; color: #c9d1d9;
    border: 1px solid #30363d; border-radius: 4px; padding: 5px 9px; font-size: 12px;
}
QFrame#pageSeparator { background-color: #30363d; max-height: 1px; border: none; }
QFrame#sidebar { background-color: #161b22; border-right: 1px solid #30363d; }
"""


def setup_dark_theme(app: QApplication) -> None:
    """Apply GitHub Dark palette and QSS stylesheet to the application."""
    app.setStyle("Fusion")
    c = QColor
    palette = QPalette()
    palette.setColor(QPalette.Window,           c("#0d1117"))
    palette.setColor(QPalette.WindowText,       c("#c9d1d9"))
    palette.setColor(QPalette.Base,             c("#0d1117"))
    palette.setColor(QPalette.AlternateBase,    c("#161b22"))
    palette.setColor(QPalette.ToolTipBase,      c("#1f2937"))
    palette.setColor(QPalette.ToolTipText,      c("#c9d1d9"))
    palette.setColor(QPalette.Text,             c("#c9d1d9"))
    palette.setColor(QPalette.Button,           c("#21262d"))
    palette.setColor(QPalette.ButtonText,       c("#c9d1d9"))
    palette.setColor(QPalette.BrightText,       c("#f0f6fc"))
    palette.setColor(QPalette.Link,             c("#58a6ff"))
    palette.setColor(QPalette.Highlight,        c("#264f78"))
    palette.setColor(QPalette.Mid,           c("#30363d"))
    palette.setColor(QPalette.Midlight,      c("#21262d"))
    palette.setColor(QPalette.Dark,          c("#0d1117"))
    palette.setColor(QPalette.Shadow,        c("#010409"))
    palette.setColor(QPalette.HighlightedText,  c("#f0f6fc"))
    palette.setColor(QPalette.Disabled, QPalette.Text,       c("#484f58"))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, c("#484f58"))
    palette.setColor(QPalette.Disabled, QPalette.WindowText, c("#484f58"))
    app.setPalette(palette)
    app.setStyleSheet(DARK_STYLESHEET)


# ─────────────────────────────────────────────
#  Data Model
# ─────────────────────────────────────────────

@dataclass
class ConfigModel:
    # Phase 1 – SD Card
    device: str = "/dev/sdd"
    hostname: str = "host1"
    user_name: str = "pi"
    user_pass: str = "123"
    wifi_ssid: str = "BRS_Bhawan_5G"
    wifi_pass: str = "123456789"
    rpi_ip: str = "192.168.1.100"
    rpi_gateway: str = "192.168.8.1"
    rpi_dns: str = "8.8.8.8"
    ubuntu_image_path: str = ""
    # Phase 2 – Deployment (cloudflare_token excluded — entered at runtime, never saved)
    code_path: str = ""    # local .zip path to code on this PC
    gateway_ip: str = "192.168.8.50"

    # SSH for remote execution (password always used; defaults to Phase 1 user_pass)
    ssh_user: str = "pi"
    ssh_pass: str = ""
    rpi_hostname: str = ""  # used to name the generated SSH key (e.g. host2)


def parse_script_defaults(model: ConfigModel) -> None:
    """Parse existing shell scripts to populate model defaults."""
    install_path = TEMPLATES_DIR / "install_ubuntu_rpi5.sh"
    setup_path = TEMPLATES_DIR / "setup_asterisk.sh"

    var_map = {
        "DEVICE": "device",
        "HOSTNAME": "hostname",
        "USER_NAME": "user_name",
        "USER_PASS": "user_pass",
        "WIFI_SSID": "wifi_ssid",
        "WIFI_PASS": "wifi_pass",
        "RPI_IP": "rpi_ip",
        "RPI_GATEWAY": "rpi_gateway",
        "RPI_DNS": "rpi_dns",
    }

    if install_path.exists():
        content = install_path.read_text()
        for var, attr in var_map.items():
            m = re.search(rf'^{var}=["\']?([^"\'#\n]*)["\']?', content, re.MULTILINE)
            if m:
                setattr(model, attr, m.group(1).strip())

    # Auto-detect Ubuntu image
    downloads = Path.home() / "Downloads"
    images = sorted(downloads.glob("ubuntu-*preinstalled-server-arm64+raspi.img.xz"))
    if images:
        model.ubuntu_image_path = str(images[-1])

    # Cloudflare token is never stored — entered at runtime only


def load_config() -> ConfigModel:
    model = ConfigModel()
    parse_script_defaults(model)
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text())
            for key, val in data.items():
                if hasattr(model, key):
                    setattr(model, key, val)
        except Exception:
            pass
    return model


def save_config(model: ConfigModel) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(model)
    CONFIG_PATH.write_text(json.dumps(data, indent=2))


# ─────────────────────────────────────────────
#  Config Generator
# ─────────────────────────────────────────────

class ConfigGenerator:
    def __init__(self, model: ConfigModel):
        self.model = model

    def _scripts_dir(self) -> Path:
        """Return Path to setup_asterisk/ folder derived from code_path zip, or TEMPLATES_DIR fallback."""
        cp = self.model.code_path.strip()
        if cp.endswith(".zip"):
            candidate = Path(cp).parent / Path(cp).stem / "setup_asterisk"
            if candidate.is_dir():
                return candidate
        return TEMPLATES_DIR

    def generate_pjsip_conf(self) -> str:
        result = (self._scripts_dir() / "pjsip.conf").read_text()
        result = result.replace("192.168.8.50", self.model.gateway_ip)
        return result

    def generate_extensions_conf(self) -> str:
        result = (self._scripts_dir() / "extensions.conf").read_text()
        result = result.replace("/home/pi/", f"/home/{self.model.user_name}/")
        return result

    def generate_cloudinit_userdata(self) -> str:
        m = self.model
        passwd_hash = "$(openssl passwd -6 " + m.user_pass + ")"
        return f"""#cloud-config
hostname: {m.hostname}
manage_etc_hosts: true
users:
  - name: {m.user_name}
    sudo: ALL=(ALL) NOPASSWD:ALL
    groups: users, admin, sudo
    shell: /bin/bash
    lock_passwd: false
    passwd: {passwd_hash}
"""

    def generate_cloudinit_network(self) -> str:
        m = self.model
        return f"""version: 2
ethernets:
  eth0:
    dhcp4: false
    optional: true
    addresses: [{m.rpi_ip}/24]
    routes:
      - to: default
        via: {m.rpi_gateway}
    nameservers:
      addresses: [{m.rpi_dns}]
wifis:
  wlan0:
    dhcp4: false
    optional: true
    addresses: [{m.rpi_ip}/24]
    routes:
      - to: default
        via: {m.rpi_gateway}
    nameservers:
      addresses: [{m.rpi_dns}]
    access-points:
      "{m.wifi_ssid}":
        password: "{m.wifi_pass}"
"""

    def generate_phase1_script(self) -> str:
        m = self.model
        src = (TEMPLATES_DIR / "install_ubuntu_rpi5.sh").read_text()

        replacements = {
            "DEVICE": m.device,
            "HOSTNAME": m.hostname,
            "USER_NAME": m.user_name,
            "USER_PASS": m.user_pass,
            "WIFI_SSID": m.wifi_ssid,
            "WIFI_PASS": m.wifi_pass,
            "RPI_IP": m.rpi_ip,
            "RPI_GATEWAY": m.rpi_gateway,
            "RPI_DNS": m.rpi_dns,
        }

        # Line-by-line replacement — handles trailing spaces/comments reliably
        out_lines = []
        for line in src.splitlines(keepends=True):
            replaced = False
            for var, val in replacements.items():
                if re.match(rf'^{var}=', line):
                    comment_m = re.search(r'([ \t]+#.*)$', line.rstrip('\n'))
                    comment = comment_m.group(1) if comment_m else ""
                    out_lines.append(f'{var}="{val}"{comment}\n')
                    replaced = True
                    break
            if not replaced:
                out_lines.append(line)
        result = "".join(out_lines)

        # Override image auto-detection if user specified a path
        if m.ubuntu_image_path:
            result = re.sub(
                r'IMG_FILE=\$\(ls[^\n]*\)',
                f'IMG_FILE="{m.ubuntu_image_path}"',
                result
            )

        return result

    def generate_phase2_script(self, cf_token: str = "") -> str:
        m = self.model
        result = (self._scripts_dir() / "setup_asterisk.sh").read_text()

        # CLOUDFLARE_TOKEN: left empty in preview; callers pass cf_token only for in-memory use

        # Remove Step 1 interactive read prompts — MachineStatus is SCP'd before script runs
        result = re.sub(
            r'read -p\s*"[^"]*IP[^"]*"\s*HOST_IP',
            f'HOST_IP="localhost"  # SCP handled by deploy_manager',
            result
        )
        result = re.sub(
            r'read -p\s*"[^"]*username[^"]*"\s*HOST_USER',
            f'HOST_USER="localhost"  # SCP handled by deploy_manager',
            result
        )
        result = re.sub(
            r'read -p\s*"[^"]*path[^"]*"\s*HOST_PATH',
            f'HOST_PATH="/home/{m.user_name}/Documents/MachineStatus"  # already SCP\'d',
            result
        )
        # Skip the scp command in step 1 — already done before script runs
        result = result.replace(
            'scp -r "$HOST_USER@$HOST_IP:$HOST_PATH" /home/pi/Documents/MachineStatus',
            'echo "-> MachineStatus already copied by deploy_manager (skipping scp)"'
        )

        # Replace gateway IP
        result = result.replace("192.168.8.50", m.gateway_ip)

        # Replace user paths
        result = result.replace("/home/pi/", f"/home/{m.user_name}/")

        return result

    def generate_cloudflare_script(self, cf_token: str = "") -> str:
        src = (TEMPLATES_DIR / "setup_cloudflare_tunnel.sh").read_text()
        result = re.sub(
            r'^CLOUDFLARE_TOKEN=.*$',
            f'CLOUDFLARE_TOKEN="{cf_token}"',
            src,
            flags=re.MULTILINE
        )
        return result


# ─────────────────────────────────────────────
#  Script Runner (QThread)
# ─────────────────────────────────────────────

class ScriptRunner(QThread):
    output_line = pyqtSignal(str)
    step_detected = pyqtSignal(int, str)   # step_index, step_label
    finished_signal = pyqtSignal(int)       # return code

    def __init__(self, command: list, env: dict = None, stdin_data: bytes = None):
        super().__init__()
        self.command = command
        self.env = env
        self.stdin_data = stdin_data
        self._process = None

    def run(self):
        import threading
        merged_env = os.environ.copy()
        if self.env:
            merged_env.update(self.env)

        try:
            self._process = subprocess.Popen(
                self.command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE if self.stdin_data else None,
                env=merged_env,
                bufsize=1,
                text=True,
            )

            if self.stdin_data:
                # Write stdin in a separate thread to avoid pipe deadlock
                # when the script is larger than the OS pipe buffer (~64 KB)
                def _feed_stdin():
                    try:
                        self._process.stdin.write(self.stdin_data.decode())
                    finally:
                        self._process.stdin.close()
                t = threading.Thread(target=_feed_stdin, daemon=True)
                t.start()

            step_pattern = re.compile(r'---\s+Step\s+(\d+)[:\s]+(.*?)---', re.IGNORECASE)

            for line in self._process.stdout:
                line = line.rstrip('\n')
                self.output_line.emit(line)
                m = step_pattern.search(line)
                if m:
                    self.step_detected.emit(int(m.group(1)) - 1, m.group(2).strip())

            self._process.wait()
            self.finished_signal.emit(self._process.returncode)

        except Exception as e:
            self.output_line.emit(f"[ERROR] {e}")
            self.finished_signal.emit(-1)

    def terminate_process(self):
        if self._process and self._process.poll() is None:
            self._process.terminate()


# ─────────────────────────────────────────────
#  UI Helpers
# ─────────────────────────────────────────────

def make_terminal() -> QPlainTextEdit:
    t = QPlainTextEdit()
    t.setReadOnly(True)
    font = QFont("JetBrains Mono", 10)
    font.setStyleHint(QFont.TypeWriter)
    t.setFont(font)
    t.setStyleSheet(
        "QPlainTextEdit {"
        "  background-color: #0a0c10;"
        "  color: #a5d6ff;"
        "  border: 1px solid #30363d;"
        "  border-radius: 8px;"
        "  padding: 12px;"
        "  selection-background-color: #264f78;"
        "}"
    )
    t.setMinimumHeight(200)
    return t


def append_terminal(terminal: QPlainTextEdit, text: str):
    terminal.appendPlainText(text)
    terminal.moveCursor(QTextCursor.End)


class _IpValidator(QValidator):
    def validate(self, s, pos):
        parts = s.split('.')
        if len(parts) > 4:
            return (QValidator.Invalid, s, pos)
        for part in parts:
            if part == '':
                continue
            if not part.isdigit():
                return (QValidator.Invalid, s, pos)
            if int(part) > 255:
                return (QValidator.Invalid, s, pos)
        if len(parts) == 4 and all(p != '' for p in parts):
            return (QValidator.Acceptable, s, pos)
        return (QValidator.Intermediate, s, pos)


def make_ip_validator():
    return _IpValidator()


def ensure_sshpass(parent_widget=None) -> bool:
    """Return True if sshpass is available; offer to install it via GUI sudo prompt if not."""
    if shutil.which("sshpass"):
        return True

    reply = QMessageBox.question(
        parent_widget, "sshpass not found",
        "sshpass is required for password-based SSH.\n\nInstall it now?",
        QMessageBox.Yes | QMessageBox.No
    )
    if reply != QMessageBox.Yes:
        return False

    sudo_pass, ok = QInputDialog.getText(
        parent_widget, "Sudo Password",
        "Enter your sudo (system) password to install sshpass:",
        QLineEdit.Password
    )
    if not ok or not sudo_pass:
        return False

    try:
        result = subprocess.run(
            ["sudo", "-S", "apt-get", "install", "-y", "sshpass"],
            input=sudo_pass + "\n",
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0 and shutil.which("sshpass"):
            QMessageBox.information(parent_widget, "Installed", "sshpass installed successfully.")
            return True
        else:
            QMessageBox.critical(parent_widget, "Failed",
                                 f"Could not install sshpass:\n{result.stderr.strip() or result.stdout.strip()}")
            return False
    except Exception as e:
        QMessageBox.critical(parent_widget, "Error", f"Install failed:\n{e}")
        return False


def password_field(placeholder: str = "") -> tuple:
    """Return (QLineEdit, QPushButton) for a password field with visibility toggle."""
    edit = QLineEdit()
    edit.setEchoMode(QLineEdit.Password)
    if placeholder:
        edit.setPlaceholderText(placeholder)
    btn = QPushButton("Show")
    btn.setFixedWidth(56)
    btn.setCheckable(True)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setToolTip("Toggle password visibility")

    def toggle(checked):
        edit.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)
        btn.setText("Hide" if checked else "Show")

    btn.toggled.connect(toggle)
    return edit, btn


def hbox(*widgets) -> QHBoxLayout:
    layout = QHBoxLayout()
    for w in widgets:
        if isinstance(w, QWidget):
            layout.addWidget(w)
        elif isinstance(w, int) and w == 0:
            layout.addStretch()
    return layout


# ─────────────────────────────────────────────
#  Page Header Helper
# ─────────────────────────────────────────────

def make_page_header(title: str, subtitle: str = "") -> QWidget:
    """Return a widget containing a bold title, optional subtitle, and separator line."""
    container = QWidget()
    container.setStyleSheet("background: transparent;")
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 12)
    layout.setSpacing(4)

    title_lbl = QLabel(title)
    title_lbl.setStyleSheet(
        "color: #f0f6fc; font-size: 18px; font-weight: 600; background: transparent;"
    )
    layout.addWidget(title_lbl)

    if subtitle:
        sub_lbl = QLabel(subtitle)
        sub_lbl.setStyleSheet(
            "color: #8b949e; font-size: 13px; background: transparent;"
        )
        layout.addWidget(sub_lbl)

    sep = QFrame()
    sep.setObjectName("pageSeparator")
    sep.setFrameShape(QFrame.HLine)
    layout.addWidget(sep)

    return container


# ─────────────────────────────────────────────
#  Sidebar Widget
# ─────────────────────────────────────────────

class SidebarWidget(QFrame):
    """Collapsible left sidebar with nav items and status indicators."""

    page_changed = pyqtSignal(int)

    EXPANDED_WIDTH = 210
    COLLAPSED_WIDTH = 52

    NAV_ITEMS = [
        ("\u25a0", "Phase 1 \u00b7 SD Card"),
        ("\u25b6", "Phase 2 \u00b7 RPi Setup"),
        ("\u25c8", "Config Preview"),
        ("\u2699", "Utilities"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self._collapsed = False
        self._nav_buttons: list = []
        self._status_labels: dict = {}
        self._build_ui()
        self._setup_animation()

    def _build_ui(self):
        self.setFixedWidth(self.EXPANDED_WIDTH)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # App title
        self._title_label = QLabel("GSM DEPLOYER")
        self._title_label.setStyleSheet(
            "color: #58a6ff; font-weight: 700; font-size: 13px;"
            " padding: 18px 16px 14px 16px; letter-spacing: 0.5px;"
            " background: transparent;"
        )
        layout.addWidget(self._title_label)

        # Title separator
        sep_top = QFrame()
        sep_top.setObjectName("pageSeparator")
        sep_top.setFrameShape(QFrame.HLine)
        layout.addWidget(sep_top)

        # Nav buttons
        nav_container = QWidget()
        nav_container.setStyleSheet("background: transparent;")
        nav_layout = QVBoxLayout(nav_container)
        nav_layout.setContentsMargins(0, 8, 0, 8)
        nav_layout.setSpacing(2)

        self._btn_group = QButtonGroup(self)
        self._btn_group.setExclusive(True)

        for i, (icon, label) in enumerate(self.NAV_ITEMS):
            btn = QPushButton(f"  {icon}  {label}")
            btn.setObjectName("navBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(label)
            btn.clicked.connect(lambda _checked, idx=i: self.page_changed.emit(idx))
            self._btn_group.addButton(btn, i)
            nav_layout.addWidget(btn)
            self._nav_buttons.append(btn)

        self._nav_buttons[0].setChecked(True)
        layout.addWidget(nav_container)

        # Spacer
        layout.addStretch()

        # Status section separator
        sep_bot = QFrame()
        sep_bot.setObjectName("pageSeparator")
        sep_bot.setFrameShape(QFrame.HLine)
        layout.addWidget(sep_bot)

        # Status indicators
        self._status_container = QWidget()
        self._status_container.setStyleSheet("background: transparent;")
        st_layout = QVBoxLayout(self._status_container)
        st_layout.setContentsMargins(14, 10, 14, 10)
        st_layout.setSpacing(6)

        hdr = QLabel("STATUS")
        hdr.setStyleSheet(
            "color: #484f58; font-size: 10px; font-weight: 600;"
            " letter-spacing: 1px; background: transparent;"
        )
        st_layout.addWidget(hdr)

        for key, text in [("ssh", "SSH: \u2014"), ("flash", "Flash: \u2014")]:
            lbl = QLabel(f"\u25cf  {text}")
            lbl.setStyleSheet("color: #484f58; font-size: 11px; background: transparent;")
            st_layout.addWidget(lbl)
            self._status_labels[key] = lbl

        layout.addWidget(self._status_container)

        # Collapse button
        self._collapse_btn = QPushButton("\u276e")
        self._collapse_btn.setObjectName("collapseBtn")
        self._collapse_btn.setFixedHeight(38)
        self._collapse_btn.setCursor(Qt.PointingHandCursor)
        self._collapse_btn.setToolTip("Collapse sidebar")
        self._collapse_btn.clicked.connect(self.toggle_collapse)
        layout.addWidget(self._collapse_btn)

    def _setup_animation(self):
        self._anim = QPropertyAnimation(self, b"maximumWidth")
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.InOutCubic)
        self._anim.finished.connect(self._on_anim_done)

    # ── Public API ────────────────────────────

    def set_active_page(self, idx: int) -> None:
        if 0 <= idx < len(self._nav_buttons):
            self._nav_buttons[idx].setChecked(True)

    def update_status(self, key: str, ok: bool, label: str = "") -> None:
        lbl = self._status_labels.get(key)
        if not lbl:
            return
        color = "#3fb950" if ok else "#484f58"
        text = label or (key.title() + (": OK" if ok else ": \u2014"))
        lbl.setStyleSheet(f"color: {color}; font-size: 11px; background: transparent;")
        lbl.setText(f"\u25cf  {text}")

    def toggle_collapse(self) -> None:
        self._collapsed = not self._collapsed
        self._anim.stop()

        if self._collapsed:
            # Shrink: hide text first, then animate
            self._title_label.hide()
            self._status_container.hide()
            for i, btn in enumerate(self._nav_buttons):
                btn.setText(f"  {self.NAV_ITEMS[i][0]}")
            self._collapse_btn.setText("\u276f")
            self._collapse_btn.setToolTip("Expand sidebar")
            self.setMinimumWidth(self.COLLAPSED_WIDTH)
            start_w, end_w = self.width(), self.COLLAPSED_WIDTH
        else:
            # Expand: animate first, then show text in _on_anim_done
            self._collapse_btn.setText("\u276e")
            self._collapse_btn.setToolTip("Collapse sidebar")
            self.setMinimumWidth(0)
            start_w, end_w = self.COLLAPSED_WIDTH, self.EXPANDED_WIDTH

        self._anim.setStartValue(start_w)
        self._anim.setEndValue(end_w)
        self._anim.start()

    def _on_anim_done(self) -> None:
        target = self.COLLAPSED_WIDTH if self._collapsed else self.EXPANDED_WIDTH
        self.setMinimumWidth(target)
        self.setMaximumWidth(target)
        if not self._collapsed:
            # Show labels after expand animation completes
            self._title_label.show()
            self._status_container.show()
            for i, btn in enumerate(self._nav_buttons):
                icon, label = self.NAV_ITEMS[i]
                btn.setText(f"  {icon}  {label}")


# ─────────────────────────────────────────────
#  Step Wizard Widget
# ─────────────────────────────────────────────

class StepWizardWidget(QWidget):
    """Horizontal step-progress indicator for Phase 2 execution."""

    def __init__(self, total_steps: int = 6, parent=None):
        super().__init__(parent)
        self._total = total_steps
        self._active = -1
        self._circles: list = []
        self._lines: list = []
        self._label_widget = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 12, 0, 8)
        root.setSpacing(6)

        row = QHBoxLayout()
        row.setSpacing(0)
        row.setContentsMargins(0, 0, 0, 0)

        for i in range(self._total):
            circle = QLabel(str(i + 1))
            circle.setAlignment(Qt.AlignCenter)
            circle.setFixedSize(30, 30)
            circle.setStyleSheet(self._style("pending"))
            row.addWidget(circle)
            self._circles.append(circle)

            if i < self._total - 1:
                line = QFrame()
                line.setFrameShape(QFrame.HLine)
                line.setFixedHeight(2)
                line.setStyleSheet("background-color: #30363d; border: none;")
                row.addWidget(line, 1)
                self._lines.append(line)

        root.addLayout(row)

        self._label_widget = QLabel("")
        self._label_widget.setAlignment(Qt.AlignCenter)
        self._label_widget.setStyleSheet("color: #8b949e; font-size: 12px;")
        root.addWidget(self._label_widget)

    @staticmethod
    def _style(state: str) -> str:
        base = "QLabel { border-radius: 15px; font-size: 12px; font-weight: 600; "
        if state == "completed":
            return base + "background-color: #238636; color: #ffffff; }"
        if state == "active":
            return base + "background-color: #1f6feb; color: #ffffff; border: 2px solid #58a6ff; }"
        if state == "failed":
            return base + "background-color: #da3633; color: #ffffff; }"
        # pending
        return base + "background-color: #21262d; color: #8b949e; border: 1px solid #30363d; }"

    # ── Public API ────────────────────────────

    def set_active_step(self, n: int) -> None:
        """Mark step n (1-based) as active; all prior steps become completed."""
        self._active = n
        for i, circle in enumerate(self._circles):
            sn = i + 1
            if sn < n:
                circle.setText("\u2713")
                circle.setStyleSheet(self._style("completed"))
                if i < len(self._lines):
                    self._lines[i].setStyleSheet("background-color: #238636; border: none;")
            elif sn == n:
                circle.setText(str(sn))
                circle.setStyleSheet(self._style("active"))
            else:
                circle.setText(str(sn))
                circle.setStyleSheet(self._style("pending"))

    def set_step_label(self, text: str) -> None:
        if self._label_widget:
            self._label_widget.setText(text)

    def mark_all_completed(self) -> None:
        for i, circle in enumerate(self._circles):
            circle.setText("\u2713")
            circle.setStyleSheet(self._style("completed"))
            if i < len(self._lines):
                self._lines[i].setStyleSheet("background-color: #238636; border: none;")
        if self._label_widget:
            self._label_widget.setStyleSheet("color: #3fb950; font-size: 12px;")
            self._label_widget.setText("All steps completed successfully")

    def mark_failed(self) -> None:
        if self._active == -1:
            return
        n = self._active
        for i, circle in enumerate(self._circles):
            sn = i + 1
            if sn < n:
                circle.setText("\u2713")
                circle.setStyleSheet(self._style("completed"))
            elif sn == n:
                circle.setText("\u2717")
                circle.setStyleSheet(self._style("failed"))
            else:
                circle.setText(str(sn))
                circle.setStyleSheet(self._style("pending"))
        if self._label_widget:
            self._label_widget.setStyleSheet("color: #f85149; font-size: 12px;")
            if not self._label_widget.text():
                self._label_widget.setText("Step failed")

    def reset(self) -> None:
        self._active = -1
        for i, circle in enumerate(self._circles):
            circle.setText(str(i + 1))
            circle.setStyleSheet(self._style("pending"))
            if i < len(self._lines):
                self._lines[i].setStyleSheet("background-color: #30363d; border: none;")
        if self._label_widget:
            self._label_widget.setStyleSheet("color: #8b949e; font-size: 12px;")
            self._label_widget.setText("")


# ─────────────────────────────────────────────
#  Phase 1 Widget
# ─────────────────────────────────────────────

class Phase1Widget(QWidget):
    flash_completed = pyqtSignal(bool)

    def __init__(self, model: ConfigModel, generator: ConfigGenerator, parent=None):
        super().__init__(parent)
        self.model = model
        self.generator = generator
        self.runner = None
        self._build_ui()
        self._load_values()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        # Page header
        root.addWidget(make_page_header(
            "Phase 1 \u2014 SD Card Preparation",
            "Configure and flash Ubuntu to the SD card for Raspberry Pi"
        ))

        # ── Config Group ──────────────────────────────
        cfg_group = QGroupBox("SD Card Configuration")
        form = QFormLayout(cfg_group)
        form.setLabelAlignment(Qt.AlignRight)
        form.setVerticalSpacing(12)
        form.setHorizontalSpacing(16)

        # Device
        dev_layout = QHBoxLayout()
        self.device_combo = QComboBox()
        self.device_combo.setEditable(True)
        self.device_combo.setMinimumWidth(160)
        self.detect_btn = QPushButton("Detect")
        self.detect_btn.setFixedWidth(70)
        self.detect_btn.setToolTip("Scan for USB block devices")
        self.detect_btn.clicked.connect(self._detect_devices)
        dev_layout.addWidget(self.device_combo)
        dev_layout.addWidget(self.detect_btn)
        form.addRow("SD Card Device:", dev_layout)

        self.device_path_label = QLabel()
        self.device_path_label.setStyleSheet("color: #f85149; font-weight: bold;")
        form.addRow("Will flash to:", self.device_path_label)

        self.hostname_edit = QLineEdit()
        form.addRow("Hostname:", self.hostname_edit)

        self.username_edit = QLineEdit()
        form.addRow("Username:", self.username_edit)

        self.pass_edit, pass_btn = password_field()
        pw_layout = QHBoxLayout()
        pw_layout.addWidget(self.pass_edit)
        pw_layout.addWidget(pass_btn)
        form.addRow("Password:", pw_layout)

        self.ssid_edit = QLineEdit()
        form.addRow("WiFi SSID:", self.ssid_edit)

        self.wifi_pass_edit, wp_btn = password_field()
        wp_layout = QHBoxLayout()
        wp_layout.addWidget(self.wifi_pass_edit)
        wp_layout.addWidget(wp_btn)
        form.addRow("WiFi Password:", wp_layout)

        self.rpi_ip_edit = QLineEdit()
        self.rpi_ip_edit.setValidator(make_ip_validator())
        form.addRow("RPi Static IP:", self.rpi_ip_edit)

        self.gateway_edit = QLineEdit()
        self.gateway_edit.setValidator(make_ip_validator())
        form.addRow("Router/Gateway IP:", self.gateway_edit)

        self.dns_edit = QLineEdit()
        self.dns_edit.setValidator(make_ip_validator())
        form.addRow("DNS Server:", self.dns_edit)

        img_layout = QHBoxLayout()
        self.image_edit = QLineEdit()
        self.image_edit.setPlaceholderText("Auto-detected from ~/Downloads")
        img_browse = QPushButton("Browse")
        img_browse.setFixedWidth(65)
        img_browse.clicked.connect(self._browse_image)
        img_layout.addWidget(self.image_edit)
        img_layout.addWidget(img_browse)
        form.addRow("Ubuntu Image:", img_layout)

        root.addWidget(cfg_group)

        # ── Buttons ───────────────────────────────────
        btn_layout = QHBoxLayout()
        self.preview_btn = QPushButton("Preview Generated Script")
        self.preview_btn.clicked.connect(self._emit_preview)
        self.flash_btn = QPushButton("Flash SD Card")
        self.flash_btn.setObjectName("dangerBtn")
        self.flash_btn.clicked.connect(self._flash)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel)
        btn_layout.addWidget(self.preview_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.flash_btn)
        root.addLayout(btn_layout)

        # ── Progress ──────────────────────────────────
        self.progress = QProgressBar()
        self.progress.setMaximum(8)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setFormat("Ready")
        root.addWidget(self.progress)

        # ── Terminal ──────────────────────────────────
        root.addWidget(QLabel("Output:"))
        self.terminal = make_terminal()
        root.addWidget(self.terminal)

        self._wire_signals()

    def _wire_signals(self):
        def update(attr):
            return lambda val: (setattr(self.model, attr, val), None)

        def _on_device_changed(_=None):
            path = self.device_combo.currentData() or self.device_combo.currentText()
            self.model.device = path
            self.device_path_label.setText(path)
        self.device_combo.currentIndexChanged.connect(_on_device_changed)
        self.device_combo.editTextChanged.connect(lambda t: _on_device_changed())
        self.hostname_edit.textChanged.connect(lambda v: setattr(self.model, 'hostname', v))
        self.username_edit.textChanged.connect(lambda v: setattr(self.model, 'user_name', v))
        self.pass_edit.textChanged.connect(lambda v: setattr(self.model, 'user_pass', v))
        self.ssid_edit.textChanged.connect(lambda v: setattr(self.model, 'wifi_ssid', v))
        self.wifi_pass_edit.textChanged.connect(lambda v: setattr(self.model, 'wifi_pass', v))
        self.rpi_ip_edit.textChanged.connect(lambda v: setattr(self.model, 'rpi_ip', v))
        self.gateway_edit.textChanged.connect(lambda v: setattr(self.model, 'rpi_gateway', v))
        self.dns_edit.textChanged.connect(lambda v: setattr(self.model, 'rpi_dns', v))
        self.image_edit.textChanged.connect(lambda v: setattr(self.model, 'ubuntu_image_path', v))

    def _load_values(self):
        m = self.model
        self.device_combo.setCurrentText(m.device)
        self.device_path_label.setText(m.device)
        self.hostname_edit.setText(m.hostname)
        self.username_edit.setText(m.user_name)
        self.pass_edit.setText(m.user_pass)
        self.ssid_edit.setText(m.wifi_ssid)
        self.wifi_pass_edit.setText(m.wifi_pass)
        self.rpi_ip_edit.setText(m.rpi_ip)
        self.gateway_edit.setText(m.rpi_gateway)
        self.dns_edit.setText(m.rpi_dns)
        self.image_edit.setText(m.ubuntu_image_path)

    def _detect_devices(self):
        self.terminal.appendPlainText("Scanning block devices...")
        try:
            result = subprocess.run(
                ["lsblk", "-d", "-J", "-o", "NAME,SIZE,MODEL,TRAN"],
                capture_output=True, text=True
            )
            import json as _json
            data = _json.loads(result.stdout)
            devices = data.get("blockdevices", [])

            self.device_combo.clear()
            usb_found = []
            for dev in devices:
                tran = (dev.get("tran") or "").lower()
                name = dev.get("name", "")
                size = dev.get("size", "")
                model = (dev.get("model") or "").strip()
                self.terminal.appendPlainText(f"  /dev/{name}  size={size}  tran={tran or '?'}  model={model or '?'}")
                if tran == "usb":
                    path = f"/dev/{name}"
                    label = f"{path} ({size}{', ' + model if model else ''})"
                    usb_found.append((path, label))

            if usb_found:
                for dev_path, label in usb_found:
                    self.device_combo.addItem(label, dev_path)
                self.device_combo.setCurrentIndex(0)
                # Manually sync model since setCurrentIndex(0) may not fire signal if already 0
                self.model.device = usb_found[0][0]
                self.device_path_label.setText(usb_found[0][0])
                self.terminal.appendPlainText(f"Found {len(usb_found)} USB device(s).")
            else:
                self.device_combo.addItem(self.model.device)
                self.device_path_label.setText(self.model.device)
                self.terminal.appendPlainText("No USB devices detected. Using default.")
        except Exception as e:
            self.terminal.appendPlainText(f"Error: {e}")

    def _browse_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Ubuntu Image", str(Path.home() / "Downloads"),
            "XZ Images (*.xz);;All Files (*)"
        )
        if path:
            self.image_edit.setText(path)

    def _emit_preview(self):
        # Signal the main window to switch to preview tab showing phase1 script
        self.window().show_preview("phase1")

    def _flash(self):
        device = self.model.device
        if not device:
            QMessageBox.warning(self, "No Device", "Please select an SD card device.")
            return

        ret = QMessageBox.warning(
            self, "Confirm Flash",
            f"This will PERMANENTLY ERASE ALL DATA on:\n\n  {device}\n\n"
            "Make sure you have selected the correct device!\n\nProceed?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if ret != QMessageBox.Yes:
            return

        # Generate script to /tmp
        try:
            script_content = self.generator.generate_phase1_script()
            script_path = "/tmp/deploy_phase1_generated.sh"
            with open(script_path, "w") as f:
                f.write(script_content)
            os.chmod(script_path, 0o755)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to generate script:\n{e}")
            return

        self.terminal.clear()
        self.progress.setValue(0)
        self.progress.setFormat("Starting...")
        self.flash_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)

        self.runner = ScriptRunner(["pkexec", "bash", script_path])
        self.runner.output_line.connect(lambda l: append_terminal(self.terminal, l))
        self.runner.step_detected.connect(self._on_step)
        self.runner.finished_signal.connect(self._on_finished)
        self.runner.start()

    def _on_step(self, idx: int, label: str):
        self.progress.setValue(idx + 1)
        self.progress.setFormat(f"Step {idx + 1}/8: {label[:40]}")

    def _on_finished(self, code: int):
        self.flash_completed.emit(code == 0)
        self.flash_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        if code == 0:
            self.progress.setValue(8)
            self.progress.setFormat("Done!")
            append_terminal(self.terminal, "\n[SUCCESS] Phase 1 complete.")
        else:
            self.progress.setFormat(f"Failed (exit {code})")
            append_terminal(self.terminal, f"\n[FAILED] Exit code: {code}")

    def _cancel(self):
        if self.runner:
            self.runner.terminate_process()
        self.cancel_btn.setEnabled(False)
        append_terminal(self.terminal, "\n[CANCELLED] by user.")


# ─────────────────────────────────────────────
#  Phase 2 Widget
# ─────────────────────────────────────────────

class Phase2Widget(QWidget):
    ssh_status_changed = pyqtSignal(bool)

    def __init__(self, model: ConfigModel, generator: ConfigGenerator, parent=None):
        super().__init__(parent)
        self.model = model
        self.generator = generator
        self.runner = None
        self._build_ui()
        self._load_values()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        # Page header
        root.addWidget(make_page_header(
            "Phase 2 \u2014 RPi Deployment",
            "Deploy code and configure the Raspberry Pi over SSH"
        ))

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(12)

        # ── 1. SSH Connection ─────────────────────────
        ssh_group = QGroupBox("SSH Connection (RPi)")
        ssh_form = QFormLayout(ssh_group)
        ssh_form.setLabelAlignment(Qt.AlignRight)
        ssh_form.setVerticalSpacing(12)
        ssh_form.setHorizontalSpacing(16)

        self.ssh_ip_edit = QLineEdit()
        self.ssh_ip_edit.setValidator(make_ip_validator())
        self.ssh_ip_edit.setPlaceholderText("e.g. 192.168.8.59")
        ssh_form.addRow("RPi Static IP:", self.ssh_ip_edit)

        self.ssh_gateway_edit = QLineEdit()
        self.ssh_gateway_edit.setValidator(make_ip_validator())
        self.ssh_gateway_edit.setPlaceholderText("e.g. 192.168.8.1")
        ssh_form.addRow("Router/Gateway IP:", self.ssh_gateway_edit)

        self.ssh_user_edit = QLineEdit()
        ssh_form.addRow("SSH Username:", self.ssh_user_edit)

        self.ssh_pass_edit, ssh_pbtn = password_field("SSH password (same as Phase 1)")
        sp_layout = QHBoxLayout()
        sp_layout.addWidget(self.ssh_pass_edit)
        sp_layout.addWidget(ssh_pbtn)
        ssh_form.addRow("SSH Password:", sp_layout)

        self.hostname_edit = QLineEdit()
        self.hostname_edit.setPlaceholderText("e.g. host2 \u2014 used to name the SSH key")
        ssh_form.addRow("Hostname:", self.hostname_edit)

        self.test_ssh_btn = QPushButton("Test SSH Connection")
        self.test_ssh_btn.setObjectName("accentBtn")
        self.test_ssh_btn.clicked.connect(self._test_ssh)
        self.ssh_status_label = QLabel("")
        test_layout = QHBoxLayout()
        test_layout.addWidget(self.test_ssh_btn)
        test_layout.addWidget(self.ssh_status_label)
        test_layout.addStretch()
        ssh_form.addRow("", test_layout)

        scroll_layout.addWidget(ssh_group)

        # ── 2. Deployment Configuration ───────────────
        dep_group = QGroupBox("Deployment Configuration")
        dep_form = QFormLayout(dep_group)
        dep_form.setLabelAlignment(Qt.AlignRight)
        dep_form.setVerticalSpacing(12)
        dep_form.setHorizontalSpacing(16)

        code_layout = QHBoxLayout()
        self.code_path_edit = QLineEdit()
        self.code_path_edit.setPlaceholderText("Select .zip of code on this PC")
        code_browse = QPushButton("Browse")
        code_browse.setFixedWidth(65)
        code_browse.clicked.connect(self._browse_code)
        code_layout.addWidget(self.code_path_edit)
        code_layout.addWidget(code_browse)
        dep_form.addRow("Code (.zip):", code_layout)

        self.cf_token_edit, cf_show_btn = password_field("Token \u2014 skip if Cloudflare already running")
        self.cf_token_edit.setToolTip(
            "Cloudflare tunnel token. Optional \u2014 if cloudflared is already running on the RPi, "
            "leave this empty and it will be skipped automatically."
        )
        cf_layout = QHBoxLayout()
        cf_layout.addWidget(self.cf_token_edit)
        cf_layout.addWidget(cf_show_btn)
        dep_form.addRow("Cloudflare Token:", cf_layout)

        scroll_layout.addWidget(dep_group)

        # ── 3. GSM Gateway ────────────────────────────
        gw_group = QGroupBox("GSM Gateway")
        gw_form = QFormLayout(gw_group)
        gw_form.setLabelAlignment(Qt.AlignRight)
        gw_form.setVerticalSpacing(12)
        gw_form.setHorizontalSpacing(16)

        self.gw_ip_edit = QLineEdit()
        self.gw_ip_edit.setValidator(make_ip_validator())
        gw_form.addRow("GSM Gateway IP:", self.gw_ip_edit)

        scroll_layout.addWidget(gw_group)

        scroll_area.setWidget(scroll_content)
        root.addWidget(scroll_area)

        # ── Buttons ───────────────────────────────────
        btn_layout = QHBoxLayout()
        self.execute_btn = QPushButton("Execute on RPi")
        self.execute_btn.setObjectName("primaryBtn")
        self.execute_btn.clicked.connect(self._execute)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel)
        btn_layout.addStretch()
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.execute_btn)
        root.addLayout(btn_layout)

        # ── Step Wizard (hidden until execution starts) ─
        self.step_wizard = StepWizardWidget(total_steps=6)
        self.step_wizard.hide()
        root.addWidget(self.step_wizard)

        # ── Progress ──────────────────────────────────
        self.progress = QProgressBar()
        self.progress.setMaximum(6)
        self.progress.setValue(0)
        self.progress.setFormat("Ready")
        root.addWidget(self.progress)

        # ── Terminal ──────────────────────────────────
        root.addWidget(QLabel("Output:"))
        self.terminal = make_terminal()
        root.addWidget(self.terminal)

        # ── Download Public Key (hidden until key ready) ──
        self.dl_key_btn = QPushButton("Download Public Key")
        self.dl_key_btn.setObjectName("accentBtn")
        self.dl_key_btn.clicked.connect(self._download_pubkey)
        self.dl_key_btn.hide()
        root.addWidget(self.dl_key_btn)

        self._wire_signals()

    def _wire_signals(self):
        self.ssh_ip_edit.textChanged.connect(lambda v: setattr(self.model, 'rpi_ip', v))
        self.ssh_gateway_edit.textChanged.connect(lambda v: setattr(self.model, 'rpi_gateway', v))
        self.ssh_user_edit.textChanged.connect(lambda v: setattr(self.model, 'ssh_user', v))
        self.ssh_pass_edit.textChanged.connect(lambda v: setattr(self.model, 'ssh_pass', v))
        self.hostname_edit.textChanged.connect(lambda v: setattr(self.model, 'rpi_hostname', v))
        self.code_path_edit.textChanged.connect(lambda v: setattr(self.model, 'code_path', v))
        self.gw_ip_edit.textChanged.connect(lambda v: setattr(self.model, 'gateway_ip', v))
        # cf_token_edit is intentionally not wired to model — never persisted

    def _load_values(self):
        m = self.model
        self.ssh_ip_edit.setText(m.rpi_ip)
        self.ssh_gateway_edit.setText(m.rpi_gateway)
        self.ssh_user_edit.setText(m.ssh_user)
        self.ssh_pass_edit.setText(m.ssh_pass or m.user_pass)
        self.hostname_edit.setText(m.rpi_hostname or m.hostname)
        self.code_path_edit.setText(m.code_path)
        self.gw_ip_edit.setText(m.gateway_ip)

    def _browse_code(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Code ZIP", str(Path.home()), "ZIP files (*.zip)"
        )
        if path:
            self.code_path_edit.setText(path)

    def _test_ssh(self):
        if not ensure_sshpass(self):
            return
        self.ssh_status_label.setText("Testing...")
        self.ssh_status_label.setStyleSheet("")
        rpi_ip = self.model.rpi_ip
        user = self.model.ssh_user
        ssh_pass = self.model.ssh_pass
        cmd = ["sshpass", "-p", ssh_pass,
               "ssh", "-o", "ConnectTimeout=5",
               "-o", "StrictHostKeyChecking=no",
               "-o", "UserKnownHostsFile=/dev/null",
               "-o", "LogLevel=ERROR",
               f"{user}@{rpi_ip}", "echo OK"]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                self.ssh_status_label.setText("Connected!")
                self.ssh_status_label.setStyleSheet("color: #3fb950; font-weight: bold;")
                self.ssh_status_changed.emit(True)
            else:
                self.ssh_status_label.setText("Failed")
                self.ssh_status_label.setStyleSheet("color: #f85149;")
                self.ssh_status_changed.emit(False)
                append_terminal(self.terminal, f"SSH test failed: {result.stderr.strip()}")
        except Exception as e:
            self.ssh_status_label.setText("Error")
            self.ssh_status_label.setStyleSheet("color: #f85149;")
            self.ssh_status_changed.emit(False)
            append_terminal(self.terminal, f"SSH error: {e}")

    def _execute(self):
        if not ensure_sshpass(self):
            return
        rpi_ip     = self.model.rpi_ip
        user       = self.model.ssh_user
        ssh_pass   = self.model.ssh_pass
        hostname   = self.hostname_edit.text().strip() or self.model.hostname
        code_zip   = self.model.code_path.strip()
        cf_token   = self.cf_token_edit.text().strip()
        gateway_ip = self.model.gateway_ip

        if not rpi_ip:
            QMessageBox.warning(self, "Missing Field", "RPi Static IP is required."); return
        if not user:
            QMessageBox.warning(self, "Missing Field", "SSH Username is required."); return
        if not ssh_pass:
            QMessageBox.warning(self, "Missing Field", "SSH Password is required."); return
        if not code_zip:
            QMessageBox.warning(self, "Missing Field", "Code .zip path is required."); return
        if not code_zip.endswith(".zip"):
            QMessageBox.warning(self, "Invalid File", "Code path must be a .zip file."); return
        # cf_token is optional — if CF is already running on RPi, it will be skipped automatically

        self.terminal.clear()
        self.dl_key_btn.hide()
        self.progress.setValue(0)
        self.progress.setFormat("Starting...")
        self.execute_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        # Show and reset step wizard
        self.step_wizard.reset()
        self.step_wizard.show()

        zip_name  = Path(code_zip).name
        key_name  = f"{hostname}_ed25519"
        dest_home = f"/home/{user}"
        ssh_opts  = ["-o", "ConnectTimeout=15",
                     "-o", "StrictHostKeyChecking=no",
                     "-o", "UserKnownHostsFile=/dev/null",
                     "-o", "LogLevel=ERROR"]
        sp        = ["sshpass", "-p", ssh_pass]

        # ── Generate config files locally (no sensitive data) ──────────────
        import tempfile as _tempfile

        pjsip_content = self.generator.generate_pjsip_conf()
        local_pjsip = _tempfile.mktemp(suffix="_pjsip.conf")
        with open(local_pjsip, "w") as fh:
            fh.write(pjsip_content)

        ext_content = self.generator.generate_extensions_conf()
        local_ext = _tempfile.mktemp(suffix="_extensions.conf")
        with open(local_ext, "w") as fh:
            fh.write(ext_content)

        # Build Asterisk configure script (no sensitive data — safe to SCP)
        asterisk_cfg_script = f"""#!/bin/bash
set -e
echo "-> Copying configs to /etc/asterisk/"
cp /tmp/pjsip_deploy.conf /etc/asterisk/pjsip.conf
cp /tmp/extensions_deploy.conf /etc/asterisk/extensions.conf

echo "-> Copying sound files to /var/lib/asterisk/sounds/en/"
mkdir -p /var/lib/asterisk/sounds/en/names
cp /tmp/asterisk_sounds_en/*.wav /var/lib/asterisk/sounds/en/
chown -R {user}:asterisk /var/lib/asterisk/sounds/en
chmod -R 755 /var/lib/asterisk/sounds/en
find /var/lib/asterisk/sounds/en -type f -exec chmod 644 {{}} +

echo "-> Creating symlink for Asterisk sound lookup"
if [ ! -L /usr/share/asterisk/sounds ] && [ -d /usr/share/asterisk/sounds ]; then
    rm -rf /usr/share/asterisk/sounds
fi
if [ ! -L /usr/share/asterisk/sounds ]; then
    ln -s /var/lib/asterisk/sounds /usr/share/asterisk/sounds
fi

echo "-> Installing SoX for audio conversion"
apt-get install -y sox

echo "-> Creating asterisk user if needed"
if ! id "asterisk" >/dev/null 2>&1; then
    adduser --system --group --home /var/lib/asterisk --no-create-home --gecos "Asterisk PBX" asterisk
fi
usermod -a -G asterisk {user}

echo "-> Setting permissions"
chown -R asterisk:asterisk /etc/asterisk /var/log/asterisk /var/spool/asterisk
chown -R asterisk:asterisk /var/lib/asterisk
chown -R {user}:asterisk /var/lib/asterisk/sounds/en
if [ -d /usr/lib/asterisk/modules ]; then chown -R asterisk:asterisk /usr/lib/asterisk/modules; fi
find /etc/asterisk -type d -exec chmod 755 {{}} +
find /var/lib/asterisk -type d -exec chmod 755 {{}} +
find /var/spool/asterisk -type d -exec chmod 755 {{}} +
find /etc/asterisk -type f -exec chmod 644 {{}} +
find /var/lib/asterisk -type f -exec chmod 644 {{}} +
if [ -d /var/spool/asterisk/outgoing ]; then chmod 770 /var/spool/asterisk/outgoing; fi

echo "-> Configuring Asterisk Manager Interface (AMI)"
cat > /etc/asterisk/manager.conf <<'AMIEOF'
[general]
enabled = yes
port = 5038
bindaddr = 127.0.0.1

[1001]
secret = 1001
deny = 0.0.0.0/0.0.0.0
permit = 127.0.0.1/255.255.255.0
read = all
write = all
AMIEOF

echo "-> Configuring /etc/default/asterisk"
if [ -f /etc/default/asterisk ]; then
    sed -i 's/^#*AST_USER=.*/AST_USER="asterisk"/' /etc/default/asterisk
    sed -i 's/^#*AST_GROUP=.*/AST_GROUP="asterisk"/' /etc/default/asterisk
else
    printf 'AST_USER="asterisk"\\nAST_GROUP="asterisk"\\n' > /etc/default/asterisk
fi

echo "-> Enabling and restarting Asterisk"
systemctl enable asterisk
systemctl restart asterisk
echo "-> Asterisk is running."
"""
        local_ast_cfg = _tempfile.mktemp(suffix="_asterisk_configure.sh")
        with open(local_ast_cfg, "w") as fh:
            fh.write(asterisk_cfg_script)

        # ── Steps ──────────────────────────────────────────────────────────

        # Step 1 – SCP zip to RPi
        step1 = " ".join(sp + ["scp"] + ssh_opts + [code_zip, f"{user}@{rpi_ip}:{dest_home}/Documents/"])

        # Step 2 – Install unzip if missing, then unzip on RPi
        step2 = " ".join(sp + ["ssh"] + ssh_opts + [f"{user}@{rpi_ip}",
            f'"command -v unzip >/dev/null 2>&1 || sudo apt-get install -y unzip && '
            f'mkdir -p {dest_home}/Documents && cd {dest_home}/Documents && unzip -o {zip_name}"'])

        # Step 3 – Install Cloudflare tunnel only if not already running
        # CF token is used in-memory only — never written to any file on the RPi
        cf_install_body = (
            "sudo mkdir -p --mode=0755 /usr/share/keyrings && "
            "curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg"
            " | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null && "
            "echo 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg]"
            " https://pkg.cloudflare.com/cloudflared any main'"
            " | sudo tee /etc/apt/sources.list.d/cloudflared.list && "
            "sudo apt-get update -qq && sudo apt-get install -y cloudflared && "
            f"sudo cloudflared service install '{cf_token}' && "
            "sudo systemctl enable cloudflared && sudo systemctl start cloudflared"
        )
        cf_install_cmd = (
            "if systemctl is-active --quiet cloudflared 2>/dev/null; then "
            "echo '-> Cloudflare tunnel already running, skipping installation'; "
            "else "
            f"if [ -z '{cf_token}' ]; then echo 'ERROR: Cloudflare not running and no token provided' && exit 1; fi && "
            f"{cf_install_body}; "
            "fi"
        )
        step3 = " ".join(sp + ["ssh"] + ssh_opts + [f"{user}@{rpi_ip}", f'"{cf_install_cmd}"'])

        # Step 4 – Install Asterisk + configure (no CF token involved)
        #   4a: apt install
        step4a = " ".join(sp + ["ssh"] + ssh_opts + [f"{user}@{rpi_ip}",
            '"if command -v asterisk >/dev/null 2>&1; then '
            'echo \\"-> Asterisk already installed, skipping\\"; '
            'else '
            'sudo apt-get update -qq && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y asterisk; '
            'fi"'])
        #   4b: SCP pjsip.conf, extensions.conf, configure script, sound files
        step4b_pjsip = " ".join(sp + ["scp"] + ssh_opts + [local_pjsip, f"{user}@{rpi_ip}:/tmp/pjsip_deploy.conf"])
        step4b_ext   = " ".join(sp + ["scp"] + ssh_opts + [local_ext,   f"{user}@{rpi_ip}:/tmp/extensions_deploy.conf"])
        step4b_cfg   = " ".join(sp + ["scp"] + ssh_opts + [local_ast_cfg, f"{user}@{rpi_ip}:/tmp/asterisk_configure.sh"])
        sounds_dir   = str(TEMPLATES_DIR / "sounds" / "en")
        step4b_snd   = " ".join(sp + ["scp"] + ssh_opts + ["-r", sounds_dir, f"{user}@{rpi_ip}:/tmp/asterisk_sounds_en"])
        #   4c: run configure script with sudo
        step4c = " ".join(sp + ["ssh"] + ssh_opts + [f"{user}@{rpi_ip}",
            '"sudo bash /tmp/asterisk_configure.sh"'])

        # Step 5 – Setup MachineStatus (venv, pip, migrations, systemd)
        ms_dir = f"{dest_home}/Documents/MachineStatus"
        ms_venv = f"{ms_dir}/ms_env"
        ms_django = f"{ms_dir}/machine_status"

        # Build the systemd service unit (no sensitive data)
        # run_server.sh has sleep 30 inside, so we background it to avoid blocking systemctl
        ms_service_content = f"""[Unit]
Description=MachineStatus Server
After=network.target asterisk.service

[Service]
Type=oneshot
RemainAfterExit=yes
User={user}
WorkingDirectory={ms_dir}
ExecStartPre=-/usr/bin/pkill -u {user} -f "python.*manage.py runserver"
ExecStartPre=-/usr/bin/pkill -u {user} -f "python.*ami_listener"
ExecStartPre=-/usr/bin/pkill -u {user} -f "python.*check_server"
ExecStartPre=/bin/sleep 1
ExecStart=/bin/bash -c "{ms_dir}/run_server.sh &"
ExecStop=-/usr/bin/pkill -u {user} -f "python.*manage.py runserver"
ExecStop=-/usr/bin/pkill -u {user} -f "python.*ami_listener"
ExecStop=-/usr/bin/pkill -u {user} -f "python.*check_server"
Environment=PYTHONPATH={ms_dir}:{ms_django}
Environment=DJANGO_SETTINGS_MODULE=machine_status.settings

[Install]
WantedBy=multi-user.target
"""
        local_ms_service = _tempfile.mktemp(suffix="_machinestatus.service")
        with open(local_ms_service, "w") as fh:
            fh.write(ms_service_content)

        # Build MachineStatus setup script
        ms_setup_script = f"""#!/bin/bash

echo "-> Setting GATEWAY_IP to {gateway_ip} in settings.py"
sed -i 's/^GATEWAY_IP = .*/GATEWAY_IP = "{gateway_ip}"/' {ms_django}/machine_status/settings.py

echo "-> Setting HOST to {hostname} in settings.py"
sed -i "s/'HOST': '[^']*'/'HOST': '{hostname}'/" {ms_django}/machine_status/settings.py

echo "-> Installing python3-venv, pip, and ffmpeg if needed"
sudo apt-get update -qq
sudo apt-get install -y python3-venv python3-pip ffmpeg

echo "-> Creating virtualenv at {ms_venv}"
if [ ! -d "{ms_venv}" ]; then
    python3 -m venv {ms_venv}
fi

echo "-> Installing Python dependencies"
source {ms_venv}/bin/activate
pip install --upgrade pip
pip install -r {ms_dir}/requirements.txt

cd {ms_django}
export PYTHONPATH={ms_dir}:{ms_django}
export DJANGO_SETTINGS_MODULE=machine_status.settings

echo "-> Creating log directory"
mkdir -p {ms_dir}/logs
chmod 777 {ms_dir}/logs 2>/dev/null || true

echo "-> Stopping existing MachineStatus processes"
pkill -f 'manage.py runserver' 2>/dev/null || true
pkill -f 'ami_listener.py' 2>/dev/null || true
pkill -f 'check_server.py' 2>/dev/null || true
sleep 2

echo "-> Installing systemd service"
sudo cp /tmp/machinestatus_deploy.service /etc/systemd/system/machinestatus.service
sudo systemctl daemon-reload
sudo systemctl enable machinestatus.service
sudo systemctl restart --no-block machinestatus.service
sleep 3
echo "-> MachineStatus service started on port 9000."
"""
        local_ms_setup = _tempfile.mktemp(suffix="_ms_setup.sh")
        with open(local_ms_setup, "w") as fh:
            fh.write(ms_setup_script)

        step5a_scp_svc   = " ".join(sp + ["scp"] + ssh_opts + [local_ms_service, f"{user}@{rpi_ip}:/tmp/machinestatus_deploy.service"])
        step5a_scp_setup = " ".join(sp + ["scp"] + ssh_opts + [local_ms_setup,   f"{user}@{rpi_ip}:/tmp/ms_setup.sh"])
        step5b_run       = " ".join(sp + ["ssh"] + ssh_opts + [f"{user}@{rpi_ip}",
            '"bash /tmp/ms_setup.sh"'])

        # Step 6 – Generate ed25519 key pair only if it doesn't already exist
        step6 = " ".join(sp + ["ssh"] + ssh_opts + [f"{user}@{rpi_ip}",
            f'"mkdir -p {dest_home}/.ssh && '
            f'if [ -f {dest_home}/.ssh/{key_name}.pub ]; then '
            f'echo \\"-> SSH key {key_name} already exists, using existing key\\"; '
            f'else '
            f'ssh-keygen -t ed25519 -f {dest_home}/.ssh/{key_name} -N \\"\\" -q; '
            f'fi"'])

        # Step 7 – SCP public key back to this PC
        self._local_pubkey = f"/tmp/{key_name}.pub"
        step7 = " ".join(sp + ["scp"] + ssh_opts +
                         [f"{user}@{rpi_ip}:{dest_home}/.ssh/{key_name}.pub", self._local_pubkey])

        shell_cmd = " && ".join([
            'echo "[Step 1/6] SCP code zip to RPi..."',            step1,
            'echo "[Step 2/6] Unzipping on RPi..."',               step2,
            'echo "[Step 3/6] Installing Cloudflare tunnel..."',    step3,
            'echo "[Step 4/6] Installing & configuring Asterisk..."',
                step4a,
                step4b_pjsip, step4b_ext, step4b_cfg, step4b_snd,
                step4c,
            'echo "[Step 5/6] Setting up MachineStatus server..."',
                step5a_scp_svc, step5a_scp_setup,
                step5b_run,
            'echo "[Step 6/6] Generating SSH ed25519 key..."',     step6,
            'echo "[INFO] Fetching public key..."',                 step7,
            'echo "[DONE]"',
        ])

        append_terminal(self.terminal, f"[INFO] Target : {user}@{rpi_ip}")
        append_terminal(self.terminal, f"[INFO] Zip    : {code_zip}")
        append_terminal(self.terminal, f"[INFO] Key    : {key_name}\n")

        self._key_name = key_name
        self.runner = ScriptRunner(["bash", "-c", shell_cmd])
        self.runner.output_line.connect(self._on_output_line)
        self.runner.finished_signal.connect(self._on_finished)
        self.runner.start()

    def _on_output_line(self, line: str):
        append_terminal(self.terminal, line)
        if line.startswith("[Step "):
            step_n = int(line[6]) if line[6].isdigit() else 0
            if step_n:
                self.step_wizard.set_active_step(step_n)
                self.step_wizard.set_step_label(line.strip())
                self.progress.setValue(step_n)
                self.progress.setFormat(line.strip())

    def _on_finished(self, code: int):
        self.execute_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        if code == 0:
            self.progress.setValue(6)
            self.progress.setFormat("Done!")
            self.step_wizard.mark_all_completed()
            append_terminal(self.terminal, "\n[SUCCESS] All steps complete.")
            self.dl_key_btn.show()
        else:
            self.progress.setFormat(f"Failed (exit {code})")
            self.step_wizard.mark_failed()
            self.step_wizard.hide()
            append_terminal(self.terminal, f"\n[FAILED] Exit code: {code}")

    def _download_pubkey(self):
        key_name = getattr(self, '_key_name', 'rpi_ed25519')
        local_src = getattr(self, '_local_pubkey', f'/tmp/{key_name}.pub')
        dest, _ = QFileDialog.getSaveFileName(
            self, "Save Public Key", str(Path.home() / f"{key_name}.pub"), "Public Key (*.pub);;All Files (*)"
        )
        if dest:
            try:
                shutil.copy2(local_src, dest)
                QMessageBox.information(self, "Saved", f"Public key saved to:\n{dest}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not save key:\n{e}")

    def _cancel(self):
        if self.runner:
            self.runner.terminate_process()
        self.execute_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.step_wizard.reset()
        self.step_wizard.hide()
        append_terminal(self.terminal, "\n[CANCELLED] by user.")

    def refresh_from_model(self):
        self.ssh_ip_edit.setText(self.model.rpi_ip)
        self.ssh_gateway_edit.setText(self.model.rpi_gateway)


# ─────────────────────────────────────────────
#  Config Preview Widget
# ─────────────────────────────────────────────

class ConfigPreviewWidget(QWidget):
    PREVIEWS = [
        ("Phase 1 Script (install_ubuntu_rpi5.sh)", "phase1"),
        ("Phase 2 Script (setup_asterisk.sh)", "phase2"),
        ("pjsip.conf", "pjsip"),
        ("extensions.conf", "extensions"),
        ("cloud-init: user-data", "userdata"),
        ("cloud-init: network-config", "network"),
        ("Cloudflare Tunnel Script", "cloudflare"),
    ]

    def __init__(self, model: ConfigModel, generator: ConfigGenerator, parent=None):
        super().__init__(parent)
        self.model = model
        self.generator = generator
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        root.addWidget(make_page_header(
            "Config Preview",
            "Review generated configuration files before deployment"
        ))

        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("Preview:"))
        self.selector = QComboBox()
        for label, _ in self.PREVIEWS:
            self.selector.addItem(label)
        self.selector.currentIndexChanged.connect(self._refresh)
        top_layout.addWidget(self.selector, 1)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self._refresh)
        top_layout.addWidget(self.refresh_btn)
        root.addLayout(top_layout)

        self.text_area = make_terminal()
        self.text_area.setReadOnly(True)
        root.addWidget(self.text_area)

        btn_layout = QHBoxLayout()
        copy_btn = QPushButton("Copy to Clipboard")
        copy_btn.clicked.connect(self._copy)
        save_btn = QPushButton("Save As...")
        save_btn.clicked.connect(self._save)
        btn_layout.addWidget(copy_btn)
        btn_layout.addWidget(save_btn)
        btn_layout.addStretch()
        root.addLayout(btn_layout)

        self._refresh()

    def refresh(self):
        self._refresh()

    def _refresh(self):
        idx = self.selector.currentIndex()
        key = self.PREVIEWS[idx][1]
        try:
            content = self._generate(key)
        except Exception as e:
            content = f"[Error generating preview]\n{e}"
        self.text_area.setPlainText(content)

    def _generate(self, key: str) -> str:
        g = self.generator
        if key == "phase1":
            return g.generate_phase1_script()
        elif key == "phase2":
            return g.generate_phase2_script()
        elif key == "pjsip":
            return g.generate_pjsip_conf()
        elif key == "extensions":
            return g.generate_extensions_conf()
        elif key == "userdata":
            return g.generate_cloudinit_userdata()
        elif key == "network":
            return g.generate_cloudinit_network()
        elif key == "cloudflare":
            return g.generate_cloudflare_script()
        return ""

    def show_key(self, key: str):
        for i, (_, k) in enumerate(self.PREVIEWS):
            if k == key:
                self.selector.setCurrentIndex(i)
                self._refresh()
                return

    def _copy(self):
        QApplication.clipboard().setText(self.text_area.toPlainText())

    def _save(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save As", str(Path.home()), "All Files (*)")
        if path:
            with open(path, "w") as f:
                f.write(self.text_area.toPlainText())


# ─────────────────────────────────────────────
#  Utilities Widget
# ─────────────────────────────────────────────

class UtilitiesWidget(QWidget):
    def __init__(self, model: ConfigModel, generator: ConfigGenerator, parent=None):
        super().__init__(parent)
        self.model = model
        self.generator = generator
        self.runners = {}
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        root.addWidget(make_page_header(
            "Utilities",
            "Standalone tools and diagnostics"
        ))

        # ── Cloudflare ────────────────────────────────
        cf_group = QGroupBox("Cloudflare Tunnel Setup (standalone)")
        cf_layout = QVBoxLayout(cf_group)
        cf_form = QFormLayout()
        cf_form.setLabelAlignment(Qt.AlignRight)
        cf_form.setVerticalSpacing(12)
        cf_form.setHorizontalSpacing(16)

        self.cf_token_util_edit, tok_btn = password_field("Enter Cloudflare token (not saved)")
        tok_layout = QHBoxLayout()
        tok_layout.addWidget(self.cf_token_util_edit)
        tok_layout.addWidget(tok_btn)
        cf_form.addRow("Cloudflare Token:", tok_layout)
        cf_layout.addLayout(cf_form)

        cf_btn_layout = QHBoxLayout()
        cf_run_btn = QPushButton("Run on RPi (SSH)")
        cf_run_btn.clicked.connect(self._run_cloudflare)
        cf_btn_layout.addWidget(cf_run_btn)
        cf_btn_layout.addStretch()
        cf_layout.addLayout(cf_btn_layout)

        self.cf_terminal = make_terminal()
        self.cf_terminal.setMinimumHeight(0)
        self.cf_terminal.setMaximumHeight(140)
        cf_layout.addWidget(self.cf_terminal)
        root.addWidget(cf_group)

        # ── Permissions ───────────────────────────────
        perm_group = QGroupBox("Fix Asterisk Permissions (standalone)")
        perm_layout = QVBoxLayout(perm_group)

        perm_btn_layout = QHBoxLayout()
        perm_run_btn = QPushButton("Run on RPi (SSH)")
        perm_run_btn.clicked.connect(self._run_permissions)
        perm_btn_layout.addWidget(perm_run_btn)
        perm_btn_layout.addStretch()
        perm_layout.addLayout(perm_btn_layout)

        self.perm_terminal = make_terminal()
        self.perm_terminal.setMinimumHeight(0)
        self.perm_terminal.setMaximumHeight(140)
        perm_layout.addWidget(self.perm_terminal)
        root.addWidget(perm_group)

        # ── Device Scanner ────────────────────────────
        scan_group = QGroupBox("Block Device Scanner")
        scan_layout = QVBoxLayout(scan_group)
        scan_btn = QPushButton("Scan Devices")
        scan_btn.clicked.connect(self._scan_devices)
        scan_layout.addWidget(scan_btn)
        self.scan_terminal = make_terminal()
        self.scan_terminal.setMinimumHeight(0)
        self.scan_terminal.setMaximumHeight(180)
        scan_layout.addWidget(self.scan_terminal)
        root.addWidget(scan_group)

        root.addStretch()

    def refresh_from_model(self):
        pass  # no synced fields in utilities tab

    def _ssh_cmd(self, remote_script_path: str, script_content: str) -> tuple:
        """Returns (command_list, stdin_bytes) for running a script over SSH."""
        m = self.model
        cmd = ["ssh",
               "-o", "ConnectTimeout=10",
               "-o", "StrictHostKeyChecking=no",
               "-o", "UserKnownHostsFile=/dev/null",
               "-o", "LogLevel=ERROR"]
        if m.ssh_pass:
            cmd = ["sshpass", "-p", m.ssh_pass] + cmd
        cmd += [f"{m.ssh_user}@{m.rpi_ip}", "sudo -S bash -s"]
        sudo_pass = (m.ssh_pass + "\n").encode() if m.ssh_pass else b"\n"
        return cmd, sudo_pass + script_content.encode()

    def _run_cloudflare(self):
        cf_token = self.cf_token_util_edit.text().strip()
        if not cf_token:
            QMessageBox.warning(self, "Missing Token", "Enter Cloudflare token first.")
            return
        try:
            content = self.generator.generate_cloudflare_script(cf_token)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            return

        cmd, stdin_data = self._ssh_cmd("/tmp/cloudflare.sh", content)
        self.cf_terminal.clear()
        runner = ScriptRunner(cmd, stdin_data=stdin_data)
        runner.output_line.connect(lambda l: append_terminal(self.cf_terminal, l))
        runner.finished_signal.connect(lambda c: append_terminal(
            self.cf_terminal, f"\n[{'OK' if c == 0 else 'FAILED'}] exit {c}"))
        self.runners["cf"] = runner
        runner.start()

    def _run_permissions(self):
        perm_script = (self.generator._scripts_dir() / "assign_asterisk_permissions.sh").read_text()
        cmd, stdin_data = self._ssh_cmd("/tmp/perm.sh", perm_script)
        self.perm_terminal.clear()
        runner = ScriptRunner(cmd, stdin_data=stdin_data)
        runner.output_line.connect(lambda l: append_terminal(self.perm_terminal, l))
        runner.finished_signal.connect(lambda c: append_terminal(
            self.perm_terminal, f"\n[{'OK' if c == 0 else 'FAILED'}] exit {c}"))
        self.runners["perm"] = runner
        runner.start()

    def _scan_devices(self):
        self.scan_terminal.clear()
        try:
            result = subprocess.run(
                ["lsblk", "-o", "NAME,SIZE,TYPE,TRAN,MODEL,MOUNTPOINTS"],
                capture_output=True, text=True
            )
            self.scan_terminal.setPlainText(result.stdout)
        except Exception as e:
            self.scan_terminal.setPlainText(f"Error: {e}")


# ─────────────────────────────────────────────
#  Main Window
# ─────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.model = load_config()
        self.generator = ConfigGenerator(self.model)
        self._build_ui()
        self.setWindowTitle("GSM Gateway \u00b7 Host Deployment Manager")
        self.resize(1050, 780)
        self.setMinimumSize(850, 600)

    def _build_ui(self):
        # ── Menu ───────────────────────────────────────
        menu = self.menuBar()
        file_menu = menu.addMenu("File")

        save_act = QAction("Save Config", self)
        save_act.setShortcut("Ctrl+S")
        save_act.triggered.connect(self._save_config)
        file_menu.addAction(save_act)

        load_act = QAction("Load Config", self)
        load_act.setShortcut("Ctrl+O")
        load_act.triggered.connect(self._load_config_dialog)
        file_menu.addAction(load_act)

        file_menu.addSeparator()

        reset_act = QAction("Reset to Script Defaults", self)
        reset_act.triggered.connect(self._reset_defaults)
        file_menu.addAction(reset_act)

        # ── Status bar ─────────────────────────────────
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage(f"Config loaded from {CONFIG_PATH}")

        # ── Central layout: sidebar + stacked pages ────
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Sidebar
        self.sidebar = SidebarWidget()
        self.sidebar.page_changed.connect(self._on_page_changed)
        main_layout.addWidget(self.sidebar)

        # Stacked pages
        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack, 1)

        self.phase1_widget = Phase1Widget(self.model, self.generator)
        self.phase2_widget = Phase2Widget(self.model, self.generator)
        self.preview_widget = ConfigPreviewWidget(self.model, self.generator)
        self.utils_widget = UtilitiesWidget(self.model, self.generator)

        self.stack.addWidget(self.phase1_widget)   # index 0
        self.stack.addWidget(self.phase2_widget)   # index 1
        self.stack.addWidget(self.preview_widget)  # index 2
        self.stack.addWidget(self.utils_widget)    # index 3

        # Wire status signals to sidebar
        self.phase1_widget.flash_completed.connect(
            lambda ok: self.sidebar.update_status(
                "flash", ok, "Flash: Done" if ok else "Flash: Failed"
            )
        )
        self.phase2_widget.ssh_status_changed.connect(
            lambda ok: self.sidebar.update_status(
                "ssh", ok, "SSH: Connected" if ok else "SSH: Failed"
            )
        )

    def _on_page_changed(self, idx: int):
        self.stack.setCurrentIndex(idx)
        self.sidebar.set_active_page(idx)
        if idx == 1:
            self.phase2_widget.refresh_from_model()
        elif idx == 2:
            self.preview_widget.refresh()
        elif idx == 3:
            self.utils_widget.refresh_from_model()

    def show_preview(self, key: str):
        self.stack.setCurrentIndex(2)
        self.sidebar.set_active_page(2)
        self.preview_widget.show_key(key)

    def _save_config(self):
        try:
            save_config(self.model)
            self.status_bar.showMessage(f"Config saved to {CONFIG_PATH}", 3000)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save config:\n{e}")

    def _load_config_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Config", str(CONFIG_PATH.parent), "JSON Files (*.json)"
        )
        if path:
            try:
                data = json.loads(Path(path).read_text())
                for k, v in data.items():
                    if hasattr(self.model, k):
                        setattr(self.model, k, v)
                # Reload all widgets
                self.phase1_widget._load_values()
                self.phase2_widget._load_values()
                self.status_bar.showMessage(f"Config loaded from {path}", 3000)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load config:\n{e}")

    def _reset_defaults(self):
        ret = QMessageBox.question(
            self, "Reset Defaults",
            "Reset all values to those currently in the shell scripts?",
            QMessageBox.Yes | QMessageBox.No
        )
        if ret == QMessageBox.Yes:
            parse_script_defaults(self.model)
            self.phase1_widget._load_values()
            self.phase2_widget._load_values()
            self.status_bar.showMessage("Reset to script defaults.", 3000)

    def closeEvent(self, event):
        save_config(self.model)
        event.accept()


# ─────────────────────────────────────────────
#  Entry Point
# ─────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("GSM Gateway Deployer")
    setup_dark_theme(app)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
