# Deploy Manager UI/UX Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform `HostTemplates/deploy_manager.py` into a modern dark-themed app with GitHub Dark palette, collapsible sidebar navigation, and a step-progress wizard for Phase 2 execution.

**Architecture:** Single-file PyQt5 app — add `DARK_STYLESHEET` constant + `setup_dark_theme()` for theming; add `SidebarWidget` + `StepWizardWidget` + `make_page_header()` as new components; replace `QTabWidget` in `MainWindow` with sidebar + `QStackedWidget`; update all existing widgets with spacing, button `objectName`s, and page headers. Zero logic changes — all config generation, SSH, and script-running code stays exactly the same.

**Tech Stack:** PyQt5 — `QPropertyAnimation`, `QEasingCurve`, `QPalette`, QSS, `QStackedWidget`, `QButtonGroup`, `pyqtSignal`

---

## File Map

| Action | Path | Responsibility |
|--------|------|---------------|
| Modify | `HostTemplates/deploy_manager.py` | All changes — theme, new classes, layout restructure |

All new classes (`SidebarWidget`, `StepWizardWidget`) live in the same file to preserve the single-file architecture.

---

### Task 1: Update imports, add DARK_STYLESHEET constant and setup_dark_theme()

**Files:**
- Modify: `HostTemplates/deploy_manager.py` — imports block (lines 17–27) and after PHASE2_STEPS (after line 42)

- [ ] **Step 1: Update PyQt5 imports to add QStackedWidget and QPropertyAnimation/QEasingCurve**

In `deploy_manager.py`, replace the imports block (lines 17–27):

```python
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QFormLayout, QGroupBox, QLineEdit, QSpinBox, QComboBox, QPlainTextEdit,
    QPushButton, QProgressBar, QLabel, QMessageBox, QFileDialog, QCheckBox,
    QListWidget, QListWidgetItem, QRadioButton, QButtonGroup, QSplitter,
    QSizePolicy, QStatusBar, QAction, QMenuBar, QFrame, QScrollArea,
    QInputDialog, QStackedWidget
)
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QFont, QColor, QPalette, QTextCursor
from PyQt5.QtGui import QValidator
```

- [ ] **Step 2: Add DARK_STYLESHEET constant and setup_dark_theme() after PHASE2_STEPS**

Insert this block after line 42 (after the closing `]` of `PHASE2_STEPS`):

```python

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
QLineEdit, QSpinBox, QComboBox {
    background-color: #0d1117;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 7px 11px;
    color: #c9d1d9;
    selection-background-color: #264f78;
    min-height: 18px;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus { border-color: #58a6ff; }
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {
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
    palette.setColor(QPalette.HighlightedText,  c("#f0f6fc"))
    palette.setColor(QPalette.Disabled, QPalette.Text,       c("#484f58"))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, c("#484f58"))
    palette.setColor(QPalette.Disabled, QPalette.WindowText, c("#484f58"))
    app.setPalette(palette)
    app.setStyleSheet(DARK_STYLESHEET)
```

- [ ] **Step 3: Smoke-test the theme function**

```bash
cd /home/ubuntu/Documents/SabkiappDigiCampProd/HostTemplates
python3 - <<'EOF'
import sys
from PyQt5.QtWidgets import QApplication
from deploy_manager import setup_dark_theme, DARK_STYLESHEET
app = QApplication(sys.argv)
setup_dark_theme(app)
print("DARK_STYLESHEET length:", len(DARK_STYLESHEET))
print("Palette window color:", app.palette().color(app.palette().Window).name())
assert app.palette().color(app.palette().Window).name() == "#0d1117"
print("OK")
EOF
```

Expected: prints `OK` with no exceptions.

- [ ] **Step 4: Commit**

```bash
cd /home/ubuntu/Documents/SabkiappDigiCampProd
git add HostTemplates/deploy_manager.py
git commit -m "feat(ui): add DARK_STYLESHEET constant and setup_dark_theme()"
```

---

### Task 2: Update make_terminal() and password_field()

