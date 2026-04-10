# Deploy Manager UI/UX Overhaul — Design Spec

**Date:** 2026-04-10
**File:** `HostTemplates/deploy_manager.py`
**Scope:** Visual theme, layout restructure, step wizard, polish. No logic changes.

## 1. Theme System

GitHub Dark palette applied via application-wide QSS stylesheet + custom QPalette on Fusion style.

### Color Tokens

| Token | Value | Usage |
|-------|-------|-------|
| `bg` | `#0d1117` | Window background |
| `surface` | `#161b22` | Cards, group boxes, sidebar |
| `elevated` | `#1f2937` | Hover states, active nav items |
| `border` | `#30363d` | All borders |
| `input_bg` | `#0d1117` | Input field backgrounds |
| `text` | `#c9d1d9` | Primary text |
| `text_subtle` | `#8b949e` | Labels, placeholders, inactive nav |
| `text_bright` | `#f0f6fc` | Headings, emphasis |
| `accent` | `#58a6ff` | Active tab, focus rings, links |
| `success` | `#238636` | Primary action buttons (bg) |
| `success_text` | `#3fb950` | Success status indicators |
| `danger` | `#da3633` | Danger buttons (bg) |
| `danger_text` | `#f85149` | Error status, danger hover |
| `info` | `#1f6feb` | Accent buttons, progress bar |
| `warning` | `#d29922` | Warning indicators |
| `terminal_bg` | `#0a0c10` | Terminal output background |
| `terminal_text` | `#a5d6ff` | Terminal output text |

### QPalette Setup

Custom QPalette applied to QApplication for Fusion style. Maps color tokens to palette roles:
- `Window` → bg, `WindowText` → text, `Base` → input_bg, `AlternateBase` → surface
- `Button` → `#21262d`, `ButtonText` → text, `Highlight` → `#264f78`
- Disabled text → `#484f58`

### QSS Stylesheet (~200 lines)

Applied at application level via `app.setStyleSheet()`. Targets standard widget classes:

- **QWidget**: bg, text color, font-family (`Segoe UI`, `SF Pro Display`, `Ubuntu`, `Cantarell`, sans-serif), font-size 13px
- **QGroupBox**: surface bg, border with border-radius 8px, padding 20px 16px 16px 16px. Title styled as accent-colored label with elevated bg, border-radius 4px
- **QLineEdit, QSpinBox, QComboBox**: input_bg, border 1px solid border color, border-radius 6px, padding 8px 12px. Focus state: accent border color
- **QPushButton**: `#21262d` bg, border 1px solid border color, border-radius 6px, padding 8px 16px. Hover: `#30363d` bg. Disabled: surface bg, `#484f58` text
- **QPushButton#primaryBtn**: success bg, white text. Hover: `#2ea043`
- **QPushButton#dangerBtn**: danger bg, white text. Hover: danger_text
- **QPushButton#accentBtn**: info bg, white text. Hover: `#388bfd`
- **QProgressBar**: surface bg, border, border-radius 6px, 24px height. Chunk: linear gradient from info to accent, border-radius 5px
- **QScrollBar**: 10px width/height, bg handle with hover state, no arrow buttons
- **QMenuBar**: bg background, border-bottom. Items: 6px 12px padding, border-radius 4px
- **QMenu**: surface bg, border, border-radius 8px. Items: padding 8px, hover elevated bg + accent text
- **QStatusBar**: bg background, subtle text, border-top
- **QPlainTextEdit (terminal)**: styled per-instance in `make_terminal()` — terminal_bg, terminal_text, border-radius 8px, padding 12px
- **QListWidget**: input_bg, rounded, selection elevated bg + accent text
- **QToolTip**: elevated bg, text, border, border-radius 4px

## 2. Layout Structure

### Current Structure
```
QMainWindow
  └── QTabWidget (4 tabs)
        ├── Phase1Widget
        ├── Phase2Widget
        ├── ConfigPreviewWidget
        └── UtilitiesWidget
```

