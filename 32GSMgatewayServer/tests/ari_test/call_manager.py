#!/usr/bin/env python3
"""
Bharti AI Call Manager
PyQt5 desktop app — make/receive AI voice calls, view history
"""

import audioop
import json
import os
import re
import shlex
import socket
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import requests as _requests

from PyQt5.QtCore import (
    QIODevice, QProcess, QSize, Qt, QTextStream, QThread, QTimer, pyqtSignal
)
from PyQt5.QtGui import QColor, QFont, QTextCursor
from PyQt5.QtWidgets import (
    QAbstractItemView, QApplication, QDialog, QDialogButtonBox, QFormLayout,
    QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPushButton, QScrollArea, QSizePolicy,
    QStatusBar, QTabWidget, QTableWidget, QTableWidgetItem, QTextEdit,
    QVBoxLayout, QWidget
)

# ─── Config ───────────────────────────────────────────────────────────────────

RPI_HOST      = "pi@192.168.8.59"
RPI_BRIDGE    = "/home/pi/Documents/32GSMgatewayServer/tests/ari_test/rpi_audio_bridge.py"
AI_SERVER     = str(Path(__file__).parent / "ai_server.py")
AI_SERVER_LOG = "/tmp/ai_server.log"
AI_WS_URL     = "ws://192.168.8.7:9090"
ARI_BASE      = "http://192.168.8.59:8088/ari"
ARI_AUTH      = ("ari_user", "ari_pass")
TRUNK         = "1017"
DB_PATH       = str(Path(__file__).parent / "call_history.db")
TASKS_JSON    = str(Path(__file__).parent / "tasks.json")
SARVAM_KEY    = "sk_8mditejo_dzkogXLt9ra7JAZf0ANgvuC1"
SERVER_PORT   = 9090

# ─── Stylesheet ───────────────────────────────────────────────────────────────

QSS = """
* { font-family: 'Segoe UI', 'Ubuntu', 'SF Pro Display', sans-serif; }
QMainWindow { background: #0f1117; }
QWidget { background: transparent; color: #e2e8f0; }

QFrame#sidebar {
    background: #161b27;
    border-right: 1px solid #1e2535;
    min-width: 280px; max-width: 280px;
}
QFrame#main_area { background: #0f1117; }

QFrame#card {
    background: #1a2035;
    border-radius: 14px;
    border: 1px solid #1e2d4a;
}
QFrame#active_card {
    background: #0a2318;
    border-radius: 14px;
    border: 2px solid #22c55e;
}

QLabel { background: transparent; }

QLineEdit#num_input {
    background: #1a2035;
    border: 1px solid #2a3a5a;
    border-radius: 10px;
    color: #f8fafc;
    font-size: 24px;
    font-weight: 700;
    padding: 10px 14px;
    letter-spacing: 2px;
}
QLineEdit#num_input:focus { border-color: #3b82f6; }

QPushButton#pad_btn {
    background: #1e2740;
    color: #e2e8f0;
    border: none;
    border-radius: 30px;
    font-size: 18px;
    font-weight: 600;
    min-width: 58px; min-height: 58px;
    max-width: 58px; max-height: 58px;
}
QPushButton#pad_btn:hover { background: #2d3a5a; }
QPushButton#pad_btn:pressed { background: #3b82f6; color: white; }

QPushButton#call_btn {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #22c55e,stop:1 #16a34a);
    color: white; border: none; border-radius: 34px;
    font-size: 24px;
    min-width: 68px; min-height: 68px;
    max-width: 68px; max-height: 68px;
}
QPushButton#call_btn:hover { background: #4ade80; }
QPushButton#call_btn:pressed { background: #15803d; }
QPushButton#call_btn:disabled { background: #1e3a26; color: #2d6a3f; }

QPushButton#end_btn {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #ef4444,stop:1 #dc2626);
    color: white; border: none; border-radius: 34px;
    font-size: 24px;
    min-width: 68px; min-height: 68px;
    max-width: 68px; max-height: 68px;
}
QPushButton#end_btn:hover { background: #f87171; }
QPushButton#end_btn:pressed { background: #991b1b; }

QPushButton#bs_btn {
    background: #1e2740;
    color: #94a3b8; border: none; border-radius: 22px;
    font-size: 18px;
    min-width: 44px; min-height: 44px;
    max-width: 44px; max-height: 44px;
}
QPushButton#bs_btn:hover { background: #2d3a5a; }

QPushButton#primary_btn {
    background: #1d4ed8; color: white;
    border: none; border-radius: 8px;
    font-size: 12px; font-weight: 600;
    padding: 6px 14px;
}
QPushButton#primary_btn:hover { background: #2563eb; }
QPushButton#primary_btn:checked, QPushButton#primary_btn:pressed { background: #1e40af; }

QPushButton#success_btn {
    background: #14532d; color: #86efac;
    border: none; border-radius: 8px;
    font-size: 12px; font-weight: 600;
    padding: 6px 14px;
}
QPushButton#success_btn:hover { background: #166534; }

QPushButton#danger_btn {
    background: #7f1d1d; color: #fca5a5;
    border: none; border-radius: 8px;
    font-size: 12px; font-weight: 600;
    padding: 6px 14px;
}
QPushButton#danger_btn:hover { background: #991b1b; }

QPushButton#muted_btn {
    background: #1e2535; color: #64748b;
    border: none; border-radius: 8px;
    font-size: 12px; font-weight: 600;
    padding: 6px 14px;
}
QPushButton#muted_btn:hover { background: #2d3a55; }

QTabWidget::pane { border: none; background: transparent; }
QTabBar { background: transparent; }
QTabBar::tab {
    background: transparent; color: #475569;
    padding: 8px 18px; font-size: 12px; font-weight: 600;
    border: none; border-bottom: 2px solid transparent;
}
QTabBar::tab:selected { color: #e2e8f0; border-bottom-color: #3b82f6; }
QTabBar::tab:hover:!selected { color: #94a3b8; }

QTableWidget {
    background: transparent; border: none;
    color: #e2e8f0; gridline-color: transparent;
    font-size: 13px;
}
QTableWidget::item { padding: 10px 8px; border-bottom: 1px solid #1a2035; }
QTableWidget::item:selected { background: #1d3461; color: white; }
QTableWidget::item:hover { background: #1e2a45; }
QHeaderView { background: transparent; }
QHeaderView::section {
    background: #161b27; color: #475569;
    font-size: 10px; font-weight: 700; text-transform: uppercase;
    padding: 8px; border: none;
    border-bottom: 1px solid #1e2535;
}

QTextEdit#log_view {
    background: #090c12;
    color: #34d399;
    border: none; border-radius: 8px;
    font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', 'Courier New', monospace;
    font-size: 11px; padding: 8px;
}

QScrollBar:vertical {
    background: transparent; width: 5px; border: none;
}
QScrollBar::handle:vertical { background: #2d3a5a; border-radius: 2px; min-height: 20px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

QStatusBar { background: #0a0d14; color: #475569; font-size: 11px; }
QStatusBar::item { border: none; }

QDialog { background: #161b27; color: #e2e8f0; }
QLabel#dlg_label { color: #94a3b8; font-size: 12px; font-weight: 600; }
QLineEdit#dialog_input {
    background: #1a2035; border: 1px solid #2a3a5a; border-radius: 8px;
    color: #f8fafc; font-size: 14px; padding: 6px 10px;
}
QLineEdit#dialog_input:focus { border-color: #3b82f6; }
QTextEdit#prompt_edit {
    background: #1a2035; color: #e2e8f0; border: 1px solid #2a3a5a;
    border-radius: 8px; padding: 6px; font-size: 13px;
}
QDialogButtonBox QPushButton {
    background: #1d4ed8; color: white; border: none; border-radius: 8px;
    font-size: 12px; font-weight: 600; padding: 7px 18px; min-width: 70px;
}
QDialogButtonBox QPushButton:hover { background: #2563eb; }
QDialogButtonBox QPushButton[text="Cancel"] { background: #1e2535; color: #64748b; }
QDialogButtonBox QPushButton[text="Cancel"]:hover { background: #2d3a55; }

QLineEdit#chat_input {
    background: #1a2035; border: 1px solid #2a3a5a; border-radius: 10px;
    color: #f8fafc; font-size: 14px; padding: 8px 12px;
}
QLineEdit#chat_input:focus { border-color: #3b82f6; }
"""