**Files:**
- Modify: `HostTemplates/deploy_manager.py` — `make_terminal()` (≈line 352) and `password_field()` (≈line 428)

- [ ] **Step 1: Replace make_terminal() body**

Find and replace `make_terminal()`:

```python
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
```

- [ ] **Step 2: Replace password_field() body**

Find and replace `password_field()`:

```python
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
```

- [ ] **Step 3: Commit**

```bash
cd /home/ubuntu/Documents/SabkiappDigiCampProd
git add HostTemplates/deploy_manager.py
git commit -m "feat(ui): update make_terminal() and password_field() styling"
```

---

### Task 3: Add SidebarWidget class

**Files:**
- Modify: `HostTemplates/deploy_manager.py` — insert new class before Phase1Widget (before the `# ─── Phase 1 Widget` comment, ≈line 460)

- [ ] **Step 1: Add make_page_header() helper and SidebarWidget class**

Insert this block immediately before the `# ─────────────────────────────────────────────` / `#  Phase 1 Widget` section:

```python
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
            start_w, end_w = self.EXPANDED_WIDTH, self.COLLAPSED_WIDTH
        else:
            # Expand: animate first, then show text in _on_anim_done
            self._collapse_btn.setText("\u276e")
            self._collapse_btn.setToolTip("Collapse sidebar")
            self.setMinimumWidth(0)
            self.setMaximumWidth(self.EXPANDED_WIDTH)
            start_w, end_w = self.COLLAPSED_WIDTH, self.EXPANDED_WIDTH

        self._anim.setStartValue(start_w)
        self._anim.setEndValue(end_w)
        self._anim.finished.connect(self._on_anim_done)
        self._anim.start()

    def _on_anim_done(self) -> None:
        try:
            self._anim.finished.disconnect(self._on_anim_done)
        except TypeError:
            pass
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
```

- [ ] **Step 2: Smoke-test SidebarWidget instantiates without error**

```bash
cd /home/ubuntu/Documents/SabkiappDigiCampProd/HostTemplates
python3 - <<'EOF'
import sys
from PyQt5.QtWidgets import QApplication
from deploy_manager import SidebarWidget, setup_dark_theme

app = QApplication(sys.argv)
setup_dark_theme(app)

sb = SidebarWidget()
sb.show()

# Test public API
sb.set_active_page(2)
sb.update_status("ssh", True, "SSH: Connected")
sb.update_status("flash", False)

assert sb._nav_buttons[2].isChecked()
assert "#3fb950" in sb._status_labels["ssh"].styleSheet()
print("SidebarWidget OK")
EOF
```

Expected: prints `SidebarWidget OK` with no exceptions.

- [ ] **Step 3: Commit**

```bash
cd /home/ubuntu/Documents/SabkiappDigiCampProd
git add HostTemplates/deploy_manager.py
git commit -m "feat(ui): add make_page_header() and SidebarWidget"
```

---

### Task 4: Add StepWizardWidget class

**Files:**
- Modify: `HostTemplates/deploy_manager.py` — insert before Phase1Widget class (after SidebarWidget, before the Phase 1 Widget comment block)

- [ ] **Step 1: Insert StepWizardWidget class**

Insert this block immediately before the `# ─────────────────────────────────────────────` / `#  Phase 1 Widget` comment block:

```python
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
```

- [ ] **Step 2: Smoke-test StepWizardWidget**

```bash
cd /home/ubuntu/Documents/SabkiappDigiCampProd/HostTemplates
python3 - <<'EOF'
import sys
from PyQt5.QtWidgets import QApplication
from deploy_manager import StepWizardWidget, setup_dark_theme

app = QApplication(sys.argv)
setup_dark_theme(app)

wiz = StepWizardWidget(total_steps=6)
wiz.show()

wiz.set_active_step(3)
wiz.set_step_label("Step 3/6 · Installing Cloudflare tunnel...")
assert "#238636" in wiz._circles[0].styleSheet()   # step 1 completed
assert "#238636" in wiz._circles[1].styleSheet()   # step 2 completed
assert "#1f6feb" in wiz._circles[2].styleSheet()   # step 3 active

wiz.mark_all_completed()
assert "\u2713" == wiz._circles[5].text()

wiz.reset()
assert "6" == wiz._circles[5].text()
print("StepWizardWidget OK")
EOF
```

