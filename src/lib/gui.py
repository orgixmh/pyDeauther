import sys
import json
import pathlib
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, QUrl, QTimer
from PyQt6.QtWidgets import QApplication
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtGui import QShortcut, QKeySequence
from PyQt6.QtWebEngineCore import QWebEnginePage 
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtCore import Qt

class HtmlGuiBridge(QObject):
    py_to_js = pyqtSignal(str)
    def __init__(self, on_command=None):
        super().__init__()
        self._on_command = on_command

    @pyqtSlot(str)
    def send_command(self, json_str: str) -> None:
        try:
            payload = json.loads(json_str)
        except Exception as e:
            print("[Python] Bad JSON from JS:", e, json_str)
            return
        if callable(self._on_command):
            self._on_command(payload)

def run_html_gui(
    html_path: str,
    width: int = 1000,
    height: int = 700,
    *,
    title: str = "HTML GUI",
    initial_py_to_js: dict | None = None,
    on_command=None,
    on_loaded=None,  # <<< new: callback(view, bridge) after page is ready
) -> int:
    app = QApplication.instance() or QApplication(sys.argv)

    view = QWebEngineView()
    view.resize(width, height)
    view.setWindowTitle(title)

    channel = QWebChannel()
    bridge = HtmlGuiBridge(on_command=on_command)
    channel.registerObject("bridge", bridge)
    view.page().setWebChannel(channel)

    html_fs_path = str(pathlib.Path(html_path).resolve())
    url = QUrl.fromLocalFile(html_fs_path)
    view.setUrl(url)

    # Create a separate DevTools window bound to the same profile
    devtools_view = QWebEngineView()
    devtools_page = QWebEnginePage(view.page().profile())
    view.page().setDevToolsPage(devtools_page)
    devtools_view.setPage(devtools_page)
    devtools_view.setWindowTitle("DevTools")

    def toggle_devtools():
        if devtools_view.isVisible():
            devtools_view.hide()
        else:
            devtools_view.resize(1000, 700)
            devtools_view.show()

    
    QShortcut(QKeySequence("F12"), view, activated=toggle_devtools)
    QShortcut(QKeySequence("Ctrl+Shift+I"), view, activated=toggle_devtools)

    W, H = width, height
    view.setFixedSize(W, H)
    view.setWindowFlag(
        view.windowFlags() & ~Qt.WindowType.WindowMaximizeButtonHint
    )   
    view.windowFlags()


    screen_geo = QGuiApplication.primaryScreen().availableGeometry()
    view.move(
        screen_geo.x() + (screen_geo.width() - W) // 2,
        screen_geo.y() + (screen_geo.height() - H) // 2
    )
    
    def after_load(ok: bool):
        if not ok:
            print(f"[Python] Failed to load: {html_fs_path}")
            return
        # give JS a tick to finish its own setup (e.g., WebChannel ready)
        def fire():
            if initial_py_to_js is not None:
                bridge.py_to_js.emit(json.dumps(initial_py_to_js))
            if callable(on_loaded):
                on_loaded(view, bridge)   # <<< hand control to main.py
        QTimer.singleShot(150, fire)    
        
    view.loadFinished.connect(after_load)

    view.show()
    return app.exec()
