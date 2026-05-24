# kb_trainer.py
# ══════════════════════════════════════════════════════════════════════════════
#  KNOWLEDGE BASE TRAINER  —  Crawls Confluence and builds local TF-IDF index
#  Runs in a background thread; reports progress via callbacks
# ══════════════════════════════════════════════════════════════════════════════
import threading
import datetime
import sqlite3
from typing import Callable
from kb_local_search import (
    _get_conn, upsert_page, rebuild_idf,
    start_training_session, update_training_progress,
    finish_training_session, get_db_stats,
)
# ══════════════════════════════════════════════════════════════════════════════
#  PROGRESS CALLBACK TYPE
#  on_progress(done: int, total: int, page_title: str, phase: str)
#  on_done(stats: dict)
#  on_error(msg: str)
# ══════════════════════════════════════════════════════════════════════════════
class KBTrainer:
    """
    Pulls every page from Confluence (paginated), strips HTML,
    computes TF vectors, upserts into local SQLite, then rebuilds IDF.
    """
    def __init__(self, client,
                 on_progress: Callable = None,
                 on_done: Callable = None,
                 on_error: Callable = None):
        self._client      = client   # ConfluenceClient instance
        self._on_progress = on_progress or (lambda *a, **k: None)
        self._on_done     = on_done     or (lambda *a, **k: None)
        self._on_error    = on_error    or (lambda *a, **k: None)
        self._stop_flag   = threading.Event()
        self._thread: threading.Thread | None = None

    # ── Public API ─────────────────────────────────────────────────────────────
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_flag.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_flag.set()

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    # ── Worker ─────────────────────────────────────────────────────────────────
    def _run(self):
        client     = self._client
        space_key  = client.space_key or ""
        # ── Open ONE connection for the entire training run ───────────────────
        conn = _get_conn()
        # WAL mode allows concurrent reads without blocking writes
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")  # wait up to 10s on lock
        session_id = start_training_session(space_key, client._origin, conn=conn)

        done  = 0
        total = 0
        try:
            # ── Phase 1: count pages ──────────────────────────────────────────
            self._on_progress(0, 0, "", "Counting pages…")
            total = self._count_pages(client, space_key)
            self._on_progress(0, total, "", f"Found {total} pages — downloading…")

            # ── Phase 2: paginated crawl ──────────────────────────────────────
            start = 0
            page_size = 50
            while not self._stop_flag.is_set():
                batch = self._fetch_page_batch(client, space_key, start, page_size)
                if not batch:
                    break
                for raw in batch:
                    if self._stop_flag.is_set():
                        break
                    page_dict = self._normalise(raw, client)
                    upsert_page(conn, page_dict)
                    done += 1
                    # Pass conn so no second connection is opened
                    update_training_progress(session_id, done, total, conn=conn)
                    self._on_progress(done, total, page_dict["title"], "Indexing…")
                conn.commit()
                start += page_size
                if len(batch) < page_size:
                    break

            # ── Phase 3: rebuild IDF ──────────────────────────────────────────
            if not self._stop_flag.is_set():
                self._on_progress(done, total, "", "Building search index…")
                rebuild_idf(conn)
                conn.commit()

            finish_training_session(session_id, done, total, conn=conn)
            conn.commit()
            stats = get_db_stats()
            self._on_done(stats)

        except Exception as exc:
            msg = str(exc)
            try:
                finish_training_session(session_id, done, total, error=msg, conn=conn)
                conn.commit()
            except Exception:
                pass
            self._on_error(msg)
        finally:
            conn.close()

    # ── Confluence pagination ─────────────────────────────────────────────────
    def _count_pages(self, client, space_key: str) -> int:
        try:
            params = {"limit": 1, "expand": ""}
            if space_key:
                params["spaceKey"] = space_key
            data = client._get("/wiki/rest/api/content", params)
            size  = data.get("size", 0)
            total = data.get("totalSize", size)
            return total or size
        except Exception:
            return 0

    def _fetch_page_batch(self, client, space_key: str,
                           start: int, limit: int) -> list:
        try:
            params = {
                "type":   "page",
                "start":  start,
                "limit":  limit,
                "expand": (
                    "body.storage,space,version,"
                    "history.createdBy,history.lastUpdated"
                ),
                "status": "current",
            }
            if space_key:
                params["spaceKey"] = space_key
            data = client._get("/wiki/rest/api/content", params)
            return data.get("results", [])
        except Exception:
            return []

    # ── Normalise raw Confluence page → our page dict ─────────────────────────
    @staticmethod
    def _normalise(raw: dict, client) -> dict:
        from confluence_kb import _strip_html
        page_id  = raw.get("id", "")
        title    = raw.get("title", "Untitled")
        sp       = raw.get("space", {})
        sp_key   = sp.get("key", client.space_key or "")
        url      = f"{client._origin}/wiki/spaces/{sp_key}/pages/{page_id}"
        raw_html = raw.get("body", {}).get("storage", {}).get("value", "")
        body     = _strip_html(raw_html)

        # ── Attribution ───────────────────────────────────────────────────────
        author      = ""
        last_editor = ""
        last_edited = ""
        try:
            import datetime as _dt
            history = raw.get("history", {})
            cb      = history.get("createdBy", {})
            author  = cb.get("displayName", "") or cb.get("username", "")
            lu = history.get("lastUpdated", {})
            if lu:
                by          = lu.get("by", {})
                last_editor = by.get("displayName", "") or by.get("username", "")
                when        = lu.get("when", "")
                if when:
                    try:
                        dt          = _dt.datetime.fromisoformat(when.replace("Z", "+00:00"))
                        last_edited = dt.strftime("%d %b %Y")
                    except Exception:
                        last_edited = when[:10]
            if not last_editor:
                ver         = raw.get("version", {})
                by          = ver.get("by", {})
                last_editor = by.get("displayName", "") or by.get("username", "")
                when        = ver.get("when", "")
                if when and not last_edited:
                    try:
                        dt          = _dt.datetime.fromisoformat(when.replace("Z", "+00:00"))
                        last_edited = dt.strftime("%d %b %Y")
                    except Exception:
                        last_edited = when[:10]
        except Exception:
            pass

        return {
            "id":          page_id,
            "title":       title,
            "url":         url,
            "space_key":   sp_key,
            "body_text":   body,
            "author":      author,
            "last_editor": last_editor,
            "last_edited": last_edited,
            "excerpt":     body[:200],
        }