Expected: prints `StepWizardWidget OK` with no exceptions.

- [ ] **Step 3: Commit**

```bash
cd /home/ubuntu/Documents/SabkiappDigiCampProd
git add HostTemplates/deploy_manager.py
git commit -m "feat(ui): add StepWizardWidget"
```

---

### Task 5: Update Phase1Widget

**Files:**
- Modify: `HostTemplates/deploy_manager.py` — `Phase1Widget` class

Changes: add `flash_completed` signal, add page header, update layout spacing, remove inline button stylesheet, add objectName to flash_btn, add tooltip to detect_btn, update device_path_label color.

- [ ] **Step 1: Add flash_completed signal to Phase1Widget**

In the `Phase1Widget` class definition, add the signal directly after `class Phase1Widget(QWidget):`:

```python
class Phase1Widget(QWidget):
    flash_completed = pyqtSignal(bool)
```

- [ ] **Step 2: Update Phase1Widget._build_ui()**

Replace the entire `_build_ui` method body (everything inside `def _build_ui(self):`) with:

```python
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
```

- [ ] **Step 3: Emit flash_completed in _on_finished()**

In `Phase1Widget._on_finished`, add `self.flash_completed.emit(code == 0)` as the first line:

```python
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
```

- [ ] **Step 4: Commit**

```bash
cd /home/ubuntu/Documents/SabkiappDigiCampProd
git add HostTemplates/deploy_manager.py
git commit -m "feat(ui): update Phase1Widget - header, spacing, dangerBtn, flash_completed signal"
```

---

### Task 6: Update Phase2Widget

**Files:**
- Modify: `HostTemplates/deploy_manager.py` — `Phase2Widget` class

Changes: add `ssh_status_changed` signal, add page header, update layout spacing, replace inline button stylesheets with objectNames, integrate `StepWizardWidget`, update SSH status label colors.

- [ ] **Step 1: Add ssh_status_changed signal to Phase2Widget**

In the `Phase2Widget` class definition, add the signal directly after `class Phase2Widget(QWidget):`:

```python
class Phase2Widget(QWidget):
    ssh_status_changed = pyqtSignal(bool)
```

- [ ] **Step 2: Replace Phase2Widget._build_ui() body**

Replace the entire `_build_ui` method body with:

```python
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
```

- [ ] **Step 3: Update _test_ssh() to emit signal and use theme colors**

Replace the body of `_test_ssh()`:

```python
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
```

- [ ] **Step 4: Update _execute() to show wizard on start**

In `_execute()`, find the block that starts `self.terminal.clear()` and add wizard setup:

```python
        self.terminal.clear()
        self.dl_key_btn.hide()
        self.progress.setValue(0)
        self.progress.setFormat("Starting...")
        self.execute_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        # Show and reset step wizard
        self.step_wizard.reset()
        self.step_wizard.show()
```

- [ ] **Step 5: Update _on_output_line() to drive wizard**

Replace `_on_output_line()`:

```python
    def _on_output_line(self, line: str):
        append_terminal(self.terminal, line)
        if line.startswith("[Step "):
            step_n = int(line[6]) if line[6].isdigit() else 0
            if step_n:
                self.step_wizard.set_active_step(step_n)
                self.step_wizard.set_step_label(line.strip())
            self.progress.setValue(step_n)
            self.progress.setFormat(line.strip())
```

- [ ] **Step 6: Update _on_finished() to drive wizard completion/failure**

Replace `_on_finished()`:

```python
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
            append_terminal(self.terminal, f"\n[FAILED] Exit code: {code}")
```

- [ ] **Step 7: Update _cancel() to reset wizard**

Replace `_cancel()`:

```python
    def _cancel(self):
        if self.runner:
            self.runner.terminate_process()
        self.execute_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.step_wizard.reset()
        self.step_wizard.hide()
        append_terminal(self.terminal, "\n[CANCELLED] by user.")
```

