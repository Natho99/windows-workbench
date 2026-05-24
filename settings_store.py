import os
import sqlite3

# ── DB path ──────────────────────────────────────────────────────────────
def _db_path() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    folder = os.path.join(base, "4GCapital")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "journal.db")

DB_PATH = _db_path()

# ── Defaults ─────────────────────────────────────────────────────────────
DEFAULTS: dict = {
    "parse_mode": "ai",
    "api_key": "",
    "groq_model": "llama-3.1-8b-instant",
    "show_groq_monitor": "0",           # "1" = visible, "0" = hidden (default: hidden)

    # Confluence Configuration — commented out; uncomment to re-enable
    # "conf_username":  "",
    # "conf_api_token": "",
    # "conf_base_url":  "https://4gcapital-company.atlassian.net/wiki/spaces/TS/pages/",

    # Transaction ID Samples
    "BeyonicTxnId":  "T91592568",
    "NetworkTxnId":  "141693582907",
    "AirtelTxnId":   "143363767927",
    "BankTxnId":     "S34111201",
    "FlexipayTxnId": "772774570001",
}

_db_initialized = False


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db():
    global _db_initialized
    if _db_initialized:
        return
    with _get_conn() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS settings "
            "(key TEXT PRIMARY KEY, value TEXT NOT NULL DEFAULT '')"
        )
        for k, v in DEFAULTS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v)
            )
        conn.commit()
    _db_initialized = True


def load_settings() -> dict:
    _init_db()
    cfg = dict(DEFAULTS)
    try:
        with _get_conn() as conn:
            rows = conn.execute("SELECT key, value FROM settings").fetchall()
        for row in rows:
            cfg[row["key"]] = row["value"]
    except Exception:
        pass
    return cfg


def save_settings(cfg: dict) -> None:
    _init_db()
    try:
        with _get_conn() as conn:
            conn.executemany(
                """
                INSERT INTO settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                [(str(k), str(v)) for k, v in cfg.items()],
            )
            conn.commit()
    except Exception as exc:
        raise IOError(f"Could not save settings: {exc}") from exc