# ─── Database ─────────────────────────────────────────────────────────────────

class Database:
    def __init__(self, path):
        self.path = path
        with sqlite3.connect(path) as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    number      TEXT NOT NULL,
                    direction   TEXT NOT NULL,
                    started_at  TEXT NOT NULL,
                    duration    REAL DEFAULT 0,
                    status      TEXT DEFAULT 'unknown'
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    name       TEXT NOT NULL,
                    phone      TEXT NOT NULL,
                    prompt     TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

    def add_call(self, number, direction, started_at):
        with sqlite3.connect(self.path) as c:
            return c.execute(
                "INSERT INTO calls (number,direction,started_at) VALUES (?,?,?)",
                (number, direction, started_at.isoformat())).lastrowid

    def end_call(self, call_id, duration, status):
        with sqlite3.connect(self.path) as c:
            c.execute("UPDATE calls SET duration=?,status=? WHERE id=?",
                      (duration, status, call_id))

    def get_recent(self, limit=100):
        with sqlite3.connect(self.path) as c:
            return c.execute(
                "SELECT id,number,direction,started_at,duration,status "
                "FROM calls ORDER BY id DESC LIMIT ?", (limit,)).fetchall()

    # ── Tasks ──────────────────────────────────────────────────────────────────

    def add_task(self, name, phone, prompt):
        with sqlite3.connect(self.path) as c:
            return c.execute(
                "INSERT INTO tasks (name,phone,prompt,created_at) VALUES (?,?,?,?)",
                (name, phone, prompt, datetime.now().isoformat())).lastrowid

    def get_tasks(self):
        with sqlite3.connect(self.path) as c:
            rows = c.execute(
                "SELECT id,name,phone,prompt,created_at FROM tasks ORDER BY name"
            ).fetchall()
        return [{"id": r[0], "name": r[1], "phone": r[2], "prompt": r[3], "created_at": r[4]}
                for r in rows]

    def update_task(self, task_id, name, phone, prompt):
        with sqlite3.connect(self.path) as c:
            c.execute("UPDATE tasks SET name=?,phone=?,prompt=? WHERE id=?",
                      (name, phone, prompt, task_id))

    def delete_task(self, task_id):
        with sqlite3.connect(self.path) as c:
            c.execute("DELETE FROM tasks WHERE id=?", (task_id,))


# ─── Log Monitor Thread ───────────────────────────────────────────────────────

class LogMonitor(QThread):
    line_added      = pyqtSignal(str)
    rpi_connected   = pyqtSignal()
    call_started    = pyqtSignal(str, str)   # number, mode
    call_ended      = pyqtSignal()
    stt_result      = pyqtSignal(str)
    llm_result      = pyqtSignal(str)
    task_done       = pyqtSignal()           # TASK_COMPLETE detected → auto-hangup done

    def __init__(self, log_path):
        super().__init__()
        self.log_path = log_path
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        # Start at END of file — only process new lines written after app starts
        try:
            with open(self.log_path, 'r', errors='replace') as f:
                f.seek(0, 2)
                pos = f.tell()
        except FileNotFoundError:
            pos = 0

        while not self._stop:
            try:
                with open(self.log_path, 'r', errors='replace') as f:
                    # Handle log truncation (server restart clears file): reset pos
                    f.seek(0, 2)
                    if f.tell() < pos:
                        pos = 0
                    f.seek(pos)
                    chunk = f.read()
                    if chunk:
                        pos = f.tell()
                        for line in chunk.splitlines():
                            if line.strip():
                                self.line_added.emit(line)
                                self._parse(line)
            except FileNotFoundError:
                pos = 0
            time.sleep(0.25)

    def _parse(self, line):
        if 'RPi connected!' in line:
            self.rpi_connected.emit()
        elif 'Call incoming from' in line or 'Call started:' in line:
            m = re.search(r'(\d{7,})', line)
            number = m.group(1) if m else "unknown"
            mode = "incoming" if "incoming" in line else "outbound"
            self.call_started.emit(number, mode)
        elif 'Call ended' in line or 'RPi disconnected' in line:
            self.call_ended.emit()
        elif '[AI] STT' in line:
            m = re.search(r'STT[^"]*"(.+)"', line)
            if m:
                self.stt_result.emit(m.group(1))
        elif '[AI] LLM' in line:
            m = re.search(r'LLM[^"]*"(.+)"', line)
            if m:
                self.llm_result.emit(m.group(1))
        elif 'Task call' in line and 'complete' in line.lower():
            self.task_done.emit()


# ─── Audio Monitor Thread (live-listen) ──────────────────────────────────────

MONITOR_PORT = 9091

class AudioMonitor(QThread):
    """Receives ulaw audio via UDP from ai_server and plays through speakers."""

    def __init__(self):
        super().__init__()
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            import pyaudio
        except ImportError:
            return
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", MONITOR_PORT))
        sock.settimeout(0.5)

        pa = pyaudio.PyAudio()
        stream = pa.open(format=pyaudio.paInt16, channels=1, rate=8000,
                         output=True, frames_per_buffer=1600)
        try:
            while not self._stop:
                try:
                    data, _ = sock.recvfrom(65535)
                    pcm = audioop.ulaw2lin(data, 2)
                    stream.write(pcm)
                except socket.timeout:
                    continue
        finally:
            stream.stop_stream()
            stream.close()
            pa.terminate()
            sock.close()


