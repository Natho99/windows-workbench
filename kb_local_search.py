# kb_local_search.py
# ══════════════════════════════════════════════════════════════════════════════
#  LOCAL-FIRST KNOWLEDGE BASE  —  SQLite + TF-IDF vector search
#  Stores trained Confluence pages locally; enables ultra-fast offline search
# ══════════════════════════════════════════════════════════════════════════════
import sqlite3
import json
import math
import re
import os
import datetime
from pathlib import Path

# ── DB location: user's home directory for true persistence ──────────────────
DB_DIR  = Path.home() / ".4gcapital_kb"
DB_PATH = DB_DIR / "knowledge_base.db"

# ── Stop-words (duplicated here to keep module self-contained) ───────────────
_STOP = {
    "a","an","the","is","are","was","were","be","been","being",
    "have","has","had","do","does","did","will","would","could",
    "should","may","might","shall","can","need","dare","ought",
    "in","on","at","to","for","of","with","by","from","up","about",
    "into","through","during","what","which","who","whom","this",
    "that","these","those","am","and","or","but","if","then",
    "because","as","until","while","how","when","where","why",
    "all","both","each","few","more","most","other","some","such",
    "no","nor","not","only","own","same","so","than","too","very",
    "just","any","there","their","they","we","our","i","my","me",
    "us","you","your","he","she","his","her","it","its",
}

