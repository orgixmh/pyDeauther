import json, pathlib, sys
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, QUrl, QTimer
from PyQt6.QtWidgets import QApplication
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtGui import QGuiApplication, QShortcut, QKeySequence
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineFullScreenRequest
from PyQt6.QtCore import Qt, QUrl, QTimer
from PyQt6.QtWebEngineCore import QWebEngineSettings

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
    on_loaded=None,
) -> int:
    app = QApplication.instance() or QApplication(sys.argv)

    view = QWebEngineView()
    view.resize(width, height)
    view.setWindowTitle(title)

    # ---- WebChannel bridge ----
    channel = QWebChannel()
    bridge = HtmlGuiBridge(on_command=on_command)
    channel.registerObject("bridge", bridge)
    view.page().setWebChannel(channel)

    # ---- Load HTML ----
    html_fs_path = str(pathlib.Path(html_path).resolve())
    url = QUrl.fromLocalFile(html_fs_path)
    view.setUrl(url)

    # ---- DevTools window (same profile) ----
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

    # ---- Window sizing/flags (start fixed size, no maximize) ----
    W, H = width, height
    view.setFixedSize(W, H)
    view.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
    view.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, True)

    # center on primary screen
    screen_geo = QGuiApplication.primaryScreen().availableGeometry()
    view.move(
        screen_geo.x() + (screen_geo.width() - W) // 2,
        screen_geo.y() + (screen_geo.height() - H) // 2,
    )

    # ---- Fullscreen support ----
    # Allow HTML5 requestFullscreen() from inside the page
    view.settings().setAttribute(
        QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True
    )

    # Remember normal geometry and relax fixed-size when entering FS
    normal_geo = None
    fixed_initially = True  # we setFixedSize above

    def enter_fs():
        nonlocal normal_geo
        if normal_geo is None:
            normal_geo = view.window().geometry()
        # relax constraints or FS may fail
        if fixed_initially:
            view.setMinimumSize(0, 0)
            view.setMaximumSize(16777215, 16777215)  # Qt max
        view.window().showFullScreen()

    def exit_fs():
        view.window().showNormal()
        # restore fixed constraints & geometry
        if fixed_initially:
            view.setFixedSize(W, H)
        if normal_geo is not None:
            view.window().setGeometry(normal_geo)

    # F11 toggle
    QShortcut(QKeySequence("F11"), view,
              activated=lambda: (exit_fs() if view.window().isFullScreen() else enter_fs()))
    # Esc to exit FS
    QShortcut(QKeySequence("Escape"), view, activated=exit_fs)

    # Honor HTML5 fullscreen requests from the page
    def on_fs_request(req: QWebEngineFullScreenRequest):
        # print for debugging if needed:
        # print("[Qt] fullScreenRequested toggleOn=", req.toggleOn())
        req.accept()
        enter_fs() if req.toggleOn() else exit_fs()

    view.page().fullScreenRequested.connect(on_fs_request)

    # ---- After load: prime JS channel & optional callback ----
    def after_load(ok: bool):
        if not ok:
            print(f"[Python] Failed to load: {html_fs_path}")
            return
        def fire():
            if initial_py_to_js is not None:
                bridge.py_to_js.emit(json.dumps(initial_py_to_js))
            if callable(on_loaded):
                on_loaded(view, bridge)
        QTimer.singleShot(150, fire)

    view.loadFinished.connect(after_load)

    view.show()
    return app.exec()