# ─── Chat Worker ─────────────────────────────────────────────────────────────

class ChatWorker(QThread):
    """Sarvam LLM chat with optional task dispatch. Maintains conversation history."""
    result = pyqtSignal(str, str, object)  # (think_text, reply_text, task_dict_or_None)

    def __init__(self, text, tasks, history):
        super().__init__()
        self.text = text
        self.tasks = tasks
        self.history = history  # list of {"role": "user"/"assistant", "content": "..."}

    def run(self):
        task_section = ""
        if self.tasks:
            task_list = "\n".join(
                f'  {t["id"]}. {t["name"]} → calls {t["phone"]}' for t in self.tasks
            )
            task_section = (
                f"\n\nSaved tasks you can execute by making a phone call:\n{task_list}\n"
                "If the user asks to execute one of these tasks, include the token "
                "EXECUTE_TASK:<id> anywhere in your reply (e.g. 'ठीक है, chai order कर रही हूँ EXECUTE_TASK:1'). "
                "The token is stripped before showing — never say it out loud."
            )

        system = (
            "You are Bharti AI, a friendly and intelligent admin assistant. "
            "Answer questions, have normal conversations, and help with whatever the user needs. "
            "Respond in the same language the user uses (Hindi, English, or mixed). "
            "Keep responses concise. "
            "If you need to reason before replying, put your reasoning inside <think>...</think> tags "
            "at the very start of your response. The thinking is shown separately — keep it brief."
            + task_section
            + ("\n\nIMPORTANT: When the user's message matches a saved task, DO NOT ask for confirmation. "
               "Immediately execute it by including EXECUTE_TASK:<id> in your reply. "
               "Just say something like 'Okay, ordering tea now!' and include the token."
               if self.tasks else "")
        )

        messages = [{"role": "system", "content": system}]
        messages.extend(self.history[-20:])  # last 10 turns
        messages.append({"role": "user", "content": self.text})

        try:
            resp = _requests.post(
                "https://api.sarvam.ai/v1/chat/completions",
                headers={"api-subscription-key": SARVAM_KEY, "Content-Type": "application/json"},
                json={"model": "sarvam-m", "messages": messages,
                      "stream": False, "max_tokens": 200},
                timeout=15,
            )
            if resp.status_code not in (200, 201):
                self.result.emit("", f"API error {resp.status_code}: {resp.text[:150]}", None)
                return
            data = resp.json()
            if "choices" not in data:
                self.result.emit("", f"Unexpected response: {str(data)[:150]}", None)
                return
            content = data["choices"][0]["message"]["content"].strip()

            # Extract EXECUTE_TASK from full content BEFORE stripping think block
            # (model sometimes puts the token inside its <think> reasoning)
            m_task = re.search(r'EXECUTE_TASK:(\d+)', content)
            execute_task_id = int(m_task.group(1)) if m_task else None

            # Extract <think>...</think> block
            think = ""
            m_think = re.search(r'<think>(.*?)</think>', content, re.DOTALL)
            if m_think:
                think = m_think.group(1).strip()
                content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()

            # Strip EXECUTE_TASK token from visible reply
            reply = re.sub(r'EXECUTE_TASK:\d+', '', content).strip()

            matched = next((t for t in self.tasks if t["id"] == execute_task_id), None) \
                      if execute_task_id else None
            self.result.emit(think, reply, matched)

        except Exception as e:
            self.result.emit("", f"Error: {e}", None)


# ─── Task Dialog ──────────────────────────────────────────────────────────────

class TaskDialog(QDialog):
    """Create / edit a task."""

    def __init__(self, parent=None, task=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Task" if task else "New Task")
        self.setMinimumWidth(420)
        self.setStyleSheet(parent.styleSheet() if parent else "")

        form = QFormLayout(self)
        form.setContentsMargins(20, 20, 20, 20)
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignRight)

        self.name_edit = QLineEdit(task["name"] if task else "")
        self.name_edit.setObjectName("dialog_input")
        self.name_edit.setPlaceholderText("e.g. Order Tea")
        form.addRow("Name:", self.name_edit)

        self.phone_edit = QLineEdit(task["phone"] if task else "")
        self.phone_edit.setObjectName("dialog_input")
        self.phone_edit.setPlaceholderText("e.g. 9876543210")
        form.addRow("Phone:", self.phone_edit)

        self.prompt_edit = QTextEdit()
        self.prompt_edit.setObjectName("prompt_edit")
        self.prompt_edit.setMinimumHeight(110)
        self.prompt_edit.setPlaceholderText(
            "Describe what the AI should do on the call.\n"
            "e.g. You are calling to order 2 cutting chai for delivery. "
            "Confirm the order and delivery address.")
        if task:
            self.prompt_edit.setPlainText(task["prompt"])
        form.addRow("AI Prompt:", self.prompt_edit)

        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._validate)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def _validate(self):
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Required", "Task name is required.")
            return
        if not self.phone_edit.text().strip():
            QMessageBox.warning(self, "Required", "Phone number is required.")
            return
        if not self.prompt_edit.toPlainText().strip():
            QMessageBox.warning(self, "Required", "AI prompt is required.")
            return
        self.accept()

    def values(self):
        return (self.name_edit.text().strip(),
                self.phone_edit.text().strip(),
                self.prompt_edit.toPlainText().strip())


# ─── Dial Pad ─────────────────────────────────────────────────────────────────

