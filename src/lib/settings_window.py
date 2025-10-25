# ./lib/settings_window.py
# PyQt6 settings window with VirtualBox-like sidebar & SQLite persistence.
# Call show_settings(sqlite_path: str) from main.py.

from __future__ import annotations
import sys
import sqlite3
from pathlib import Path
from typing import Dict, Any, Optional
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon, QGuiApplication
from PyQt6.QtWidgets import (
    QApplication, QWidget, QMainWindow, QListWidget, QListWidgetItem,
    QStackedWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QComboBox,
    QPlainTextEdit, QLineEdit, QPushButton, QSpacerItem, QSizePolicy, QMessageBox,
    QFormLayout
)
from typing import Optional
from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtGui import QPalette, QColor
from PyQt6.QtWidgets import QApplication, QStyleFactory
# =========================
# Top-level configurable labels & defaults
# =========================

MENU_LABELS = {
    "general": "General",
    "applications": "Deauther",
    "about": "About",
}

GENERAL_LABELS = {
    "fast_mode": "Fast mode",
    "default_screen": "Default Screen",
    "automatic_turn_on": "Automatic Turn On",
}

APPLICATIONS_LABELS = {
    "wifi_card":"Wifi card name",
    "deauth_count":"Deauth count",
    "scan_time":"Scant time in seconds",
    "max_attack_loop": "Re-scan every x attacks",
    "enable_monitor_cmds": "Enable Monitor mode commands",
    "disable_monitor_cmds": "Disable Monitor mode commands",
    "set_channel_cmd": "Set channel command",
    "scan_cmd": "airodump-ng command",
    "lolipop_broadcast_cmd": "aireplaly-ng broadcast command",
    "lolipop_client_cmd": "aireplaly-ng client command",
}

ABOUT_TEXT = (
    '<div style="font-size: 13px;">'
    'pyDeauther © ORGix<br>'
    '<a href="http://github.com/orgixmh/lolipop">http://github.com/orgixmh/lolipop</a>'
    '<br>Credits to Dreff and Gevin'
    '</div>'
)

# Combobox options
DEFAULT_SCREEN_OPTIONS = ["Matrix", "Red Queen", "Amiga"]

# Defaults (persisted to DB on first run / missing keys)
DEFAULT_SETTINGS: Dict[str, Any] = {
    # General
    "fast_mode": True,
    "default_screen": DEFAULT_SCREEN_OPTIONS[0],
    "automatic_turn_on": False,

    # Applications
    "enable_monitor_cmds": "ifconfig wlan0 down\niwconfig wlan0 mode monitor\nifconfig wlan0 up",
    "disable_monitor_cmds": "ifconfig wlan0 down\niwconfig wlan0 mode managed\nifconfig wlan0 up",
    "set_channel_cmd": "iw wlan0 set channel %CHANNEL%",
    "scan_cmd": "airodump-ng wlan0 --write output /tmp/airodump-ng.csv",
    "wifi_card":"wlan0",
    "deauth_count":"10",
    "scan_time":"20",
    "max_attack_loop":"10",
    "lolipop_broadcast_cmd": "aireplaly-ng -1 10 -c %BSSID% -h %CLIENT% wlan0",
    "lolipop_client_cmd": "aireplaly-ng -1 10 -c %BSSID% -h %CLIENT% wlan0",
}

# Keys schema mapping to types (for UI & serialization)
SETTING_TYPES = {
    "fast_mode": "bool",
    "default_screen": "str",
    "automatic_turn_on": "bool",
    "enable_monitor_cmds": "text",
    "disable_monitor_cmds": "text",
    "set_channel_cmd": "str",
    "scan_cmd": "text",
    "lolipop_broadcast_cmd": "str",
    "lolipop_client_cmd": "str",
    "wifi_card":"text",
    "deauth_count":"text",
    "scan_time":"text",
    "max_attack_loop":"text",
}

# =========================
# SQLite helpers
# =========================

def _ensure_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.commit()
    return conn

def _load_settings(conn: sqlite3.Connection) -> Dict[str, Any]:
    # Read current values
    cur = conn.cursor()
    cur.execute("SELECT key, value FROM settings")
    rows = cur.fetchall()
    data = {k: v for k, v in rows}

    # Merge defaults for missing keys and persist them
    missing = []
    for k, default in DEFAULT_SETTINGS.items():
        if k not in data:
            missing.append((k, _to_db_value(default)))
            data[k] = _from_db_value(_to_db_value(default), SETTING_TYPES.get(k, "str"))
    if missing:
        cur.executemany("INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)", missing)
        conn.commit()

    # Cast to proper types
    casted = {k: _from_db_value(v, SETTING_TYPES.get(k, "str")) for k, v in data.items()}
    return casted

