# wifi_importer.py
import csv
import pathlib
import sqlite3
from typing import Optional, Tuple, List, Dict

NETWORKS_HEADER = ["BSSID", "First time seen", "Last time seen", "channel", "CH", "Speed",
                   "Privacy", "Cipher", "Authentication", "Power", "beacons", "IV",
                   "LAN IP", "ID-length", "ESSID", "Key"]

CLIENTS_HEADER = ["Station MAC", "First time seen", "Last time seen", "Power",
                  "# packets", "BSSID", "STATION","Probed ESSIDs"]

def to_int_or_none(x: str) -> Optional[int]:
    try:
        return int(x.strip())
    except Exception:
        return None

def normalize_bssid(x: str) -> str:
    return x.strip().upper()

def _norm(h: str) -> str:
    """normalize header tokens: lower, trim, collapse spaces"""
    return " ".join(h.strip().lower().split())

def _find_col(header: List[str], *aliases: str) -> Optional[int]:
    """find the first index in header matching any alias"""
    hmap = { _norm(h): i for i, h in enumerate(header) }
    for a in aliases:
        if a in hmap:
            return hmap[a]
    return None

def parse_airodump_csv(csv_path: pathlib.Path) -> Tuple[List[Dict], List[Dict]]:
    """
    Robust parser for airodump-ng CSV that tolerates header name changes like:
      - channel <-> CH
      - Station MAC <-> STATION
    """
    networks: List[Dict] = []
    clients: List[Dict] = []

    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        mode: Optional[str] = None   # "networks" | "clients" | None
        idx = {}  # indices for current section

        for row in reader:
            # Skip empty/blank rows
            if not row or all(c.strip() == "" for c in row):
                continue

            header = [_norm(c) for c in row]

            # ---- Detect (or re-detect) section + build index map ----
            # NETWORKS section typically has BSSID and ESSID columns.
            if ("bssid" in header) and ("essid" in header):
                mode = "networks"
                idx = {
                    "bssid": _find_col(row, "bssid"),
                    "channel": _find_col(row, "channel", "ch"),
                    "essid": _find_col(row, "essid", "ssid"),
                }
                # If something critical is missing, keep going; we’ll skip rows gracefully.
                continue

            # CLIENTS section has Station MAC/Station and BSSID.
            if (("station mac" in header) or ("station" in header)) and ("bssid" in header):
                mode = "clients"
                idx = {
                    "station": _find_col(row, "station mac", "station"),
                    "bssid": _find_col(row, "bssid"),
                }
                continue

            # ---- Parse rows according to current section ----
            if mode == "networks":
                try:
                    i_bssid = idx.get("bssid")
                    i_ch    = idx.get("channel")
                    i_ssid  = idx.get("essid")
                    if i_bssid is None or i_ssid is None:
                        continue  # missing critical columns
                    bssid = normalize_bssid(row[i_bssid])
                    channel = to_int_or_none(row[i_ch]) if (i_ch is not None and i_ch < len(row)) else None
                    ssid = row[i_ssid].strip() if (i_ssid < len(row)) else ""
                    networks.append({"ssid": ssid, "bssid": bssid, "channel": channel})
                except Exception:
                    continue

            elif mode == "clients":
                try:
                    i_sta = idx.get("station")
                    i_bss = idx.get("bssid")
                    if i_sta is None:
                        continue
                    station_mac = normalize_bssid(row[i_sta])
                    ap_bssid_raw = row[i_bss].strip().upper() if (i_bss is not None and i_bss < len(row)) else ""
                    # treat NOT ASSOCIATED and broadcast as None
                    bad = {"(NOT ASSOCIATED)", "FF:FF:FF:FF:FF:FF", ""}
                    associated = None if ap_bssid_raw in bad else normalize_bssid(ap_bssid_raw)
                    clients.append({"client_bssid": station_mac, "associated_network": associated})
                except Exception:
                    continue

    return networks, clients


def init_db(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS networks(
            bssid TEXT PRIMARY KEY,
            ssid TEXT,
            channel INTEGER
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS clients(
            client_bssid TEXT PRIMARY KEY,
            associated_network TEXT NULL
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_networks_ssid ON networks(ssid)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_networks_channel ON networks(channel)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_clients_assoc ON clients(associated_network)")
    conn.commit()

def upsert_data(conn: sqlite3.Connection, networks, clients) -> None:
    cur = conn.cursor()
    cur.executemany(
        """INSERT INTO networks(bssid, ssid, channel)
           VALUES(:bssid, :ssid, :channel)
           ON CONFLICT(bssid) DO UPDATE SET ssid=excluded.ssid, channel=excluded.channel""",
        networks
    )
    cur.executemany(
        """INSERT INTO clients(client_bssid, associated_network)
           VALUES(:client_bssid, :associated_network)
           ON CONFLICT(client_bssid) DO UPDATE SET associated_network=excluded.associated_network""",
        clients
    )
    conn.commit()

def import_airodump_to_sqlite(csv_file: str, db_file: str) -> Tuple[int, int]:
    """
    Import airodump CSV into SQLite.
    Returns (networks_count, clients_count) imported (rows parsed, not DB rowcount deltas).
    Raises exceptions on fatal errors.
    """
    networks, clients = parse_airodump_csv(pathlib.Path(csv_file))
    conn = sqlite3.connect(db_file)
    try:
        init_db(conn)
        upsert_data(conn, networks, clients)
    finally:
        conn.close()
    return len(networks), len(clients)

def fetch_stats(db_file: str) -> Tuple[int, int]:
    """Return (network_rows_in_db, client_rows_in_db)."""
    conn = sqlite3.connect(db_file)
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM networks")
        n = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM clients")
        c = cur.fetchone()[0]
        return n, c
    finally:
        conn.close()