### New Structure
```
QMainWindow
  └── QHBoxLayout (central widget)
        ├── SidebarWidget (QFrame, 200px / 50px collapsed)
        │     ├── App title area
        │     ├── Nav items (4 items)
        │     ├── Stretch
        │     ├── Status section
        │     └── Collapse toggle button
        └── QStackedWidget (pages)
              ├── Phase1Widget (updated)
              ├── Phase2Widget (updated, with StepWizardWidget)
              ├── ConfigPreviewWidget (updated)
              └── UtilitiesWidget (updated)
```

### SidebarWidget (new class, ~80 lines)

A `QFrame` subclass with:

- **Expanded state** (200px width):
  - Title: "GSM DEPLOYER" label, accent color, bold, 13px
  - Nav items: 4 `QPushButton`s (flat, no border) in a QVBoxLayout, each with unicode icon + text label
    - `\u25A0  Phase 1 · SD Card` (▪ solid square — represents storage/card)
    - `\u25B6  Phase 2 · RPi Setup` (▶ play/deploy triangle)
    - `\u25C8  Config Preview` (◈ diamond — represents configuration)
    - `\u2699  Utilities` (⚙ gear)
  - Active item: elevated bg, accent text, 2px left border accent
  - Inactive: subtle text, transparent bg, hover → elevated bg
  - Status section at bottom (below stretch):
    - Small label "STATUS" in dim uppercase
    - Status dots: colored circle + label. These are static visual hints, not live — updated by MainWindow when:
      - SSH test succeeds/fails in Phase2Widget (emits signal → sidebar updates "SSH" dot)
      - Phase1 flash completes (emits signal → sidebar updates "Flash" dot)
    - Two indicators: "SSH: Connected/Disconnected", "Flash: Done/Pending"
  - Collapse button: `\u276E` (❮) / `\u276F` (❯) arrow at very bottom

- **Collapsed state** (50px width):
  - Title hidden
  - Nav items: icons only, centered, with tooltips showing full names
  - Status dots only (no text)
  - Expand button

- **Signals**: `page_changed(int)` emitted when nav item clicked, connected to `QStackedWidget.setCurrentIndex`

- **Collapse animation**: Use `QPropertyAnimation` on `maximumWidth` property for smooth transition (200ms, EaseInOut curve)

### Page Titles

Each page widget gets a title header area at the top of its layout:
- Heading: text_bright, 18px, font-weight 600
- Subtitle: text_subtle, 13px
- Thin separator line (`QFrame` with `HLine` shape) below, border color

## 3. Phase 2 Step Wizard

### StepWizardWidget (new class, ~60 lines)

A `QWidget` that renders a horizontal step progress indicator. Placed between the Phase 2 form fields and the terminal output.

**Visual layout:**
```
[●]───[●]───[③]───[○]───[○]───[○]
 ✓     ✓   Active   4     5     6
```