def _save_settings(conn: sqlite3.Connection, values: Dict[str, Any]) -> None:
    cur = conn.cursor()
    rows = [(k, _to_db_value(v)) for k, v in values.items()]
    cur.executemany("INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)", rows)
    conn.commit()

def _to_db_value(v: Any) -> str:
    if isinstance(v, bool):
        return "1" if v else "0"
    return str(v if v is not None else "")

def _from_db_value(raw: Optional[str], typ: str) -> Any:
    if typ == "bool":
        return (raw or "0") in ("1", "true", "True", "YES", "yes")
    # "text" and "str" both become str, but text may include newlines
    return "" if raw is None else raw

# =========================
# UI
# =========================
def apply_dark_mode(app: QApplication) -> None:
    # Force Fusion so the palette is respected across platforms
    app.setStyle(QStyleFactory.create("Fusion"))

    pal = QPalette()
    base      = QColor(30, 30, 30)
    alt_base  = QColor(37, 37, 37)
    window    = QColor(24, 24, 24)
    text      = QColor(230, 230, 230)
    mid       = QColor(60, 60, 60)
    button    = QColor(45, 45, 45)
    highlight = QColor(53, 132, 228)

    pal.setColor(QPalette.ColorRole.Window, window)
    pal.setColor(QPalette.ColorRole.WindowText, text)
    pal.setColor(QPalette.ColorRole.Base, base)
    pal.setColor(QPalette.ColorRole.AlternateBase, alt_base)
    pal.setColor(QPalette.ColorRole.ToolTipBase, text)
    pal.setColor(QPalette.ColorRole.ToolTipText, text)
    pal.setColor(QPalette.ColorRole.Text, text)
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(160,160,160))
    pal.setColor(QPalette.ColorRole.Button, button)
    pal.setColor(QPalette.ColorRole.ButtonText, text)
    pal.setColor(QPalette.ColorRole.Dark, QColor(20,20,20))
    pal.setColor(QPalette.ColorRole.Mid, mid)
    pal.setColor(QPalette.ColorRole.Shadow, QColor(0,0,0))
    pal.setColor(QPalette.ColorRole.Highlight, highlight)
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(255,255,255))
    pal.setColor(QPalette.ColorRole.Link, QColor(120,170,255))
    pal.setColor(QPalette.ColorRole.LinkVisited, QColor(170,150,255))

    app.setPalette(pal)

    # Optional stylesheet to nudge common widgets darker
    app.setStyleSheet("""
        QToolTip { color: #eee; background: #222; border: 1px solid #444; }
        QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QListView, QTreeView, QSpinBox {
            background: #1f1f1f; color: #e6e6e6; border: 1px solid #3a3a3a; border-radius: 4px;
        }
        QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus {
            border: 1px solid #3584e4;
        }
        QPushButton {
            background: #2b2b2b; color: #e6e6e6; border: 1px solid #3a3a3a; padding: 6px 12px; border-radius: 6px;
        }
        QPushButton:hover { background: #333; }
        QPushButton:pressed { background: #262626; }
        QListWidget { background: #1b1b1b; border: 1px solid #333; }
    """)

