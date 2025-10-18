# wifi_importer.py
import csv
import pathlib
import sqlite3
from typing import Optional, Tuple, List, Dict

NETWORKS_HEADER = ["BSSID", "First time seen", "Last time seen", "channel", "Speed",
                   "Privacy", "Cipher", "Authentication", "Power", "beacons", "IV",
                   "LAN IP", "ID-length", "ESSID", "Key"]

CLIENTS_HEADER = ["Station MAC", "First time seen", "Last time seen", "Power",
                  "# packets", "BSSID", "Probed ESSIDs"]

def to_int_or_none(x: str) -> Optional[int]:
    try:
        return int(x.strip())
    except Exception:
        return None

def normalize_bssid(x: str) -> str:
    return x.strip().upper()

def parse_airodump_csv(csv_path: pathlib.Path) -> Tuple[List[Dict], List[Dict]]:
    networks = []
    clients = []
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        mode = None
        for row in reader:
            if not row or all((c.strip() == "" for c in row)):
                continue
            header = [c.strip() for c in row]
            if header[:len(NETWORKS_HEADER)] == NETWORKS_HEADER:
                mode = "networks"; continue
            if header[:len(CLIENTS_HEADER)] == CLIENTS_HEADER:
                mode = "clients"; continue

            if mode == "networks":
                try:
                    bssid = normalize_bssid(row[0])
                    channel = to_int_or_none(row[3])
                    ssid = row[13].strip() if len(row) > 13 else ""
                    networks.append({"ssid": ssid, "bssid": bssid, "channel": channel})
                except Exception:
                    continue
            elif mode == "clients":
                try:
                    station_mac = normalize_bssid(row[0])
                    ap_bssid = row[5].strip().upper() if len(row) > 5 else ""
                    associated = None if ap_bssid in {"(NOT ASSOCIATED)", "FF:FF:FF:FF:FF:FF", ""} else normalize_bssid(ap_bssid)
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