- [ ] **Step 8: Commit**

```bash
cd /home/ubuntu/Documents/SabkiappDigiCampProd
git add HostTemplates/deploy_manager.py
git commit -m "feat(ui): update Phase2Widget - header, spacing, wizard, signals, accentBtn/primaryBtn"
```

---

### Task 7: Update ConfigPreviewWidget and UtilitiesWidget

**Files:**
- Modify: `HostTemplates/deploy_manager.py` — `ConfigPreviewWidget._build_ui()` and `UtilitiesWidget._build_ui()`

- [ ] **Step 1: Replace ConfigPreviewWidget._build_ui() body**

```python
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
```

- [ ] **Step 2: Replace UtilitiesWidget._build_ui() body**

```python
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
        self.scan_terminal.setMaximumHeight(180)
        scan_layout.addWidget(self.scan_terminal)
        root.addWidget(scan_group)

        root.addStretch()
```

Note: `ConfigPreviewWidget._refresh()` calls `self.text_area.setPlainText(content)`. Since `text_area` is now a `QPlainTextEdit` (returned by `make_terminal()`), that call still works unchanged.

- [ ] **Step 3: Commit**

```bash
cd /home/ubuntu/Documents/SabkiappDigiCampProd
git add HostTemplates/deploy_manager.py
git commit -m "feat(ui): update ConfigPreviewWidget and UtilitiesWidget - headers and spacing"
```

---

### Task 8: Restructure MainWindow

**Files:**
- Modify: `HostTemplates/deploy_manager.py` — `MainWindow` class

Changes: replace `QTabWidget` with `SidebarWidget` + `QStackedWidget`, wire sidebar signals, connect `flash_completed` and `ssh_status_changed` to sidebar, update title/size.

- [ ] **Step 1: Replace MainWindow.__init__**

```python
    def __init__(self):
        super().__init__()
        self.model = load_config()
        self.generator = ConfigGenerator(self.model)
        self._build_ui()
        self.setWindowTitle("GSM Gateway \u00b7 Host Deployment Manager")
        self.resize(1050, 780)
        self.setMinimumSize(850, 600)
```

- [ ] **Step 2: Replace MainWindow._build_ui()**

```python
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
```

- [ ] **Step 3: Replace _on_tab_changed with _on_page_changed**

Remove `_on_tab_changed` and add `_on_page_changed`:

```python
    def _on_page_changed(self, idx: int):
        self.stack.setCurrentIndex(idx)
        self.sidebar.set_active_page(idx)
        if idx == 1:
            self.phase2_widget.refresh_from_model()
        elif idx == 2:
            self.preview_widget._refresh()
        elif idx == 3:
            self.utils_widget.refresh_from_model()
```

- [ ] **Step 4: Update show_preview() to use stack**

```python
    def show_preview(self, key: str):
        self.stack.setCurrentIndex(2)
        self.sidebar.set_active_page(2)
        self.preview_widget.show_key(key)
```

- [ ] **Step 5: Commit**

```bash
cd /home/ubuntu/Documents/SabkiappDigiCampProd
git add HostTemplates/deploy_manager.py
git commit -m "feat(ui): restructure MainWindow - sidebar + QStackedWidget replaces QTabWidget"
```

---

### Task 9: Update main(), verify the app runs, final commit

**Files:**
- Modify: `HostTemplates/deploy_manager.py` — `main()` function

- [ ] **Step 1: Replace main()**

```python
def main():
    app = QApplication(sys.argv)
    app.setApplicationName("GSM Gateway Deployer")
    setup_dark_theme(app)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
```

- [ ] **Step 2: Run the app and verify visual correctness**

```bash
cd /home/ubuntu/Documents/SabkiappDigiCampProd/HostTemplates
python3 deploy_manager.py
```