class DialPad(QWidget):
    digit_pressed = pyqtSignal(str)

    KEYS = [
        ('1',''), ('2','ABC'), ('3','DEF'),
        ('4','GHI'), ('5','JKL'), ('6','MNO'),
        ('7','PQRS'), ('8','TUV'), ('9','WXYZ'),
        ('*',''), ('0','+'), ('#',''),
    ]

    def __init__(self):
        super().__init__()
        grid = QGridLayout(self)
        grid.setSpacing(10)
        grid.setContentsMargins(0, 0, 0, 0)
        for i, (digit, sub) in enumerate(self.KEYS):
            btn = QPushButton()
            btn.setObjectName("pad_btn")
            layout = QVBoxLayout(btn)
            layout.setContentsMargins(0, 4, 0, 4)
            layout.setSpacing(0)
            d = QLabel(digit)
            d.setAlignment(Qt.AlignCenter)
            d.setStyleSheet("font-size: 18px; font-weight: 700; color: #e2e8f0;")
            layout.addWidget(d)
            if sub:
                s = QLabel(sub)
                s.setAlignment(Qt.AlignCenter)
                s.setStyleSheet("font-size: 7px; color: #475569; letter-spacing: 1px;")
                layout.addWidget(s)
            btn.clicked.connect(lambda _, d=digit: self.digit_pressed.emit(d))
            grid.addWidget(btn, i // 3, i % 3)


# ─── Active Call Card ─────────────────────────────────────────────────────────

class ActiveCallCard(QFrame):
    hangup_clicked = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setObjectName("active_card")
        self._elapsed = 0
        self._timer = QTimer()
        self._timer.timeout.connect(self._tick)
        self._build()
        self.hide()

    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(8)

        # Top row: indicator + status + number + duration
        top = QHBoxLayout()
        pulse = QLabel("●")
        pulse.setStyleSheet("color: #22c55e; font-size: 10px;")
        top.addWidget(pulse)
        self.status_lbl = QLabel("Active Call")
        self.status_lbl.setStyleSheet("font-size: 12px; color: #22c55e; font-weight: 600;")
        top.addWidget(self.status_lbl)
        top.addSpacing(12)
        self.num_lbl = QLabel("—")
        self.num_lbl.setStyleSheet("font-size: 15px; font-weight: 800; color: #f1f5f9;")
        top.addWidget(self.num_lbl)
        top.addStretch()
        self.dur_lbl = QLabel("0:00")
        self.dur_lbl.setStyleSheet("font-size: 13px; color: #64748b; font-weight: 600;")
        top.addWidget(self.dur_lbl)
        # Listen button
        self.listen_btn = QPushButton("🔊 Listen")
        self.listen_btn.setFixedHeight(30)
        self.listen_btn.setCheckable(True)
        self.listen_btn.setStyleSheet(
            "QPushButton{background:#1e3a5f;color:#93c5fd;border:1px solid #2d4a6a;"
            "border-radius:6px;padding:0 12px;font-size:11px;font-weight:600;}"
            "QPushButton:checked{background:#166534;color:#86efac;border-color:#22c55e;}"
            "QPushButton:hover{background:#1e4070;}")
        self.listen_btn.toggled.connect(self._on_listen_toggled)
        top.addWidget(self.listen_btn)
        top.addSpacing(6)
        # End call button inline
        end = QPushButton("End Call")
        end.setObjectName("danger_btn")
        end.setFixedHeight(30)
        end.clicked.connect(self.hangup_clicked.emit)
        top.addSpacing(10)
        top.addWidget(end)
        v.addLayout(top)

        # Scrollable chat transcript
        self.chat = QTextEdit()
        self.chat.setReadOnly(True)
        self.chat.setMinimumHeight(160)
        self.chat.setStyleSheet(
            "QTextEdit {"
            "  background: #080d18;"
            "  border: 1px solid #1e2d4a;"
            "  border-radius: 10px;"
            "  padding: 6px;"
            "  font-size: 13px;"
            "}"
            "QScrollBar:vertical { background: transparent; width: 5px; border: none; }"
            "QScrollBar::handle:vertical { background: #2d3a5a; border-radius: 2px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )
        v.addWidget(self.chat)

    def _on_listen_toggled(self, checked):
        if checked:
            self.listen_btn.setText("🔊 Listening")
            self._audio_mon = AudioMonitor()
            self._audio_mon.start()
        else:
            self.listen_btn.setText("🔊 Listen")
            if hasattr(self, '_audio_mon') and self._audio_mon:
                self._audio_mon.stop()
                self._audio_mon.wait(2000)
                self._audio_mon = None

    def start(self, number, direction):
        self.num_lbl.setText(number)
        self.status_lbl.setText("⬆ Outbound" if direction == "outbound" else "⬇ Incoming")
        self.chat.clear()
        self._elapsed = 0
        self._timer.start(1000)
        self.listen_btn.setChecked(False)
        self.show()

    def stop(self):
        self._timer.stop()
        self.listen_btn.setChecked(False)
        self.hide()

    def _tick(self):
        self._elapsed += 1
        m, s = divmod(self._elapsed, 60)
        self.dur_lbl.setText(f"{m}:{s:02d}")

    def set_transcript(self, text):
        """User speech — right side, blue bubble."""
        ts = datetime.now().strftime("%H:%M:%S")
        self.chat.append(
            f'<table width="100%" cellpadding="0" cellspacing="0">'
            f'<tr><td width="25%"></td>'
            f'<td align="right">'
            f'<div style="background:#1e3a5f; color:#93c5fd; padding:7px 12px; '
            f'border-radius:14px 14px 2px 14px; font-size:12px; display:inline-block;">'
            f'🎤 &nbsp;{text}</div>'
            f'<div style="color:#334155; font-size:10px; text-align:right; margin-top:2px;">{ts}</div>'
            f'</td></tr></table>'
        )
        self._scroll_bottom()

    def set_reply(self, text):
        """AI reply — left side, green bubble."""
        self.chat.append(
            f'<table width="100%" cellpadding="0" cellspacing="0">'
            f'<tr><td align="left">'
            f'<div style="background:#0a2318; color:#86efac; padding:7px 12px; '
            f'border-radius:14px 14px 14px 2px; font-size:12px; display:inline-block;">'
            f'🤖 &nbsp;{text}</div>'
            f'</td><td width="25%"></td></tr></table>'
        )
        self._scroll_bottom()

    def _scroll_bottom(self):
        sb = self.chat.verticalScrollBar()
        sb.setValue(sb.maximum())


# ─── Main Window ──────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bharti AI — Call Manager")
        self.resize(1120, 680)
        self.setMinimumSize(900, 600)

        self.db              = Database(DB_PATH)
        self.server_proc     = None     # QProcess for ai_server.py
        self.bridge_proc     = None     # subprocess.Popen (SSH) for RPi bridge
        self.call_id         = None
        self.call_start_time = None
        self.call_number     = None
        self.call_direction  = None
        self.incoming_mode   = False
        self._chat_worker    = None
        self._chat_history   = []   # [{"role": "user"/"assistant", "content": "..."}]

        self._build()
        self._refresh_history()
        self._refresh_tasks()
        self._write_tasks_json()
        self._start_log_monitor()

        # Periodic server liveness check
        self._health_timer = QTimer()
        self._health_timer.timeout.connect(self._check_server_health)
        self._health_timer.start(4000)
        self._check_server_health()

    # ─── UI Build ─────────────────────────────────────────────────────────────

    def _build(self):
        self.setStyleSheet(QSS)
        root_widget = QWidget()
        self.setCentralWidget(root_widget)
        root = QHBoxLayout(root_widget)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Status bar
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Ready")

        # ── Sidebar ───────────────────────────────────────────────────────────
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sv = QVBoxLayout(sidebar)
        sv.setContentsMargins(20, 24, 20, 20)
        sv.setSpacing(0)

        # Brand
        brand = QLabel("Bharti AI")
        brand.setStyleSheet("font-size: 20px; font-weight: 800; color: #f1f5f9;")
        sv.addWidget(brand)
        sv.addWidget(self._label("Call Manager", "font-size: 11px; color: #334155;"))
        sv.addSpacing(20)
        sv.addWidget(self._sep())
        sv.addSpacing(16)

        # Server row
        srv_row = QHBoxLayout()
        self.srv_dot = QLabel("●")
        self.srv_dot.setStyleSheet("color: #ef4444; font-size: 12px;")
        srv_row.addWidget(self.srv_dot)
        srv_row.addWidget(self._label("AI Server", "font-size: 13px; color: #94a3b8;"))
        srv_row.addStretch()
        self.srv_btn = QPushButton("Start")
        self.srv_btn.setObjectName("primary_btn")
        self.srv_btn.setFixedWidth(58)
        self.srv_btn.clicked.connect(self._toggle_server)
        srv_row.addWidget(self.srv_btn)
        sv.addLayout(srv_row)
        sv.addSpacing(10)

        # RPi row
        rpi_row = QHBoxLayout()
        self.rpi_dot = QLabel("●")
        self.rpi_dot.setStyleSheet("color: #ef4444; font-size: 12px;")
        rpi_row.addWidget(self.rpi_dot)
        rpi_row.addWidget(self._label("RPi Bridge", "font-size: 13px; color: #94a3b8;"))
        rpi_row.addStretch()
        self.inc_btn = QPushButton("Incoming")
        self.inc_btn.setObjectName("muted_btn")
        self.inc_btn.setFixedWidth(76)
        self.inc_btn.setToolTip("Start in incoming mode — accept calls from any SIM")
        self.inc_btn.clicked.connect(self._toggle_incoming)
        rpi_row.addWidget(self.inc_btn)
        sv.addLayout(rpi_row)
        sv.addSpacing(16)
        sv.addWidget(self._sep())
        sv.addSpacing(16)

        # Number input
        self.num_input = QLineEdit()
        self.num_input.setObjectName("num_input")
        self.num_input.setPlaceholderText("Enter number…")
        self.num_input.returnPressed.connect(self._make_call)
        sv.addWidget(self.num_input)
        sv.addSpacing(12)

        # Dial pad
        pad = DialPad()
        pad.digit_pressed.connect(lambda d: (
            self.num_input.setText(self.num_input.text() + d)))
        sv.addWidget(pad)
        sv.addSpacing(14)

        # Action row: backspace | call | end
        act = QHBoxLayout()
        act.addStretch()
        bs = QPushButton("⌫")
        bs.setObjectName("bs_btn")
        bs.clicked.connect(lambda: self.num_input.setText(self.num_input.text()[:-1]))
        act.addWidget(bs)
        act.addSpacing(10)
        self.call_btn = QPushButton("📞")
        self.call_btn.setObjectName("call_btn")
        self.call_btn.clicked.connect(self._make_call)
        act.addWidget(self.call_btn)
        self.end_btn = QPushButton("📵")
        self.end_btn.setObjectName("end_btn")
        self.end_btn.clicked.connect(self._hangup)
        self.end_btn.hide()
        act.addWidget(self.end_btn)
        act.addStretch()
        sv.addLayout(act)
        sv.addStretch()

        root.addWidget(sidebar)

        # ── Main area ─────────────────────────────────────────────────────────
        main = QFrame()
        main.setObjectName("main_area")
        mv = QVBoxLayout(main)
        mv.setContentsMargins(24, 24, 24, 24)
        mv.setSpacing(16)

        # Active call card
        self.active_card = ActiveCallCard()
        self.active_card.hangup_clicked.connect(self._hangup)
        mv.addWidget(self.active_card)

        # Tabs
        tabs = QTabWidget()
        tabs.setDocumentMode(True)

        # History tab
        hist_w = QWidget()
        hv = QVBoxLayout(hist_w)
        hv.setContentsMargins(0, 8, 0, 0)
        self.history = QTableWidget()
        self.history.setColumnCount(6)
        self.history.setHorizontalHeaderLabels(["Number", "Dir", "Date / Time", "Duration", "Status", ""])
        h = self.history.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, 5):
            h.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(5, QHeaderView.Fixed)
        self.history.setColumnWidth(5, 68)
        self.history.verticalHeader().hide()
        self.history.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.history.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.history.setShowGrid(False)
        self.history.setAlternatingRowColors(True)
        self.history.setStyleSheet("QTableWidget { alternate-background-color: #141928; }")
        self.history.doubleClicked.connect(self._call_from_history)
        hv.addWidget(self.history)
        tabs.addTab(hist_w, "  Call History  ")

        # Log tab
        self.log_view = QTextEdit()
        self.log_view.setObjectName("log_view")
        self.log_view.setReadOnly(True)
        tabs.addTab(self.log_view, "  Live Log  ")

        # Tasks tab
        tabs.addTab(self._build_tasks_tab(), "  Tasks  ")

        # Chat tab
        tabs.addTab(self._build_chat_tab(), "  Chat  ")

        mv.addWidget(tabs)
        root.addWidget(main)

    # ─── Tasks tab ────────────────────────────────────────────────────────────

    def _build_tasks_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 8, 0, 0)
        v.setSpacing(8)

        # Header row
        hdr = QHBoxLayout()
        hdr.addWidget(self._label("Saved Tasks", "font-size: 13px; font-weight: 700; color: #94a3b8;"))
        hdr.addStretch()
        new_btn = QPushButton("+ New Task")
        new_btn.setObjectName("primary_btn")
        new_btn.clicked.connect(self._new_task)
        hdr.addWidget(new_btn)
        v.addLayout(hdr)

        self.tasks_table = QTableWidget()
        self.tasks_table.setColumnCount(5)
        self.tasks_table.setHorizontalHeaderLabels(["Name", "Phone", "Prompt", "", ""])
        h = self.tasks_table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.Stretch)
        h.setSectionResizeMode(3, QHeaderView.Fixed)
        h.setSectionResizeMode(4, QHeaderView.Fixed)
        self.tasks_table.setColumnWidth(3, 90)
        self.tasks_table.setColumnWidth(4, 70)
        self.tasks_table.verticalHeader().hide()
        self.tasks_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tasks_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tasks_table.setShowGrid(False)
        self.tasks_table.setAlternatingRowColors(True)
        self.tasks_table.setStyleSheet("QTableWidget { alternate-background-color: #141928; }")
        v.addWidget(self.tasks_table)
        return w

    def _refresh_tasks(self):
        tasks = self.db.get_tasks()
        self.tasks_table.setRowCount(len(tasks))
        for r, task in enumerate(tasks):
            prompt_preview = task["prompt"][:60] + "…" if len(task["prompt"]) > 60 else task["prompt"]
            for col, (text, color) in enumerate([
                (task["name"],  "#f1f5f9"),
                (task["phone"], "#94a3b8"),
                (prompt_preview, "#475569"),
            ]):
                item = QTableWidgetItem(text)
                item.setForeground(QColor(color))
                self.tasks_table.setItem(r, col, item)

            # Run button
            run_btn = QPushButton("▶ Run")
            run_btn.setStyleSheet(
                "QPushButton{background:#14532d;color:#86efac;border:none;border-radius:6px;"
                "font-size:11px;font-weight:600;padding:4px 8px;}"
                "QPushButton:hover{background:#166534;}")
            run_btn.clicked.connect(lambda _, t=task: self._run_task(t))
            cell_r = QWidget(); lay_r = QHBoxLayout(cell_r)
            lay_r.setContentsMargins(4, 3, 4, 3); lay_r.addWidget(run_btn)
            self.tasks_table.setCellWidget(r, 3, cell_r)

            # Edit + Delete in one cell
            ed_btn = QPushButton("✎")
            ed_btn.setFixedSize(28, 28)
            ed_btn.setStyleSheet("QPushButton{background:#1d4ed8;color:white;border:none;border-radius:6px;font-size:13px;}"
                                 "QPushButton:hover{background:#2563eb;}")
            ed_btn.clicked.connect(lambda _, t=task: self._edit_task(t))
            del_btn = QPushButton("✕")
            del_btn.setFixedSize(28, 28)
            del_btn.setStyleSheet("QPushButton{background:#7f1d1d;color:#fca5a5;border:none;border-radius:6px;font-size:13px;}"
                                  "QPushButton:hover{background:#991b1b;}")
            del_btn.clicked.connect(lambda _, t=task: self._delete_task(t))
            cell_ed = QWidget(); lay_ed = QHBoxLayout(cell_ed)
            lay_ed.setContentsMargins(2, 2, 2, 2); lay_ed.setSpacing(4)
            lay_ed.addWidget(ed_btn); lay_ed.addWidget(del_btn)
            self.tasks_table.setCellWidget(r, 4, cell_ed)
            self.tasks_table.setRowHeight(r, 42)

    def _new_task(self):
        dlg = TaskDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            name, phone, prompt = dlg.values()
            self.db.add_task(name, phone, prompt)
            self._refresh_tasks()
            self._write_tasks_json()

    def _edit_task(self, task):
        dlg = TaskDialog(self, task)
        if dlg.exec_() == QDialog.Accepted:
            name, phone, prompt = dlg.values()
            self.db.update_task(task["id"], name, phone, prompt)
            self._refresh_tasks()
            self._write_tasks_json()

    def _delete_task(self, task):
        if QMessageBox.question(self, "Delete Task",
                                f'Delete task "{task["name"]}"?',
                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.db.delete_task(task["id"])
            self._refresh_tasks()
            self._write_tasks_json()

    def _write_tasks_json(self):
        try:
            with open(TASKS_JSON, 'w', encoding='utf-8') as f:
                json.dump({"tasks": self.db.get_tasks()}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ─── Chat tab ─────────────────────────────────────────────────────────────

    def _build_chat_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 8, 0, 0)
        v.setSpacing(8)

        lbl = self._label("Admin Chat  —  type a command to execute a task",
                          "font-size: 11px; color: #334155;")
        v.addWidget(lbl)

        self.chat_view = QTextEdit()
        self.chat_view.setReadOnly(True)
        self.chat_view.setStyleSheet(
            "QTextEdit{background:#080d18;border:1px solid #1e2d4a;border-radius:10px;"
            "padding:6px;font-size:13px;}"
            "QScrollBar:vertical{background:transparent;width:5px;border:none;}"
            "QScrollBar::handle:vertical{background:#2d3a5a;border-radius:2px;}"
            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}")
        v.addWidget(self.chat_view)

        # Thinking indicator
        self._thinking_label = QLabel("")
        self._thinking_label.setStyleSheet(
            "color:#64748b; font-size:11px; font-style:italic; padding:2px 8px;")
        self._thinking_label.hide()
        v.addWidget(self._thinking_label)
        self._thinking_dots = 0
        self._thinking_timer = QTimer()
        self._thinking_timer.timeout.connect(self._animate_thinking)

        # Input row
        inp_row = QHBoxLayout()
        self.chat_input = QLineEdit()
        self.chat_input.setObjectName("chat_input")
        self.chat_input.setPlaceholderText("Type a command… e.g. order 2 coffee, chai mangao")
        self.chat_input.returnPressed.connect(self._send_chat)
        inp_row.addWidget(self.chat_input)
        send_btn = QPushButton("Send")
        send_btn.setObjectName("primary_btn")
        send_btn.setFixedWidth(64)
        send_btn.clicked.connect(self._send_chat)
        inp_row.addWidget(send_btn)
        v.addLayout(inp_row)
        return w

    def _send_chat(self):
        text = self.chat_input.text().strip()
        if not text:
            return
        self.chat_input.clear()
        self.chat_input.setEnabled(False)
        self._chat_bubble_user(text)
        tasks = self.db.get_tasks()
        self._chat_worker = ChatWorker(text, tasks, list(self._chat_history))
        self._chat_history.append({"role": "user", "content": text})
        self._chat_worker.result.connect(self._on_chat_result)
        self._chat_worker.start()
        self._thinking_dots = 0
        self._thinking_label.setText("🤖 Thinking")
        self._thinking_label.show()
        self._thinking_timer.start(400)

    def _on_chat_result(self, think, reply, task):
        self._thinking_timer.stop()
        self._thinking_label.hide()
        self.chat_input.setEnabled(True)
        self.chat_input.setFocus()
        if think:
            self._chat_bubble_think(think)
        if reply:
            self._chat_bubble_ai(reply)
            self._chat_history.append({"role": "assistant", "content": reply})
        if task:
            self._chat_bubble_system(f"Running task: {task['name']} → {task['phone']}")
            self._run_task(task)

    def _run_task(self, task):
        self._ensure_server_then(lambda: self._launch_task_call(task))

    def _launch_task_call(self, task):
        if self.call_id is not None:
            return  # don't interrupt an active call
        endpoint = f"PJSIP/{task['phone']}@{TRUNK}"
        full_prompt = (
            # OPENING: line is extracted by ai_server for direct TTS (purpose, said after greeting)
            f"OPENING: मुझे {task['name']} करना था।\n\n"
            # Clear first-person caller perspective
            "You are Bharti AI. You have CALLED this person — you are the CALLER, they are receiving your call. "
            "Speak as a customer or person placing a request (first person). "
            "Say 'mujhe X chahiye' not 'aapne X order kiya'. "
            "Do not reveal you are an AI.\n\n"
            f"Task: {task['prompt']}\n\n"
            "When the task is successfully completed (order confirmed, info received, etc.), "
            "append the exact token TASK_COMPLETE to your final response. "
            "Do not say TASK_COMPLETE out loud."
        )
        ssh_cmd = (
            f"python3 -u {RPI_BRIDGE} --mode outbound "
            f"--endpoint {shlex.quote(endpoint)} "
            f"--server {AI_WS_URL} "
            f"--task-prompt {shlex.quote(full_prompt)}"
        )
        try:
            self._stop_bridge()
            self.bridge_proc = subprocess.Popen(
                ["ssh", RPI_HOST, ssh_cmd],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._register_call_start(task["phone"], "outbound")
            self._status_bar.showMessage(f"Task: {task['name']} → {task['phone']}")
        except Exception as e:
            self._chat_bubble_system(f"SSH error: {e}")

    def _chat_bubble_user(self, text):
        self.chat_view.append(
            f'<table width="100%" cellpadding="0" cellspacing="0">'
            f'<tr><td width="20%"></td>'
            f'<td align="right">'
            f'<div style="background:#1e3a5f;color:#93c5fd;padding:7px 12px;'
            f'border-radius:14px 14px 2px 14px;font-size:12px;display:inline-block;">'
            f'👤 &nbsp;{text}</div></td></tr></table>')
        self._chat_scroll()

    def _chat_bubble_ai(self, text):
        self.chat_view.append(
            f'<table width="100%" cellpadding="0" cellspacing="0">'
            f'<tr><td align="left">'
            f'<div style="background:#1a2035;color:#e2e8f0;padding:7px 12px;'
            f'border-radius:14px 14px 14px 2px;font-size:12px;display:inline-block;">'
            f'🤖 &nbsp;{text}</div>'
            f'</td><td width="20%"></td></tr></table>')
        self._chat_scroll()

    def _chat_bubble_think(self, text):
        self.chat_view.append(
            f'<table width="100%" cellpadding="0" cellspacing="0">'
            f'<tr><td align="left">'
            f'<div style="background:#0f1729;color:#64748b;padding:5px 10px;'
            f'border-radius:8px;font-size:11px;font-style:italic;'
            f'border-left:2px solid #2a3a5a;margin-bottom:2px;">'
            f'💭 &nbsp;{text}</div>'
            f'</td><td width="30%"></td></tr></table>')
        self._chat_scroll()

    def _chat_bubble_system(self, text):
        self.chat_view.append(
            f'<div style="text-align:center;color:#475569;font-size:11px;'
            f'padding:4px 0;">{text}</div>')
        self._chat_scroll()

    def _animate_thinking(self):
        self._thinking_dots = (self._thinking_dots % 3) + 1
        self._thinking_label.setText("🤖 Thinking" + "." * self._thinking_dots)

    def _chat_scroll(self):
        sb = self.chat_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ─── Helper builders ──────────────────────────────────────────────────────

    @staticmethod
    def _label(text, style=""):
        lbl = QLabel(text)
        if style:
            lbl.setStyleSheet(style)
        return lbl

    @staticmethod
    def _sep():
        f = QFrame()
        f.setFrameShape(QFrame.HLine)
        f.setStyleSheet("background: #1e2535; max-height: 1px; min-height: 1px;")
        return f

    # ─── Server management ────────────────────────────────────────────────────

    def _toggle_server(self):
        if self.server_proc and self.server_proc.state() == QProcess.Running:
            self.server_proc.terminate()
        else:
            self._start_server()

    def _start_server(self):
        # Clear old log
        try:
            open(AI_SERVER_LOG, 'w').close()
        except Exception:
            pass
        if self.server_proc:
            self.server_proc.kill()
        self.server_proc = QProcess()
        self.server_proc.setStandardOutputFile(AI_SERVER_LOG)
        self.server_proc.setStandardErrorFile(AI_SERVER_LOG)
        self.server_proc.started.connect(lambda: self._set_server_ui(True))
        self.server_proc.finished.connect(lambda: self._set_server_ui(False))
        self.server_proc.start(sys.executable, ["-u", AI_SERVER])

    def _set_server_ui(self, running):
        if running:
            self.srv_dot.setStyleSheet("color: #22c55e; font-size: 12px;")
            self.srv_btn.setText("Stop")
            self._status_bar.showMessage("AI Server running")
        else:
            self.srv_dot.setStyleSheet("color: #ef4444; font-size: 12px;")
            self.srv_btn.setText("Start")
            self._status_bar.showMessage("AI Server stopped")

    def _check_server_health(self):
        """Check if port 9090 is listening — without connecting (avoids WS errors)."""
        if self.server_proc and self.server_proc.state() == QProcess.Running:
            self._set_server_ui(True)
            return
        try:
            result = subprocess.run(
                ["ss", "-tlnH"],
                capture_output=True, text=True, timeout=1)
            alive = f":{SERVER_PORT}" in result.stdout
        except Exception:
            alive = False
        dot_color = "#22c55e" if alive else "#ef4444"
        self.srv_dot.setStyleSheet(f"color: {dot_color}; font-size: 12px;")
        if alive and self.srv_btn.text() == "Start":
            self.srv_btn.setText("Stop")

    # ─── Bridge management ────────────────────────────────────────────────────

    def _toggle_incoming(self):
        if self.incoming_mode:
            self._stop_bridge()
            self.incoming_mode = False
            self.inc_btn.setText("Incoming")
            self.inc_btn.setObjectName("muted_btn")
            self.inc_btn.setStyleSheet("")
        else:
            self._ensure_server_then(self._start_incoming)

    def _start_incoming(self):
        self._stop_bridge()
        cmd = ["ssh", RPI_HOST,
               f"python3 -u {RPI_BRIDGE} --mode incoming --server {AI_WS_URL}"]
        try:
            self.bridge_proc = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.incoming_mode = True
            self.rpi_dot.setStyleSheet("color: #fbbf24; font-size: 12px;")
            self.inc_btn.setText("Stop")
            self.inc_btn.setObjectName("danger_btn")
            self.inc_btn.setStyleSheet(
                "background:#7f1d1d;color:#fca5a5;border:none;border-radius:8px;"
                "font-size:12px;font-weight:600;padding:6px 14px;")
            self._status_bar.showMessage("Incoming mode — waiting for calls")
        except Exception as e:
            self._alert(f"SSH failed:\n{e}")

    def _start_outbound_bridge(self, number):
        self._stop_bridge()
        endpoint = f"PJSIP/{number}@{TRUNK}"
        cmd = ["ssh", RPI_HOST,
               f"python3 -u {RPI_BRIDGE} --mode outbound "
               f"--endpoint {endpoint} --server {AI_WS_URL}"]
        try:
            self.bridge_proc = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception as e:
            self._alert(f"SSH failed:\n{e}")
            return False

    def _stop_bridge(self):
        if self.bridge_proc and self.bridge_proc.poll() is None:
            self.bridge_proc.terminate()
        self.bridge_proc = None
        self.rpi_dot.setStyleSheet("color: #ef4444; font-size: 12px;")

    # ─── Call actions ─────────────────────────────────────────────────────────

    def _make_call(self):
        number = self.num_input.text().strip()
        if not number or self.call_id is not None:
            return
        self._ensure_server_then(lambda: self._launch_call(number))

    def _launch_call(self, number):
        if not self._start_outbound_bridge(number):
            return
        self._register_call_start(number, "outbound")

    def _register_call_start(self, number, direction):
        now = datetime.now()
        self.call_start_time = now
        self.call_number = number
        self.call_direction = direction
        self.call_id = self.db.add_call(number, direction, now)
        self.active_card.start(number, direction)
        self.call_btn.hide()
        self.end_btn.show()
        self.incoming_mode = False
        self._refresh_history()
        self._status_bar.showMessage(f"{'Incoming' if direction == 'incoming' else 'Calling'}: {number}")

    def _hangup(self):
        self._stop_bridge()
        # ARI REST hangup — delete all non-RTP channels
        try:
            import requests as req
            channels = req.get(f"{ARI_BASE}/channels", auth=ARI_AUTH, timeout=3).json()
            for ch in channels:
                if "UnicastRTP" not in ch.get("name", ""):
                    req.delete(f"{ARI_BASE}/channels/{ch['id']}", auth=ARI_AUTH, timeout=3)
        except Exception:
            pass
        self._finish_call("completed")

    def _finish_call(self, status="completed"):
        if self.call_id is not None:
            dur = (datetime.now() - self.call_start_time).total_seconds() \
                  if self.call_start_time else 0
            self.db.end_call(self.call_id, dur, status)
            self.call_id = None
            self.call_start_time = None
            self.call_number = None
            self.call_direction = None
        self.active_card.stop()
        self.call_btn.show()
        self.end_btn.hide()
        self._refresh_history()
        self._status_bar.showMessage("Ready")

    # ─── Log Monitor ─────────────────────────────────────────────────────────

    def _start_log_monitor(self):
        self._monitor = LogMonitor(AI_SERVER_LOG)
        self._monitor.line_added.connect(self._on_log_line)
        self._monitor.rpi_connected.connect(self._on_rpi_connected)
        self._monitor.call_started.connect(self._on_call_started)
        self._monitor.call_ended.connect(self._on_call_ended)
        self._monitor.stt_result.connect(self.active_card.set_transcript)
        self._monitor.llm_result.connect(self.active_card.set_reply)
        self._monitor.task_done.connect(self._on_task_done)
        self._monitor.start()

    def _on_log_line(self, line):
        # Colorize by log level
        if 'ERROR' in line or 'error' in line.lower():
            color = "#f87171"
        elif 'WARNING' in line or 'warning' in line.lower():
            color = "#fbbf24"
        elif '[AI]' in line:
            color = "#34d399"
        else:
            color = "#4b5563"
        self.log_view.append(f'<span style="color:{color};">{line}</span>')
        c = self.log_view.textCursor()
        c.movePosition(QTextCursor.End)
        self.log_view.setTextCursor(c)

    def _on_rpi_connected(self):
        self.rpi_dot.setStyleSheet("color: #22c55e; font-size: 12px;")
        self._status_bar.showMessage("RPi Bridge connected")

    def _on_call_started(self, number, mode):
        if self.call_id is not None:
            return  # already tracking (outbound)
        # Incoming call detected via log
        self._register_call_start(number, mode)

    def _on_call_ended(self):
        if self.call_id is not None:
            self._finish_call("completed")

    def _on_task_done(self):
        self._chat_bubble_system("Task completed ✓")

    # ─── History ─────────────────────────────────────────────────────────────

    def _refresh_history(self):
        rows = self.db.get_recent(100)
        self.history.setRowCount(len(rows))
        for r, (_, number, direction, started_at, duration, status) in enumerate(rows):
            try:
                dt = datetime.fromisoformat(started_at)
                date_str = dt.strftime("%d %b %Y  %H:%M")
            except Exception:
                date_str = started_at

            dur_str = "—"
            if duration and duration > 0:
                m, s = divmod(int(duration), 60)
                dur_str = f"{m}m {s:02d}s"

            dir_str = "⬆ Out" if direction == "outbound" else "⬇ In"
            status_color = "#22c55e" if status == "completed" else (
                "#fbbf24" if status == "unknown" else "#ef4444")

            for col, (text, color) in enumerate([
                (number,              "#f1f5f9"),
                (dir_str,             "#64748b"),
                (date_str,            "#475569"),
                (dur_str,             "#94a3b8"),
                (status.capitalize(), status_color),
            ]):
                item = QTableWidgetItem(text)
                item.setForeground(QColor(color))
                self.history.setItem(r, col, item)

            # Call button
            call_btn = QPushButton("📞")
            call_btn.setFixedSize(36, 36)
            call_btn.setStyleSheet(
                "QPushButton { background: #14532d; color: #86efac; border: none; "
                "border-radius: 8px; font-size: 14px; }"
                "QPushButton:hover { background: #166534; }"
                "QPushButton:pressed { background: #22c55e; color: white; }")
            call_btn.clicked.connect(lambda _, n=number: self._call_number(n))
            cell = QWidget()
            lay = QHBoxLayout(cell)
            lay.setContentsMargins(4, 4, 4, 4)
            lay.addWidget(call_btn)
            self.history.setCellWidget(r, 5, cell)
            self.history.setRowHeight(r, 44)

    def _call_from_history(self, idx):
        item = self.history.item(idx.row(), 0)
        if item:
            self._call_number(item.text())

    def _call_number(self, number):
        self.num_input.setText(number)
        self._make_call()

    # ─── Helpers ─────────────────────────────────────────────────────────────

    def _ensure_server_then(self, callback):
        """Start server if not running, then call callback."""
        try:
            result = subprocess.run(
                ["ss", "-tlnH"], capture_output=True, text=True, timeout=1)
            alive = f":{SERVER_PORT}" in result.stdout
        except Exception:
            alive = False
        if alive or (self.server_proc and self.server_proc.state() == QProcess.Running):
            callback()
        else:
            self._start_server()
            QTimer.singleShot(2500, callback)

    def _alert(self, msg):
        QMessageBox.critical(self, "Error", msg)

    def closeEvent(self, event):
        if self._monitor:
            self._monitor.stop()
        if self.server_proc:
            self.server_proc.terminate()
        self._stop_bridge()
        event.accept()


# ─── Entry point ─────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Bharti AI")
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
