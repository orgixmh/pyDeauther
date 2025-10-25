# hud_stream.py
from __future__ import annotations
import re
from collections import deque
from typing import Optional, Callable

from PyQt6.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot

# ANSI sequences
_RE_CSI_CLEAR = re.compile(r'\x1b\[(?:2J|J)')  # ED (clear screen)
_RE_CSI_HOME  = re.compile(r'\x1b\[H')        # CUP home
_RE_ANSI_ALL  = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')  # generic CSI stripper

class HudStreamAggregator(QObject):
    """
    Thread-safe aggregator for terminal-like output (e.g., airodump-ng):
      - feed(...) from ANY thread (bytes/str)
      - Handles \r (in-place updates)
      - Detects clear-screen/home → resets buffer
      - Clears old lines immediately when a new frame header is seen
        (we split by 'CH ' in a case-insensitive way and keep only the latter part)
      - Strips ANSI
      - Throttles updates (timer) and emits full text via sig_render
    """
    sig_render = pyqtSignal(str)
    _sig_feed_str = pyqtSignal(str)
    _sig_feed_bytes = pyqtSignal(bytes)

    def __init__(
        self,
        *,
        max_lines: int = 1500,
        interval_ms: int = 75,
        frame_anchor_regex: str = r'CH',  # not strictly needed now, kept for compatibility
        parent: Optional[QObject] = None
    ):
        super().__init__(parent)
        self._lines = deque(maxlen=max_lines)
        self._current_line: list[str] = []
        self._dirty = False

        self._anchor_re = re.compile(frame_anchor_regex, re.IGNORECASE)

        # marshal to GUI thread
        self._sig_feed_str.connect(self._consume_str)
        self._sig_feed_bytes.connect(self._consume_bytes)

        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._flush)
        self._timer.start()

    # ----- public API -----
    def feed(self, chunk) -> None:
        """Feed bytes/str from ANY thread."""
        if chunk is None:
            return
        if isinstance(chunk, (bytes, bytearray)):
            self._sig_feed_bytes.emit(bytes(chunk))
        else:
            self._sig_feed_str.emit(str(chunk))

    def reset(self, initial_header: Optional[str] = None) -> None:
        """Clear buffers; optionally start with a header line."""
        self._lines.clear()
        self._current_line.clear()
        if initial_header:
            self._lines.append(initial_header.rstrip('\n'))
        self._dirty = True

    # ----- GUI-thread consumers -----
    @pyqtSlot(bytes)
    def _consume_bytes(self, b: bytes) -> None:
        if not b:
            return
        # detect clear/home BEFORE stripping
        text_for_ctrl = b.decode('utf-8', 'ignore')
        if _RE_CSI_CLEAR.search(text_for_ctrl) or _RE_CSI_HOME.search(text_for_ctrl):
            self.reset()
        try:
            text = b.decode('utf-8', errors='replace')
        except Exception:
            text = str(b)
        self._ingest(_RE_ANSI_ALL.sub('', text))

    @pyqtSlot(str)
    def _consume_str(self, text: str) -> None:
        if not text:
            return
        if _RE_CSI_CLEAR.search(text) or _RE_CSI_HOME.search(text):
            self.reset()
        self._ingest(_RE_ANSI_ALL.sub('', text))

    # ----- core ingestion (GUI thread) -----
    def _finalize_line(self) -> None:
        """Finalize current line, with new-frame logic triggered by 'CH ' detection."""
        raw_line = ''.join(self._current_line)
        self._current_line.clear()

        # NEW: robust in-line detection:
        # If 'CH ' appears anywhere (case-insensitive), clear previous content and keep only from that token.
        up = raw_line.upper()
        idx = up.find('CH ')
        if idx != -1:
            # clear previous lines and keep normalized header start
            self._lines.clear()
            line = raw_line[idx:]  # keep from 'CH ' onward
        else:
            line = raw_line
            # (Optional) legacy: if regex matched at line start you could still clear
            # if self._anchor_re.match(line): self._lines.clear()

        self._lines.append(line)
        self._dirty = True

    def _ingest(self, chunk: str) -> None:
        i = 0
        cl = self._current_line
        while i < len(chunk):
            ch = chunk[i]
            if ch == '\r':
                cl.clear()  # rewrite current line
                i += 1
            elif ch == '\n':
                self._finalize_line()
                i += 1
            else:
                cl.append(ch)
                i += 1
        self._dirty = True  # even without newline, update the live line

    def _flush(self):
        if not self._dirty:
            return
        parts = list(self._lines)
        if self._current_line:
            parts.append(''.join(self._current_line))
        self.sig_render.emit('\n'.join(parts))
        self._dirty = False


# ---------- Helpers to wire into your OutputHUD ----------

def attach_to_output_hud(
    hud,
    *,
    max_lines: int = 1500,
    interval_ms: int = 75,
    frame_anchor_regex: str = r'CH',  # kept for API compatibility
    auto_show: bool = False,
    parent: Optional[QObject] = None,
) -> HudStreamAggregator:
    """
    Wire aggregator to OutputHUD (uses hud.view.setPlainText).
    Call agg.reset('CH ...') at the start of each run if you want a header immediately.
    """
    agg = HudStreamAggregator(
        max_lines=max_lines,
        interval_ms=interval_ms,
        frame_anchor_regex=frame_anchor_regex,
        parent=parent
    )

    def _set_text_full(s: str):
        sb = hud.view.verticalScrollBar()
        at_end = (sb.value() == sb.maximum())
        hud.view.setPlainText(s)
        if at_end:
            sb.setValue(sb.maximum())
        if auto_show and not hud.isVisible():
            hud.show_hud()

    agg.sig_render.connect(_set_text_full)
    return agg


def make_process_output_handler(agg: HudStreamAggregator) -> Callable[[int, str], None]:
    """Tiny adapter for your CommandManager on_output callback."""
    def _on_out(pid: int, chunk) -> None:
        agg.feed(chunk)
    return _on_out