# ══════════════════════════════════════════════════════════════════════════════
#  SCHEMA
# ══════════════════════════════════════════════════════════════════════════════
_DDL = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
CREATE TABLE IF NOT EXISTS pages (
    id           TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    url          TEXT,
    space_key    TEXT,
    body_text    TEXT,
    author       TEXT,
    last_editor  TEXT,
    last_edited  TEXT,
    excerpt      TEXT,
    indexed_at   TEXT NOT NULL,
    tf_json      TEXT
);
CREATE TABLE IF NOT EXISTS training_sessions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    pages_total  INTEGER DEFAULT 0,
    pages_done   INTEGER DEFAULT 0,
    status       TEXT DEFAULT 'running',
    error_msg    TEXT,
    space_key    TEXT,
    base_url     TEXT
);
CREATE TABLE IF NOT EXISTS idf_cache (
    term         TEXT PRIMARY KEY,
    idf          REAL NOT NULL,
    doc_count    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pages_space ON pages(space_key);
CREATE INDEX IF NOT EXISTS idx_pages_indexed ON pages(indexed_at);
"""

# ══════════════════════════════════════════════════════════════════════════════
#  DB HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def _get_conn() -> sqlite3.Connection:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=30,
                           check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(_DDL)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.commit()
    return conn

def _now() -> str:
    return datetime.datetime.utcnow().isoformat()

# ══════════════════════════════════════════════════════════════════════════════
#  TEXT PROCESSING
# ══════════════════════════════════════════════════════════════════════════════
def _tokenise(text: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9]+", text.lower())
    return [t for t in tokens if t not in _STOP and len(t) >= 2]

def _term_freq(tokens: list[str]) -> dict[str, float]:
    if not tokens:
        return {}
    counts: dict[str, int] = {}
    for t in tokens:
        counts[t] = counts.get(t, 0) + 1
    total = len(tokens)
    return {t: c / total for t, c in counts.items()}

# ══════════════════════════════════════════════════════════════════════════════
#  IDF BUILD / LOAD
# ══════════════════════════════════════════════════════════════════════════════
def rebuild_idf(conn: sqlite3.Connection) -> dict[str, float]:
    """Recompute IDF over all pages and cache in idf_cache table."""
    rows = conn.execute("SELECT tf_json FROM pages WHERE tf_json IS NOT NULL").fetchall()
    N = len(rows)
    if N == 0:
        return {}
    df: dict[str, int] = {}
    for row in rows:
        tf = json.loads(row["tf_json"])
        for term in tf:
            df[term] = df.get(term, 0) + 1
    idf: dict[str, float] = {}
    for term, cnt in df.items():
        idf[term] = math.log((N + 1) / (cnt + 1)) + 1.0
    conn.execute("DELETE FROM idf_cache")
    conn.executemany(
        "INSERT INTO idf_cache(term, idf, doc_count) VALUES(?,?,?)",
        [(t, v, df[t]) for t, v in idf.items()])
    conn.commit()
    return idf

def load_idf(conn: sqlite3.Connection) -> dict[str, float]:
    rows = conn.execute("SELECT term, idf FROM idf_cache").fetchall()
    if not rows:
        return rebuild_idf(conn)
    return {r["term"]: r["idf"] for r in rows}

# ══════════════════════════════════════════════════════════════════════════════
#  UPSERT PAGE
# ══════════════════════════════════════════════════════════════════════════════
def upsert_page(conn: sqlite3.Connection, page: dict) -> None:
    body   = (page.get("body_text") or "")[:8000]
    tokens = _tokenise((page.get("title") or "") + " " + body)
    tf     = _term_freq(tokens)
    conn.execute("""
        INSERT INTO pages
            (id, title, url, space_key, body_text, author,
             last_editor, last_edited, excerpt, indexed_at, tf_json)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
            title       = excluded.title,
            url         = excluded.url,
            body_text   = excluded.body_text,
            author      = excluded.author,
            last_editor = excluded.last_editor,
            last_edited = excluded.last_edited,
            excerpt     = excluded.excerpt,
            indexed_at  = excluded.indexed_at,
            tf_json     = excluded.tf_json
    """, (
        page["id"], page["title"], page.get("url", ""),
        page.get("space_key", ""), body,
        page.get("author", ""), page.get("last_editor", ""),
        page.get("last_edited", ""), page.get("excerpt", ""),
        _now(), json.dumps(tf),
    ))

# ══════════════════════════════════════════════════════════════════════════════
#  TF-IDF SEARCH
# ══════════════════════════════════════════════════════════════════════════════
def search_local(query: str, limit: int = 10,
                 space_key: str = None) -> list[dict]:
    """
    Return ranked list of page dicts from the local DB.
    Falls back to title-substring match if TF-IDF returns nothing.
    """
    conn = _get_conn()
    try:
        idf      = load_idf(conn)
        q_tokens = _tokenise(query)
        q_tf     = _term_freq(q_tokens)

        # Query TF-IDF vector
        q_vec  = {t: q_tf[t] * idf.get(t, 1.0) for t in q_tf}
        q_norm = math.sqrt(sum(v * v for v in q_vec.values())) or 1.0

        where  = "WHERE tf_json IS NOT NULL"
        params: list = []
        if space_key:
            where += " AND space_key = ?"
            params.append(space_key)

        rows = conn.execute(
            f"SELECT id, title, url, body_text, author, last_editor, "
            f"last_edited, excerpt, tf_json FROM pages {where}",
            params
        ).fetchall()

        scored = []
        for row in rows:
            tf = json.loads(row["tf_json"])
            dot = sum(q_vec.get(t, 0) * tf.get(t, 0) * idf.get(t, 1.0)
                      for t in q_vec)
            doc_norm = math.sqrt(
                sum((tf.get(t, 0) * idf.get(t, 1.0)) ** 2 for t in tf)
            ) or 1.0
            score = dot / (q_norm * doc_norm)
            if score > 0.001:
                scored.append((score, row))

        scored.sort(key=lambda x: -x[0])

        results = []
        for _, row in scored[:limit]:
            results.append({
                "id":          row["id"],
                "title":       row["title"],
                "url":         row["url"],
                "body_text":   row["body_text"],
                "excerpt":     row["excerpt"],
                "author":      row["author"],
                "last_editor": row["last_editor"],
                "last_edited": row["last_edited"],
            })

        # Fallback: substring title match
        if not results:
            kws = [w.lower() for w in re.findall(r"[A-Za-z0-9]+", query)
                   if w.lower() not in _STOP and len(w) >= 3]
            for kw in kws[:3]:
                fb_rows = conn.execute(
                    f"SELECT id, title, url, body_text, excerpt, author, "
                    f"last_editor, last_edited FROM pages {where} "
                    f"AND lower(title) LIKE ? LIMIT ?",
                    params + [f"%{kw}%", limit]
                ).fetchall()
                for row in fb_rows:
                    if not any(r["id"] == row["id"] for r in results):
                        results.append(dict(row))
                if len(results) >= limit:
                    break

        return results[:limit]
    finally:
        conn.close()

# ══════════════════════════════════════════════════════════════════════════════
#  TRAINING SESSION HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def start_training_session(space_key: str, base_url: str,
                            conn: sqlite3.Connection = None) -> int:
    """
    Insert a new training_sessions row and return its rowid.
    Reuses `conn` if supplied; otherwise opens (and closes) its own.
    """
    own_conn = conn is None
    if own_conn:
        conn = _get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO training_sessions(started_at, status, space_key, base_url) "
            "VALUES(?,?,?,?)",
            (_now(), "running", space_key, base_url),
        )
        if own_conn:
            conn.commit()
        return cur.lastrowid
    finally:
        if own_conn:
            conn.close()


def update_training_progress(session_id: int, done: int, total: int,
                              conn: sqlite3.Connection = None) -> None:
    """
    Update pages_done / pages_total for a running session.
    Reuses `conn` if supplied; otherwise opens (and closes) its own.
    """
    own_conn = conn is None
    if own_conn:
        conn = _get_conn()
    try:
        conn.execute(
            "UPDATE training_sessions SET pages_done=?, pages_total=? WHERE id=?",
            (done, total, session_id),
        )
        if own_conn:
            conn.commit()
    finally:
        if own_conn:
            conn.close()


def finish_training_session(session_id: int, done: int, total: int,
                             error: str = None,
                             conn: sqlite3.Connection = None) -> None:
    """
    Mark a training session as finished (or failed).
    Reuses `conn` if supplied; otherwise opens (and closes) its own.
    """
    status   = "error" if error else "complete"
    own_conn = conn is None
    if own_conn:
        conn = _get_conn()
    try:
        conn.execute(
            "UPDATE training_sessions "
            "SET finished_at=?, pages_done=?, pages_total=?, status=?, error_msg=? "
            "WHERE id=?",
            (_now(), done, total, status, error, session_id),
        )
        if own_conn:
            conn.commit()
    finally:
        if own_conn:
            conn.close()


def get_last_training_session() -> dict | None:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM training_sessions ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_db_stats() -> dict:
    conn = _get_conn()
    try:
        page_count = conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
        idf_terms  = conn.execute("SELECT COUNT(*) FROM idf_cache").fetchone()[0]
        size_bytes = DB_PATH.stat().st_size if DB_PATH.exists() else 0
        last_sess  = get_last_training_session()
        return {
            "page_count":   page_count,
            "idf_terms":    idf_terms,
            "size_mb":      round(size_bytes / 1_048_576, 2),
            "db_path":      str(DB_PATH),
            "last_session": last_sess,
        }
    finally:
        conn.close()


def clear_local_db() -> None:
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM pages")
        conn.execute("DELETE FROM idf_cache")
        conn.commit()
    finally:
        conn.close()