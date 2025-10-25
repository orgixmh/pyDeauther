# whitelist_lib.py
# PyQt6-based whitelist editor with SQLite persistence
from __future__ import annotations

import os
import re
import sqlite3
from contextlib import closing
from typing import List, Optional

from PyQt6 import QtCore, QtGui, QtWidgets


MAC_REGEX = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")


# -----------------------------
# Persistence helper
# -----------------------------
class WhitelistDB:
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _ensure_schema(self) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS whitelist (
                    id  INTEGER PRIMARY KEY AUTOINCREMENT,
                    mac TEXT NOT NULL UNIQUE
                )
                """
            )

    def load_all(self) -> List[str]:
        with closing(self._connect()) as conn:
            cur = conn.execute("SELECT mac FROM whitelist ORDER BY mac COLLATE NOCASE;")
            return [row[0] for row in cur.fetchall()]

    def replace_all(self, macs: List[str]) -> None:
        macs = list(dict.fromkeys(macs))  # de-dup preserving order
        with closing(self._connect()) as conn, conn:
            conn.execute("DELETE FROM whitelist;")
            conn.executemany("INSERT INTO whitelist(mac) VALUES (?)", [(m,) for m in macs])

    def clear(self) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute("DELETE FROM whitelist;")


# -----------------------------
# Dark mode style (local, no global theme changes)
# -----------------------------
DARK_QSS = """
QDialog, QWidget {
    background-color: #111315;
    color: #E6E6E6;
    font-size: 13px;
}
QLineEdit, QListWidget, QInputDialog, QAbstractItemView, QMessageBox {
    background-color: #1A1D20;
    color: #E6E6E6;
    border: 1px solid #2A2E33;
    padding: 4px;
    selection-background-color: #2F3A46;
}
QPushButton {
    background-color: #20242A;
    border: 1px solid #2A2E33;
    padding: 6px 10px;
    border-radius: 6px;
}
QPushButton:hover { background-color: #2A2F36; }
QPushButton:pressed { background-color: #242932; }
QPushButton#danger {
    border: 1px solid #5a2a2a;
    background-color: #3a1f1f;
}
QPushButton#primary {
    border: 1px solid #2f4a5f;
    background-color: #1f2b36;
}
QLabel[secondary="true"] { color: #A6A6A6; }
QGroupBox {
    border: 1px solid #2A2E33;
    margin-top: 10px;
}
QGroupBox::title {
    subcontrol-origin: margin; left: 8px; padding: 0 4px;
}
"""


# -----------------------------
# Validation helpers
# -----------------------------
def is_valid_mac(mac: str) -> bool:
    return bool(MAC_REGEX.match(mac.strip()))


def normalize_mac(mac: str) -> str:
    mac = mac.strip()
    # Uppercase hex and ensure colon-separated
    mac = mac.replace("-", ":")
    parts = mac.split(":")
    if len(parts) == 6 and all(len(p) in (1, 2) for p in parts):
        parts = [p.zfill(2) for p in parts]
        return ":".join(parts).upper()
    return mac.upper()


# -----------------------------
# Main window/dialog
# -----------------------------
class WhitelistWindow(QtWidgets.QDialog):
    """
    Usage:
        dlg = WhitelistWindow(db_path)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            macs = dlg.current_macs()
    """
    macsChanged = QtCore.pyqtSignal(list)

    def __init__(self, db_path: str, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Whitelist")
        self.setObjectName("WhitelistWindow")
        self.setModal(True)
        self.setMinimumSize(520, 440)
        self.setStyleSheet(DARK_QSS)

        self.db = WhitelistDB(db_path)

        # Widgets
        self.list = QtWidgets.QListWidget()
        self.list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)

        self.input_mac = QtWidgets.QLineEdit()
        self.input_mac.setPlaceholderText("Add MAC (e.g. 00:11:22:33:44:55)")
        self.btn_add = QtWidgets.QPushButton("Add")
        self.btn_edit = QtWidgets.QPushButton("Edit")
        self.btn_remove = QtWidgets.QPushButton("Remove")

        self.btn_save = QtWidgets.QPushButton("Save")
        self.btn_save.setObjectName("primary")
        self.btn_clear = QtWidgets.QPushButton("Clear")
        self.btn_clear.setObjectName("danger")
        self.btn_close = QtWidgets.QPushButton("Close")

        info = QtWidgets.QLabel("Stored in SQLite table: whitelist")
        info.setProperty("secondary", True)

        # Layout
        left_box = QtWidgets.QVBoxLayout()
        left_box.addWidget(self.list, 1)
        left_box.addWidget(info, 0)

        right_box = QtWidgets.QVBoxLayout()
        right_box.addWidget(self.input_mac)
        right_box.addWidget(self.btn_add)
        right_box.addWidget(self.btn_edit)
        right_box.addWidget(self.btn_remove)
        right_box.addStretch(1)

        top = QtWidgets.QHBoxLayout()
        top.addLayout(left_box, 1)
        top.addLayout(right_box, 0)

        bottom = QtWidgets.QHBoxLayout()
        bottom.addStretch(1)
        bottom.addWidget(self.btn_save)
        bottom.addWidget(self.btn_clear)
        bottom.addWidget(self.btn_close)

        root = QtWidgets.QVBoxLayout(self)
        root.addLayout(top, 1)
        root.addSpacing(8)
        root.addLayout(bottom, 0)

        # Wire up
        self.btn_add.clicked.connect(self._on_add)
        self.btn_edit.clicked.connect(self._on_edit)
        self.btn_remove.clicked.connect(self._on_remove)
        self.btn_save.clicked.connect(self._on_save)
        self.btn_clear.clicked.connect(self._on_clear)
        self.btn_close.clicked.connect(self.reject)
        self.input_mac.returnPressed.connect(self._on_add)
        self.list.itemDoubleClicked.connect(lambda _: self._on_edit())

        # Load initial
        self._load_from_db()

    # ---------- public API ----------
    def current_macs(self) -> List[str]:
        return [self.list.item(i).text() for i in range(self.list.count())]

    # ---------- internal actions ----------
    def _load_from_db(self) -> None:
        self.list.clear()
        for mac in self.db.load_all():
            self.list.addItem(mac)

    def _add_mac_to_list(self, mac: str) -> None:
        macs = set(self.current_macs())
        if mac in macs:
            QtWidgets.QMessageBox.information(self, "Duplicate", f"{mac} already exists.")
            return
        self.list.addItem(mac)
        self.macsChanged.emit(self.current_macs())

    def _on_add(self) -> None:
        raw = self.input_mac.text().strip()
        if not raw:
            # If empty, open a dialog to type it
            ok = False
            raw, ok = QtWidgets.QInputDialog.getText(self, "Add MAC", "MAC address:")
            if not ok:
                return
        mac = normalize_mac(raw)
        if not is_valid_mac(mac):
            QtWidgets.QMessageBox.warning(self, "Invalid MAC", "Please enter a valid MAC like 00:11:22:33:44:55")
            return
        self._add_mac_to_list(mac)
        self.input_mac.clear()

    def _on_edit(self) -> None:
        items = self.list.selectedItems()
        if not items:
            QtWidgets.QMessageBox.information(self, "Edit", "Select a MAC to edit.")
            return
        item = items[0]
        cur = item.text()
        new, ok = QtWidgets.QInputDialog.getText(self, "Edit MAC", "MAC address:", text=cur)
        if not ok:
            return
        mac = normalize_mac(new)
        if not is_valid_mac(mac):
            QtWidgets.QMessageBox.warning(self, "Invalid MAC", "Please enter a valid MAC like 00:11:22:33:44:55")
            return
        # Check duplicate (allow same item)
        existing = set(self.current_macs())
        existing.discard(cur)
        if mac in existing:
            QtWidgets.QMessageBox.information(self, "Duplicate", f"{mac} already exists.")
            return
        item.setText(mac)
        self.macsChanged.emit(self.current_macs())

    def _on_remove(self) -> None:
        items = self.list.selectedItems()
        if not items:
            QtWidgets.QMessageBox.information(self, "Remove", "Select one or more MACs to remove.")
            return
        for it in items:
            row = self.list.row(it)
            self.list.takeItem(row)
        self.macsChanged.emit(self.current_macs())

    def _on_save(self) -> None:
        try:
            self.db.replace_all(self.current_macs())
            QtWidgets.QMessageBox.information(self, "Saved", "Whitelist saved.")
            self.accept()  # close as 'OK'
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to save: {e!r}")

    def _on_clear(self) -> None:
        reply = QtWidgets.QMessageBox.question(
            self,
            "Confirm Clear",
            "This will remove ALL MAC addresses from the list and database.\nAre you sure?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No,
        )
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            self.list.clear()
            try:
                self.db.clear()
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Error", f"Failed to clear DB: {e!r}")
            self.macsChanged.emit([])

# -----------------------------
# Simple facades for callers
# -----------------------------
def edit_whitelist(db_path: str, parent: Optional[QtWidgets.QWidget] = None) -> List[str]:
    """
    Opens the editor window modally. Returns the (possibly updated) MAC list
    from the database after the window closes (regardless of Save/Close).
    """
    owns_app = False
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
        owns_app = True

    dlg = WhitelistWindow(db_path, parent=parent)
    dlg.exec()

    # Always read fresh from DB
    macs = WhitelistDB(db_path).load_all()
    if owns_app:
        app.quit()
    return macs


def get_whitelist(db_path: str) -> List[str]:
    """Utility to fetch MACs as an array without opening the UI."""
    return WhitelistDB(db_path).load_all()
