# run_import_and_check.py
from lib.wifi_importer import import_airodump_to_sqlite, fetch_stats
from lib.gui import run_html_gui, HtmlGuiBridge
from PyQt6.QtWidgets import QApplication
import sqlite3
import sys
import json
from PyQt6.QtCore import QTimer
from lib.settings_window import create_settings_window, apply_dark_mode
CSV_FILE = "tmp/test.csv"
DB_FILE = "db/wifi.sqlite"
WEB_VIEW = None
settings_win = None 

def main():
    readWifis()

def readWifis():    
    
    try:
        parsed_n, parsed_c = import_airodump_to_sqlite(CSV_FILE, DB_FILE)
        a = "Loaded targets: {} networks, {} clients.".format(parsed_n, parsed_c)
        call_js(WEB_VIEW, "receiveData", {"command":"typeOut","data":a})
        
        
        db_n, db_c = fetch_stats(DB_FILE)
        print(f"DEBUG: DB now has {db_n} networks and {db_c} clients.")

    except Exception as e:
        print(f"Import failed: {e}")
        

    try:
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        print("\nDEBUG: Networks found:")
        #call_js(WEB_VIEW, "receiveData", {"command":"typeOut","data":"Networks found:"})

        for row in cur.execute("SELECT ssid, bssid, channel FROM networks WHERE CAST(channel AS INTEGER) > 0 ORDER BY bssid"):
            print(row)
            #call_js(WEB_VIEW, "receiveData", {"command":"typeOut","data":row})

        print("\nDEBUG: Clients found:")
        #call_js(WEB_VIEW, "receiveData", {"command":"typeOut","data":"Clients found:"})
      
        for row in cur.execute("SELECT client_bssid, COALESCE(associated_network,'<NULL>') FROM clients WHERE associated_network IS NOT NULL AND associated_network <> '' ORDER BY client_bssid"):
            #call_js(WEB_VIEW, "receiveData", {"command":"typeOut","data":row})
            print(row)

    finally:
        conn.close()


def on_command(payload: dict) -> None:
    global WEB_VIEW
    print("[main] got command:", payload)
    cmd = (payload.get("command") or "").lower()
    data = payload.get("data")
    if cmd == "exit":
        # do cleanup if needed…
        #QApplication.instance().quit()
        call_js(WEB_VIEW, "receiveData", {"command":"ping","data":123})
    elif cmd == "ping":
        print("pong:", data)
    elif cmd == "scan":
        call_js(WEB_VIEW, "receiveData", {"command":"typeOut","data":"Scanning for networks"})
        readWifis()
    elif cmd == "settings":
        global settings_win
        app = QApplication.instance() or QApplication([])
        apply_dark_mode(app)
        settings_win = create_settings_window(DB_FILE)  # no parent
        settings_win.show()
        settings_win.raise_()
        settings_win.activateWindow()
        

def on_loaded(view, bridge):
    global WEB_VIEW
    payload = {"command": "appReady", "data": True}
    view.page().runJavaScript(
        f"receiveData({json.dumps(payload)})",
        lambda result: print("JS returned:", result)  # callback is optional
    )
    WEB_VIEW=view

def call_js(view, func_name: str, arg):
    
    import json
    view.page().runJavaScript(f"{func_name}({json.dumps(arg)})")


if __name__ == "__main__":    
    
    exit_code = run_html_gui(
        html_path="www/index.html",
        width=800,
        height=710,
        title="pyDeauther",
        initial_py_to_js={"appState": "ready"},
        on_command=on_command,
        on_loaded=on_loaded
    )
    raise SystemExit(exit_code)