Verify checklist (manual):
- [ ] App launches with dark background (#0d1117)
- [ ] Left sidebar visible at ~210px with nav items, title "GSM DEPLOYER"
- [ ] Clicking nav items switches the right-side page content
- [ ] Collapse button (❮) at bottom of sidebar animates it to icon-only mode
- [ ] Expand button (❯) animates it back to full width with labels
- [ ] Phase 1 page shows title "Phase 1 — SD Card Preparation" with subtitle
- [ ] Phase 1 "Flash SD Card" button is red (dangerBtn)
- [ ] Phase 2 "Execute on RPi" button is green (primaryBtn)
- [ ] Phase 2 "Test SSH Connection" button is blue (accentBtn)
- [ ] All inputs have dark background with focus border on click
- [ ] Group box titles are blue/small-caps style
- [ ] Progress bars have gradient blue fill
- [ ] Terminal areas have near-black background with blue text
- [ ] Config Preview page uses terminal-style text area for code display
- [ ] Status bar at bottom styled (dark, subtle text)
- [ ] File menu works: Save (Ctrl+S), Load (Ctrl+O), Reset all function

- [ ] **Step 3: Full smoke test (no display required)**

```bash
cd /home/ubuntu/Documents/SabkiappDigiCampProd/HostTemplates
python3 - <<'EOF'
import sys
from PyQt5.QtWidgets import QApplication
from deploy_manager import (
    MainWindow, setup_dark_theme,
    SidebarWidget, StepWizardWidget,
    ConfigModel, load_config,
)

app = QApplication(sys.argv)
setup_dark_theme(app)

win = MainWindow()

# Sidebar
assert hasattr(win, "sidebar")
assert hasattr(win, "stack")
assert win.stack.count() == 4

# Page switching
win._on_page_changed(1)
assert win.stack.currentIndex() == 1
win._on_page_changed(0)
assert win.stack.currentIndex() == 0

# Sidebar status update
win.sidebar.update_status("ssh", True, "SSH: Connected")
win.sidebar.update_status("flash", False)

# Step wizard
wiz = win.phase2_widget.step_wizard
wiz.set_active_step(2)
wiz.mark_all_completed()
wiz.reset()

# show_preview
win.show_preview("pjsip")
assert win.stack.currentIndex() == 2

print("Full smoke test PASSED")
EOF
```

Expected output: `Full smoke test PASSED`

- [ ] **Step 4: Final commit**

```bash
cd /home/ubuntu/Documents/SabkiappDigiCampProd
git add HostTemplates/deploy_manager.py
git commit -m "feat(ui): update main() + complete deploy manager UI/UX overhaul"
```

---

## Self-Review Notes

**Spec coverage check:**
- Theme system (DARK_STYLESHEET + QPalette + setup_dark_theme) → Task 1 ✓
- make_terminal() + password_field() updates → Task 2 ✓
- SidebarWidget with collapse animation, nav items, status indicators → Task 3 ✓
- StepWizardWidget with 6 steps, state API → Task 4 ✓
- Phase1Widget: header, spacing, dangerBtn, flash_completed signal → Task 5 ✓
- Phase2Widget: header, spacing, primaryBtn/accentBtn, wizard integration, ssh_status_changed → Task 6 ✓
- ConfigPreviewWidget + UtilitiesWidget: headers, spacing → Task 7 ✓
- MainWindow restructure (sidebar + QStackedWidget) → Task 8 ✓
- main() update → Task 9 ✓
- make_page_header() helper → Task 3 ✓ (inserted before SidebarWidget)
- No external dependencies → confirmed, all built-in PyQt5 ✓

**Type consistency check:**
- `SidebarWidget.set_active_page(idx: int)` called in MainWindow._on_page_changed and show_preview → consistent ✓
- `SidebarWidget.update_status(key, ok, label)` called in MainWindow lambda → consistent ✓
- `StepWizardWidget.set_active_step(n)` called from Phase2Widget._on_output_line → consistent ✓
- `StepWizardWidget.mark_all_completed()` / `mark_failed()` / `reset()` called in Phase2Widget → consistent ✓
- `flash_completed = pyqtSignal(bool)` emitted and connected → consistent ✓
- `ssh_status_changed = pyqtSignal(bool)` emitted and connected → consistent ✓