class SettingsWindow(QMainWindow):
    def __init__(self, sqlite_path: str, parent: Optional[QMainWindow] = None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self._db_path = Path(sqlite_path)
        self._conn = _ensure_db(self._db_path)
        self._values = _load_settings(self._conn)
        self.setFixedWidth(1200)
        # Main layout: sidebar + stacked pages
        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(10)

        self.sidebar = QListWidget()
        self.sidebar.setIconSize(QSize(24, 24))
        self.sidebar.setFixedWidth(160)
        self.sidebar.setUniformItemSizes(True)
        self.sidebar.setAlternatingRowColors(False)
        self.sidebar.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.sidebar.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # Icons: try themed first, then fallbacks
        icon_general = (QIcon.fromTheme("preferences-system")
                        or QIcon.fromTheme("settings")
                        or self.style().standardIcon(self.style().StandardPixmap.SP_ComputerIcon))
        icon_apps = (QIcon.fromTheme("network-wireless")       # wifi icon
                     or QIcon.fromTheme("preferences-desktop")
                     or self.style().standardIcon(self.style().StandardPixmap.SP_DriveNetIcon))
        icon_about = (QIcon.fromTheme("help-about")
                      or self.style().standardIcon(self.style().StandardPixmap.SP_MessageBoxInformation))

        self.pages = QStackedWidget()

        # Build pages
        general_page = self._build_general_page()
        apps_page = self._build_applications_page()
        about_page = self._build_about_page()

        self.pages.addWidget(general_page)
        self.pages.addWidget(apps_page)
        self.pages.addWidget(about_page)

        # Sidebar items
        self._add_sidebar_item(MENU_LABELS["general"], icon_general, 0)
        self._add_sidebar_item(MENU_LABELS["applications"], icon_apps, 1)
        self._add_sidebar_item(MENU_LABELS["about"], icon_about, 2)
        self.sidebar.setCurrentRow(0)
        self.sidebar.currentRowChanged.connect(self.pages.setCurrentIndex)

        # Right side: pages + buttons
        right_col = QWidget()
        right_layout = QVBoxLayout(right_col)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)
        right_layout.addWidget(self.pages)

        # Buttons row
        btn_row = QHBoxLayout()
        btn_row.addItem(QSpacerItem(20, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        self.btn_save = QPushButton("Save")
        self.btn_close = QPushButton("Close")
        btn_row.addWidget(self.btn_save)
        btn_row.addWidget(self.btn_close)
        right_layout.addLayout(btn_row)

        # Assemble
        root_layout.addWidget(self.sidebar)
        root_layout.addWidget(right_col)

        self.setCentralWidget(root)

        # Connections
        self.btn_save.clicked.connect(self.save_settings)
        self.btn_close.clicked.connect(self.close)

        # Fixed layout size suggestion (similar to VirtualBox scale)
        self.resize(880, 620)
        self._center()

    def _add_sidebar_item(self, text: str, icon: QIcon, page_index: int):
        item = QListWidgetItem(icon, text)
        item.setData(Qt.ItemDataRole.UserRole, page_index)
        self.sidebar.addItem(item)

    # ----- Pages -----

    def _build_general_page(self) -> QWidget:
        w = QWidget()
        layout = QFormLayout(w)
        layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setHorizontalSpacing(18)
        layout.setVerticalSpacing(12)

        # fast_mode
        self.chk_fast_mode = QCheckBox()
        self.chk_fast_mode.setChecked(bool(self._values.get("fast_mode", False)))
        layout.addRow(GENERAL_LABELS["fast_mode"], self.chk_fast_mode)

        # default_screen
        self.cmb_default_screen = QComboBox()
        self.cmb_default_screen.addItems(DEFAULT_SCREEN_OPTIONS)
        current = str(self._values.get("default_screen", DEFAULT_SCREEN_OPTIONS[0]))
        if current in DEFAULT_SCREEN_OPTIONS:
            self.cmb_default_screen.setCurrentText(current)
        layout.addRow(GENERAL_LABELS["default_screen"], self.cmb_default_screen)

        # automatic_turn_on
        self.chk_automatic = QCheckBox()
        self.chk_automatic.setChecked(bool(self._values.get("automatic_turn_on", False)))
        layout.addRow(GENERAL_LABELS["automatic_turn_on"], self.chk_automatic)

        return w

    def _build_applications_page(self) -> QWidget:
        w = QWidget()
        layout = QFormLayout(w)
        layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setHorizontalSpacing(18)
        layout.setVerticalSpacing(12)

        # Helper constructors
        def _mk_plain(key: str, lines: int = 4) -> QPlainTextEdit:
            te = QPlainTextEdit()
            te.setPlainText(str(self._values.get(key, "")))
            te.setFixedHeight(te.fontMetrics().height() * lines + 18)
            te.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
            return te

        def _mk_line(key: str) -> QLineEdit:
            le = QLineEdit()
            le.setText(str(self._values.get(key, "")))
            return le

        # scan_cmd (multiline)
        self.te_wifi_card = _mk_line("wifi_card")
        layout.addRow(APPLICATIONS_LABELS["wifi_card"], self.te_wifi_card)
        # scan_cmd (multiline)
        self.te_deauth_count = _mk_line("deauth_count")
        layout.addRow(APPLICATIONS_LABELS["deauth_count"], self.te_deauth_count)
        # scan_cmd (multiline)
        self.te_scan_time = _mk_line("scan_time")
        layout.addRow(APPLICATIONS_LABELS["scan_time"], self.te_scan_time)

        self.te_max_attack_loop = _mk_line("max_attack_loop")
        layout.addRow(APPLICATIONS_LABELS["max_attack_loop"], self.te_max_attack_loop)

        # enable_monitor_cmds (multiline)
        self.te_enable_monitor = _mk_plain("enable_monitor_cmds", 3)
        layout.addRow(APPLICATIONS_LABELS["enable_monitor_cmds"], self.te_enable_monitor)

        # disable_monitor_cmds (multiline)
        self.te_disable_monitor = _mk_plain("disable_monitor_cmds", 3)
        layout.addRow(APPLICATIONS_LABELS["disable_monitor_cmds"], self.te_disable_monitor)

        # set_channel_cmd (single line)
        self.le_set_channel = _mk_line("set_channel_cmd")
        layout.addRow(APPLICATIONS_LABELS["set_channel_cmd"], self.le_set_channel)

        # scan_cmd (multiline)
        self.te_scan = _mk_line("scan_cmd")
        layout.addRow(APPLICATIONS_LABELS["scan_cmd"], self.te_scan)

        # lolipop_broadcast_cmd (single line)
        self.le_broadcast = _mk_line("lolipop_broadcast_cmd")
        layout.addRow(APPLICATIONS_LABELS["lolipop_broadcast_cmd"], self.le_broadcast)

        # lolipop_client_cmd (single line)
        self.le_client = _mk_line("lolipop_client_cmd")
        layout.addRow(APPLICATIONS_LABELS["lolipop_client_cmd"], self.le_client)

        return w

    def _build_about_page(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(16, 16, 16, 16)
        title = QLabel(f"<h2 style='margin:0'>{MENU_LABELS['about']}</h2>")
        v.addWidget(title)
        body = QLabel(ABOUT_TEXT)
        body.setOpenExternalLinks(True)
        v.addWidget(body)
        v.addStretch(1)
        return w

    # ----- Persistence -----

    def _collect_values(self) -> Dict[str, Any]:
        values = {}
        # General
        values["fast_mode"] = bool(self.chk_fast_mode.isChecked())
        values["default_screen"] = self.cmb_default_screen.currentText()
        values["automatic_turn_on"] = bool(self.chk_automatic.isChecked())
        
        # Applications
        values["wifi_card"] = self.te_wifi_card.text()
        values["deauth_count"] = self.te_deauth_count.text()
        
        values["enable_monitor_cmds"] = self.te_enable_monitor.toPlainText()
        values["disable_monitor_cmds"] = self.te_disable_monitor.toPlainText()
        values["set_channel_cmd"] = self.le_set_channel.text()
        values["scan_cmd"] = self.te_scan.text()
        values["lolipop_broadcast_cmd"] = self.le_broadcast.text()
        values["lolipop_client_cmd"] = self.le_client.text()
        values["deauth_count"] = self.te_deauth_count.text()
        values["scan_time"] = self.te_scan_time.text()
        values["max_attack_loop"] = self.te_max_attack_loop.text()
        
        return values

    def save_settings(self):
        try:
            values = self._collect_values()
            _save_settings(self._conn, values)
            QMessageBox.information(self, "Saved", "Settings have been saved.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save settings:\n{e}")

    # ----- Helpers -----

    def _center(self):
        screen_geo = QGuiApplication.primaryScreen().availableGeometry()
        w, h = self.width(), self.height()
        self.move(
            screen_geo.x() + (screen_geo.width() - w) // 2,
            screen_geo.y() + (screen_geo.height() - h) // 2
        )

    def closeEvent(self, event):
        try:
            if self._conn:
                self._conn.close()
        finally:
            super().closeEvent(event)


def create_settings_window(sqlite_path: str, parent: Optional[QMainWindow] = None) -> SettingsWindow:
    """
    Create the settings window without starting the event loop.
    Use this when your app is already running a QApplication.
    """
    # DO NOT create a new QApplication here; assume caller already has one.
    return SettingsWindow(sqlite_path, parent=parent)

def run_settings_app(sqlite_path: str) -> int:
    """
    Standalone runner (only for testing). Starts QApplication and execs.
    """
    import sys
    app = QApplication.instance() or QApplication(sys.argv)
    apply_dark_mode(app)
    win = SettingsWindow(sqlite_path)
    
    win.show()
    return app.exec()

# Public API
def show_settings(sqlite_path: str, parent=None):
    import sys
    app = QApplication.instance()
    created = False
    if app is None:
        from PyQt6.QtWidgets import QApplication
        app = QApplication(sys.argv)
        created = True

    apply_dark_mode(app)             # <-- BEFORE creating the window
    win = SettingsWindow(sqlite_path, parent=parent)
    win.show()

    if created:
        app.exec()
    return win
