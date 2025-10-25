# output_hud.py
from __future__ import annotations
from typing import Optional
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QPoint, QTimer
from PyQt6.QtGui import QFont, QAction, QGuiApplication
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QPlainTextEdit, QHBoxLayout, QPushButton, QApplication, QFileDialog
)

class OutputHUD(QWidget):
    """
    Minimal always-on-top HUD for streaming text.
    Starts hidden. Call append()/set_text()/show_hud()/hide_hud()/toggle().
    """

    # internal signals to keep GUI-thread safety
    _sig_append   = pyqtSignal(str)
    _sig_set_text = pyqtSignal(str)   # <-- added
    _sig_show     = pyqtSignal()
    _sig_hide     = pyqtSignal()
    _sig_clear    = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None, *,
                 title: str = "Output",
                 max_chars: int = 500_000,          # rolling buffer
                 width: int = 800, height: int = 700,
                 translucent: bool = True):
        super().__init__(parent)

        self._title = title
        self._max_chars = max_chars
        self._autoscroll_pending = False

        # Window chrome
        flags = (
            Qt.WindowType.Tool |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setWindowFlags(flags)
        if translucent:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # Contents
        self.setObjectName("OutputHUD")
        box = QVBoxLayout(self)
        box.setContentsMargins(10, 10, 10, 10)
        box.setSpacing(6)

        # Header row with tiny buttons
        header = QHBoxLayout()
        header.setSpacing(6)

        btn_title = QPushButton(self._title)
        btn_title.setEnabled(False)
        btn_title.setFlat(True)

        btn_clear = QPushButton("Clear")
        btn_clear.clicked.connect(self.clear)

        btn_save = QPushButton("Save…")
        btn_save.clicked.connect(self._save_to_file)

        btn_close = QPushButton("Hide")
        btn_close.clicked.connect(self.hide_hud)

        for b in (btn_title, btn_clear, btn_save, btn_close):
            b.setCursor(Qt.CursorShape.PointingHandCursor)

        header.addWidget(btn_title)
        header.addStretch(1)
        header.addWidget(btn_clear)
        header.addWidget(btn_save)
        header.addWidget(btn_close)

        # Text area
        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        f = QFont("Monospace")
        f.setStyleHint(QFont.StyleHint.TypeWriter)
        self.view.setFont(f)

        box.addLayout(header)
        box.addWidget(self.view)

        # Styling (dark HUD)
        self.setStyleSheet("""
        QWidget#OutputHUD {
            background: rgba(22,22,26,180);
            border-radius: 12px;
        }
        QPlainTextEdit {
            color: #e6e6e6;
            background: transparent;
            border: 1px solid rgba(255,255,255,0.10);
            padding: 6px;
        }
        QPushButton {
            color: #ddd; background: rgba(255,255,255,0.06);
            border: 1px solid rgba(255,255,255,0.12); border-radius: 6px; padding: 3px 8px;
        }
        QPushButton:hover { background: rgba(255,255,255,0.12); }
        QPushButton:disabled { color: #aaa; opacity: 0.8; }
        """)

        # Default size & corner placement (bottom-right)
        self.resize(width, height)
        self._move_to_bottom_right(margin=20)

        # Keyboard shortcuts (hooked via actions)
        act_toggle = QAction(self)
        act_toggle.setShortcut("Ctrl+H")
        act_toggle.triggered.connect(self.toggle)
        self.addAction(act_toggle)

        act_clear = QAction(self)
        act_clear.setShortcut("Ctrl+K")
        act_clear.triggered.connect(self.clear)
        self.addAction(act_clear)

        act_save = QAction(self)
        act_save.setShortcut("Ctrl+S")
        act_save.triggered.connect(self._save_to_file)
        self.addAction(act_save)

        # Connect signals
        self._sig_append.connect(self._append_gui)
        self._sig_set_text.connect(self._set_text_gui)   # <-- added
        self._sig_show.connect(super().show)
        self._sig_hide.connect(super().hide)
        self._sig_clear.connect(self._clear_gui)

        # Start hidden by default (caller decides when to show)
        super().hide()

    # ---------- Public API ----------

    def append(self, text: str) -> None:
        """Thread-safe: queue text to HUD (appends)."""
        self._sig_append.emit(text)

    def set_text(self, text: str) -> None:
        """Thread-safe: replace HUD contents with exactly `text`."""
        self._sig_set_text.emit(text)

    def show_hud(self) -> None:
        self._sig_show.emit()

    def hide_hud(self) -> None:
        self._sig_hide.emit()

    def toggle(self) -> None:
        (self._sig_hide if self.isVisible() else self._sig_show).emit()

    def clear(self) -> None:
        self._sig_clear.emit()

    # ---------- Internals ----------

    def _move_to_bottom_right(self, margin: int = 16) -> None:
        screen = QGuiApplication.primaryScreen()
        if not screen:
            return
        geo = screen.availableGeometry()
        pos = QPoint(geo.right() - self.width() - margin,
                     geo.bottom() - self.height() - margin)
        self.move(pos)

    def _append_gui(self, text: str) -> None:
        # rolling buffer trim (cheap: after append if over max)
        self.view.moveCursor(self.view.textCursor().MoveOperation.End)
        self.view.insertPlainText(text)

        doc = self.view.document()
        if doc.characterCount() > self._max_chars:
            cursor = self.view.textCursor()
            cursor.setPosition(0)
            cursor.setPosition(int(self._max_chars * 0.2), cursor.MoveMode.KeepAnchor)  # trim ~20%
            cursor.removeSelectedText()
            cursor.deletePreviousChar()  # remove leftover newline if any

        # auto-scroll (batched)
        if not self._autoscroll_pending:
            self._autoscroll_pending = True
            QTimer.singleShot(0, self._scroll_to_end)

    def _set_text_gui(self, text: str) -> None:
        """Replace entire contents, preserving autoscroll if user is at bottom."""
        sb = self.view.verticalScrollBar()
        at_end = sb.value() == sb.maximum()
        self.view.setPlainText(text)
        if at_end:
            sb.setValue(sb.maximum())

    def _scroll_to_end(self) -> None:
        self._autoscroll_pending = False
        self.view.moveCursor(self.view.textCursor().MoveOperation.End)

    def _clear_gui(self) -> None:
        self.view.clear()

    def _save_to_file(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save Output", "output.txt", "Text Files (*.txt);;All Files (*)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.view.toPlainText())

    # Optional: drag the frameless HUD by grabbing empty space
    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()
            ev.accept()
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if ev.buttons() & Qt.MouseButton.LeftButton:
            self.move(ev.globalPosition().toPoint() - getattr(self, "_drag_pos", QPoint()))
            ev.accept()
        super().mouseMoveEvent(ev)