**Structure:**
- Row of circle widgets connected by horizontal lines
- 6 steps (matching Phase 2's existing step count)
- Each circle: 28px diameter, centered number or checkmark

**Step states:**
- **Completed**: success bg (`#238636`), white checkmark, green connecting line
- **Active**: accent bg (`#58a6ff`), white number, animated (optional subtle pulse via QTimer opacity toggle)
- **Pending**: border-color circle (`#30363d` bg), subtle text number, gray connecting line

**API:**
- `set_total_steps(n: int)` — configure step count
- `set_active_step(n: int)` — mark step n as active (all prior become completed)
- `set_step_label(text: str)` — show text below the wizard (e.g., "Step 3/6 · Installing Cloudflare tunnel...")
- `reset()` — all steps back to pending

**Integration with Phase2Widget:**
- The wizard is hidden initially, shown when "Execute on RPi" is clicked
- `_on_output_line` already parses `[Step N/6]` — connect this to `set_active_step(N)`
- On finished with success: all steps completed
- On finished with failure: active step turns danger color
- On cancel: reset

## 4. Widget Updates

### Phase1Widget

Changes to `_build_ui`:
- Add page title: "Phase 1 — SD Card Preparation" / "Configure and flash Ubuntu to SD card"
- Root layout: 20px content margins, 12px spacing
- Form layout: 12px vertical spacing, 16px horizontal spacing
- `flash_btn`: remove inline stylesheet, set `objectName("dangerBtn")`
- `preview_btn`: no change (default button style from QSS)
- `cancel_btn`: no change (default button style)
- `device_path_label`: update color to `#f85149`
- `detect_btn`: add tooltip "Scan for USB block devices"
- Progress bar: styled by QSS (no code changes needed)
- Terminal: updated via `make_terminal()` changes

### Phase2Widget

Changes to `_build_ui`:
- Add page title: "Phase 2 — RPi Deployment" / "Deploy code and configure Raspberry Pi"
- Root layout: 20px content margins, 12px spacing
- Insert `StepWizardWidget` between form scroll area and terminal
- `execute_btn`: remove inline stylesheet, set `objectName("primaryBtn")`
- `dl_key_btn`: remove inline stylesheet, set `objectName("accentBtn")`
- `test_ssh_btn`: add `objectName("accentBtn")`
- SSH status label colors: update to theme colors (`#3fb950` success, `#f85149` error)
- Form layouts: 12px vertical spacing, 16px horizontal spacing
- `cf_token_edit` placeholder: add tooltip explaining the field is optional

### ConfigPreviewWidget

Changes to `_build_ui`:
- Add page title: "Config Preview" / "Review generated configuration files"
- Root layout: 20px content margins, 12px spacing
- `text_area`: use `make_terminal()` styling (same dark bg, monospace font)
- Buttons: default style via QSS (no objectName needed)

### UtilitiesWidget

Changes to `_build_ui`:
- Add page title: "Utilities" / "Standalone tools and diagnostics"
- Root layout: 20px content margins, 12px spacing
- Group boxes: styled by QSS
- Terminals: updated via `make_terminal()` changes

## 5. Updated Helper Functions

### `make_terminal()`
- Font: `JetBrains Mono` (fallback `Monospace`), 10pt
- Stylesheet: terminal_bg background, terminal_text color, border 1px solid border, border-radius 8px, padding 12px, selection-background-color `#264f78`
- Min height: 200px

### `password_field()`
- Toggle button: 56px width, cursor set to `Qt.PointingHandCursor`
- Add tooltip "Toggle password visibility"
- No other changes (QSS handles styling)

### `main()`
- Remove `app.setStyle("Fusion")` (moved into `setup_dark_theme`)
- Call `setup_dark_theme(app)` which sets Fusion style, custom QPalette, and QSS

## 6. MainWindow Changes

- Window title: `"GSM Gateway · Host Deployment Manager"`
- Default size: 1050x780 (slightly wider for sidebar)
- Minimum size: 850x600
- Remove `QTabWidget` — replace with sidebar + `QStackedWidget`
- Keep menu bar (File menu with Save, Load, Reset). It's styled by QSS to match the dark theme and sits naturally above the sidebar+content layout. Keyboard shortcuts Ctrl+S, Ctrl+O preserved.
- Status bar: keep, style via QSS
- `_on_tab_changed` → connect to sidebar's `page_changed` signal instead
- `show_preview(key)` → switch to preview page via stacked widget index

## 7. Files Changed

Only one file: `HostTemplates/deploy_manager.py`

**New classes (2):**
- `SidebarWidget(QFrame)` — ~80 lines
- `StepWizardWidget(QWidget)` — ~60 lines

**New functions (1):**
- `setup_dark_theme(app)` — ~30 lines

**New constants (1):**
- `DARK_STYLESHEET` — ~200 lines

**Modified classes (5):**
- `Phase1Widget` — spacing, objectNames, page title
- `Phase2Widget` — spacing, objectNames, page title, wizard integration
- `ConfigPreviewWidget` — spacing, page title
- `UtilitiesWidget` — spacing, page title
- `MainWindow` — layout restructure (sidebar + stacked widget)

**Modified functions (2):**
- `make_terminal()` — updated font and stylesheet
- `main()` — call `setup_dark_theme()`

**No logic changes.** All config generation, script running, SSH, and data model code stays exactly the same.

## 8. No External Dependencies

Everything uses built-in PyQt5:
- `QPropertyAnimation` for sidebar collapse
- `QPalette` for dark theme
- `QStackedWidget` for page switching
- `QFrame` for sidebar
- Unicode characters for nav icons
- QSS for all styling
