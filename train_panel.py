# train_panel.py
# ══════════════════════════════════════════════════════════════════════════════
#  TRAINING PANEL  —  Manages local KB index with live progress feedback
# ══════════════════════════════════════════════════════════════════════════════
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import datetime

from kb_local_search import get_db_stats, get_last_training_session, clear_local_db

# ── Palette (matches confluence_kb.py) ───────────────────────────────────────
BG_BASE         = "#F5EFE3"
BG_SURFACE      = "#EDE4D3"
BG_ELEVATED     = "#E3D7C3"
BG_INPUT        = "#FAF6EE"
BG_OUTPUT       = "#F8F3E8"
TERRA           = "#A0522D"
TERRA_BRIGHT    = "#C06030"
TERRA_MUTED     = "#8B6248"
TERRA_DEEP      = "#7A3B1E"
TERRA_TINT      = "#F0E6D8"
TEXT_PRIMARY    = "#2C1F0E"
TEXT_SECONDARY  = "#6B4F35"
TEXT_MUTED      = "#9B7D60"
TEXT_GHOST      = "#C4A882"
TEXT_INVERSE    = "#FAF6EE"
BORDER_SUBTLE   = "#D9C9B0"
BORDER_MID      = "#C4A882"
BORDER_TERRA    = "#A0522D"
SUCCESS         = "#2A7A50"
WARNING         = "#A06010"
ERROR           = "#B03030"

FONT_LABEL   = ("Consolas",  8, "bold")
FONT_UI      = ("Segoe UI",  9)
FONT_UI_BOLD = ("Segoe UI",  9, "bold")
FONT_SMALL   = ("Segoe UI",  8)
FONT_MONO    = ("Consolas",  9)
FONT_TITLE   = ("Segoe UI", 12, "bold")
FONT_METRIC  = ("Consolas", 20, "bold")
FONT_BADGE   = ("Segoe UI",  8, "italic")


# ══════════════════════════════════════════════════════════════════════════════
#  METRIC CARD
# ══════════════════════════════════════════════════════════════════════════════
class _MetricCard(tk.Frame):
    def __init__(self, parent, label: str, value: str,
                 sub: str = "", accent: str = TERRA, **kw):
        super().__init__(parent, bg=BG_SURFACE,
                          relief="flat", padx=16, pady=12, **kw)
        tk.Frame(self, bg=accent, width=3).pack(side="left", fill="y")
        body = tk.Frame(self, bg=BG_SURFACE)
        body.pack(side="left", padx=(10, 0))
        self._val_var = tk.StringVar(value=value)
        self._sub_var = tk.StringVar(value=sub)
        tk.Label(body, text=label, font=FONT_LABEL,
                 bg=BG_SURFACE, fg=TEXT_MUTED, anchor="w").pack(anchor="w")
        tk.Label(body, textvariable=self._val_var, font=FONT_METRIC,
                 bg=BG_SURFACE, fg=TEXT_PRIMARY, anchor="w").pack(anchor="w")
        tk.Label(body, textvariable=self._sub_var, font=FONT_BADGE,
                 bg=BG_SURFACE, fg=TEXT_MUTED, anchor="w").pack(anchor="w")

    def set(self, value: str, sub: str = None):
        self._val_var.set(value)
        if sub is not None:
            self._sub_var.set(sub)


# ══════════════════════════════════════════════════════════════════════════════
#  TRAINING LOG (scrollable text widget)
# ══════════════════════════════════════════════════════════════════════════════
class _TrainLog(tk.Frame):
    def __init__(self, parent, height: int = 8, **kw):
        super().__init__(parent, bg=BG_SURFACE, **kw)
        border = tk.Frame(self, bg=BORDER_MID, padx=1, pady=1)
        border.pack(fill="both", expand=True)
        inner = tk.Frame(border, bg="#1A1208")
        inner.pack(fill="both", expand=True)
        self._txt = tk.Text(
            inner, height=height, font=FONT_MONO, wrap="none",
            bg="#F7CD9A", fg="#C4A882", bd=0, relief="flat",
            padx=10, pady=8, state="disabled",
            selectbackground=TERRA_MUTED)
        vsb = ttk.Scrollbar(inner, orient="vertical", command=self._txt.yview)
        self._txt.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self._txt.pack(fill="both", expand=True)
        # colour tags
        self._txt.tag_config("info",    foreground="#C4A882")
        self._txt.tag_config("ok",      foreground="#4ABA7A")
        self._txt.tag_config("warn",    foreground="#D4A040")
        self._txt.tag_config("err",     foreground="#E05050")
        self._txt.tag_config("dim",     foreground="#6B4F35")
        self._txt.tag_config("title",   foreground="#F0D8B8",
                             font=("Consolas", 9, "bold"))

    def log(self, msg: str, tag: str = "info"):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self._txt.config(state="normal")
        self._txt.insert(tk.END, f"[{ts}]  {msg}\n", tag)
        self._txt.see(tk.END)
        self._txt.config(state="disabled")

    def clear(self):
        self._txt.config(state="normal")
        self._txt.delete("1.0", tk.END)
        self._txt.config(state="disabled")


# ══════════════════════════════════════════════════════════════════════════════
#  TRAIN PANEL  —  main widget
# ══════════════════════════════════════════════════════════════════════════════
class TrainPanel(tk.Frame):
    """
    Embeddable frame.  Call  attach_client(confluence_client)  before
    the user hits Train, or set it lazily via the settings loader.
    """

    def __init__(self, parent, settings_loader=None, **kw):
        super().__init__(parent, bg=BG_BASE, **kw)
        self._settings_loader = settings_loader   # callable → dict
        self._client          = None
        self._trainer         = None
        self._training        = False
        self._spin_idx        = 0
        self._spin_frames     = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
        self._build()
        self._refresh_stats()

    # ── Public API ─────────────────────────────────────────────────────────────
    def attach_client(self, client):
        """Supply a ConfluenceClient so the panel can train."""
        self._client = client

    # ── Build UI ───────────────────────────────────────────────────────────────
    def _build(self):
        # ── Header ────────────────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=TERRA_DEEP, height=44)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="  🧠  AI Training Centre",
                 font=("Segoe UI", 11, "bold"),
                 bg=TERRA_DEEP, fg=TEXT_INVERSE,
                 anchor="w").pack(side="left", fill="y", padx=12)
        tk.Label(hdr,
                 text="Local-First Knowledge Index  —  Ultra-fast offline search",
                 font=("Segoe UI", 8, "italic"),
                 bg=TERRA_DEEP, fg=TEXT_GHOST,
                 anchor="e").pack(side="right", fill="y", padx=16)
        tk.Frame(self, bg=TERRA, height=2).pack(fill="x")

        # ── Metrics row ───────────────────────────────────────────────────────
        metrics_row = tk.Frame(self, bg=BG_BASE)
        metrics_row.pack(fill="x", padx=12, pady=(14, 4))

        self._card_pages = _MetricCard(
            metrics_row, "INDEXED PAGES", "—", "no local data yet",
            accent=TERRA)
        self._card_pages.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self._card_terms = _MetricCard(
            metrics_row, "VOCAB TERMS", "—", "TF-IDF index",
            accent=TERRA_MUTED)
        self._card_terms.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self._card_size = _MetricCard(
            metrics_row, "DB SIZE", "—", "local SQLite",
            accent=TERRA_DEEP)
        self._card_size.pack(side="left", fill="x", expand=True)

        # ── Last trained ──────────────────────────────────────────────────────
        info_row = tk.Frame(self, bg=BG_BASE)
        info_row.pack(fill="x", padx=12, pady=4)

        self._last_trained_var = tk.StringVar(value="Never trained")
        self._last_status_var  = tk.StringVar(value="")
        tk.Label(info_row, text="Last training: ",
                 font=FONT_SMALL, bg=BG_BASE, fg=TEXT_MUTED).pack(side="left")
        tk.Label(info_row, textvariable=self._last_trained_var,
                 font=("Segoe UI", 8, "bold"),
                 bg=BG_BASE, fg=TEXT_PRIMARY).pack(side="left")
        self._last_status_lbl = tk.Label(
            info_row, textvariable=self._last_status_var,
            font=FONT_BADGE, bg=BG_BASE, fg=SUCCESS)
        self._last_status_lbl.pack(side="left", padx=(10, 0))

        self._db_path_var = tk.StringVar(value="")
        tk.Label(info_row, textvariable=self._db_path_var,
                 font=("Consolas", 7), bg=BG_BASE,
                 fg=TEXT_GHOST).pack(side="right")

        tk.Frame(self, bg=BORDER_SUBTLE, height=1).pack(fill="x", padx=12, pady=6)

        # ── Progress bar + status ─────────────────────────────────────────────
        prog_row = tk.Frame(self, bg=BG_BASE)
        prog_row.pack(fill="x", padx=12, pady=(0, 4))

        self._spinner_var = tk.StringVar(value="")
        tk.Label(prog_row, textvariable=self._spinner_var,
                 font=("Segoe UI", 11), bg=BG_BASE, fg=TERRA).pack(side="left")

        self._progress_var = tk.StringVar(value="Ready to train")
        tk.Label(prog_row, textvariable=self._progress_var,
                 font=FONT_SMALL, bg=BG_BASE, fg=TEXT_SECONDARY).pack(
            side="left", padx=(6, 0))

        self._pct_var = tk.StringVar(value="")
        tk.Label(prog_row, textvariable=self._pct_var,
                 font=("Segoe UI", 8, "bold"),
                 bg=BG_BASE, fg=TERRA).pack(side="right")

        style = ttk.Style()
        style.configure("Train.Horizontal.TProgressbar",
                         troughcolor=BG_ELEVATED,
                         background=TERRA, thickness=8)
        self._pbar = ttk.Progressbar(
            self, orient="horizontal", mode="determinate",
            style="Train.Horizontal.TProgressbar")
        self._pbar.pack(fill="x", padx=12, pady=(0, 8))

        # ── Action buttons ────────────────────────────────────────────────────
        btn_row = tk.Frame(self, bg=BG_BASE)
        btn_row.pack(fill="x", padx=12, pady=(0, 10))

        _bc = dict(relief="flat", cursor="hand2", bd=0,
                   padx=16, pady=8, font=FONT_UI_BOLD)

        self._train_btn = tk.Button(
            btn_row, text="▶  Train Now",
            bg=TERRA, fg=TEXT_INVERSE,
            activebackground=TERRA_BRIGHT,
            command=self._start_training, **_bc)
        self._train_btn.pack(side="left", padx=(0, 8))
        self._train_btn.bind("<Enter>",
            lambda _: self._train_btn.config(bg=TERRA_BRIGHT))
        self._train_btn.bind("<Leave>",
            lambda _: self._train_btn.config(bg=TERRA))

        self._stop_btn = tk.Button(
            btn_row, text="■  Stop",
            bg=BG_ELEVATED, fg=TEXT_PRIMARY,
            activebackground=ERROR, activeforeground=TEXT_INVERSE,
            state="disabled",
            command=self._stop_training, **_bc)
        self._stop_btn.pack(side="left", padx=(0, 8))

        tk.Button(
            btn_row, text="↺  Refresh Stats",
            bg=BG_ELEVATED, fg=TEXT_PRIMARY,
            activebackground=TERRA_MUTED, activeforeground=TEXT_INVERSE,
            command=self._refresh_stats, **_bc).pack(side="left", padx=(0, 8))

        tk.Button(
            btn_row, text="🗑  Clear Index",
            bg=BG_ELEVATED, fg=TEXT_PRIMARY,
            activebackground=ERROR, activeforeground=TEXT_INVERSE,
            command=self._clear_index, **_bc).pack(side="right")

        # ── How it works info strip ───────────────────────────────────────────
        info_strip = tk.Frame(self, bg=TERRA_TINT)
        info_strip.pack(fill="x", padx=12, pady=(0, 8))
        tk.Label(
            info_strip,
            text=(
                "  🧠  How it works:  "
                "Train downloads every Confluence page into a local SQLite database.  "
                "Searches then run locally (< 50 ms) with TF-IDF cosine ranking.  "
                "The AI enriches answers using the local context — no live API calls needed."
            ),
            font=("Segoe UI", 8, "italic"),
            bg=TERRA_TINT, fg=TERRA_MUTED,
            wraplength=800, justify="left", anchor="w",
            padx=12, pady=8,
        ).pack(fill="x")

        tk.Frame(self, bg=BORDER_TERRA, height=1).pack(fill="x", padx=12, pady=(0, 8))

        # ── Training log ──────────────────────────────────────────────────────
        log_label_row = tk.Frame(self, bg=BG_BASE)
        log_label_row.pack(fill="x", padx=12)
        tk.Label(log_label_row, text="TRAINING LOG",
                 font=FONT_LABEL, bg=BG_BASE, fg=TEXT_MUTED,
                 anchor="w").pack(side="left")
        tk.Button(
            log_label_row, text="Clear log",
            font=("Segoe UI", 7), bg=BG_BASE, fg=TEXT_GHOST,
            relief="flat", bd=0, cursor="hand2",
            command=lambda: self._log.clear()).pack(side="right")

        self._log = _TrainLog(self, height=10)
        self._log.pack(fill="both", expand=True, padx=12, pady=(4, 12))

        self._log.log("Training Centre ready.", "dim")
        self._log.log("Click ▶ Train Now to index your Confluence space locally.", "dim")

    # ── Stats refresh ──────────────────────────────────────────────────────────
    def _refresh_stats(self):
        try:
            stats = get_db_stats()
            self._card_pages.set(
                str(stats["page_count"]),
                f"{stats['idf_terms']:,} vocab terms"
            )
            self._card_terms.set(f"{stats['idf_terms']:,}", "indexed terms")
            self._card_size.set(
                f"{stats['size_mb']} MB",
                f"at {stats['db_path'][-40:]}")
            self._db_path_var.set(f"DB: {stats['db_path']}")

            sess = stats.get("last_session")
            if sess:
                finished = sess.get("finished_at") or sess.get("started_at") or ""
                if finished:
                    try:
                        dt = datetime.datetime.fromisoformat(finished)
                        friendly = dt.strftime("%d %b %Y  %H:%M UTC")
                    except Exception:
                        friendly = finished[:16]
                else:
                    friendly = "In progress…"
                self._last_trained_var.set(friendly)
                status = sess.get("status", "")
                pages_done = sess.get("pages_done", 0)
                pages_total = sess.get("pages_total", 0)
                if status == "complete":
                    self._last_status_var.set(
                        f"✓  {pages_done}/{pages_total} pages  —  complete")
                    self._last_status_lbl.config(fg=SUCCESS)
                elif status == "error":
                    self._last_status_var.set(f"✗  {sess.get('error_msg','error')[:60]}")
                    self._last_status_lbl.config(fg=ERROR)
                elif status == "running":
                    self._last_status_var.set(f"⟳  {pages_done}/{pages_total}")
                    self._last_status_lbl.config(fg=WARNING)
            else:
                self._last_trained_var.set("Never")
                self._last_status_var.set("")
        except Exception as e:
            self._log.log(f"Stats error: {e}", "warn")

    # ── Training lifecycle ─────────────────────────────────────────────────────
    def _start_training(self):
        if self._training:
            return

        # Try to get/build a client
        client = self._client
        if client is None:
            if self._settings_loader:
                try:
                    self._build_client_from_settings()
                    client = self._client
                except Exception as exc:
                    messagebox.showerror("Settings Error", str(exc), parent=self)
                    return
            else:
                messagebox.showwarning(
                    "Not Connected",
                    "Please run ⚡ Test in the Knowledge Base tab first "
                    "to establish a Confluence connection.",
                    parent=self)
                return

        if client is None:
            return

        self._training = True
        self._train_btn.config(state="disabled", bg=TERRA_MUTED,
                                text="⟳  Training…")
        self._stop_btn.config(state="normal")
        self._pbar["value"] = 0
        self._log.clear()
        self._log.log("═" * 50, "dim")
        self._log.log("▶  Training started", "title")
        self._log.log(f"   Space   : {client.space_key or 'all'}", "dim")
        self._log.log(f"   Origin  : {client._origin}", "dim")
        self._log.log("═" * 50, "dim")

        from kb_trainer import KBTrainer
        self._trainer = KBTrainer(
            client,
            on_progress = self._on_progress,
            on_done     = self._on_done,
            on_error    = self._on_error,
        )
        self._trainer.start()
        self._start_spinner()

    def _stop_training(self):
        if self._trainer:
            self._trainer.stop()
        self._log.log("■  Stop requested — finishing current page…", "warn")
        self._stop_btn.config(state="disabled")

    def _build_client_from_settings(self):
        if not self._settings_loader:
            raise RuntimeError("No settings loader configured.")
        s = self._settings_loader()
        from confluence_kb import ConfluenceClient
        self._client = ConfluenceClient(
            base_url  = s["conf_base_url"],
            username  = s["conf_username"],
            api_token = s["conf_api_token"],
        )

    # ── Progress / done / error callbacks (called from bg thread) ─────────────
    def _on_progress(self, done: int, total: int,
                      page_title: str, phase: str):
        self.after(0, lambda: self._ui_progress(done, total, page_title, phase))

    def _on_done(self, stats: dict):
        self.after(0, lambda: self._ui_done(stats))

    def _on_error(self, msg: str):
        self.after(0, lambda: self._ui_error(msg))

    # ── UI updates (main thread) ───────────────────────────────────────────────
    def _ui_progress(self, done: int, total: int,
                      page_title: str, phase: str):
        self._progress_var.set(
            f"{phase}  {page_title[:60]}" if page_title else phase)
        if total > 0:
            pct = int(done / total * 100)
            self._pbar["value"] = pct
            self._pct_var.set(f"{pct}%  ({done}/{total})")
        else:
            self._pbar["mode"] = "indeterminate"
        if page_title:
            self._log.log(f"[{done:>4}/{total}]  {page_title}", "info")

    def _ui_done(self, stats: dict):
        self._training = False
        self._stop_spinner()
        self._pbar["value"] = 100
        self._train_btn.config(state="normal", bg=TERRA, text="▶  Train Now")
        self._stop_btn.config(state="disabled")
        self._progress_var.set("Training complete ✓")
        self._pct_var.set("100%")
        self._log.log("═" * 50, "dim")
        self._log.log("✓  Training complete!", "ok")
        self._log.log(f"   Pages indexed : {stats['page_count']}", "ok")
        self._log.log(f"   Vocab terms   : {stats['idf_terms']:,}", "ok")
        self._log.log(f"   DB size       : {stats['size_mb']} MB", "ok")
        self._log.log(f"   DB path       : {stats['db_path']}", "dim")
        self._log.log("═" * 50, "dim")
        self._refresh_stats()
        messagebox.showinfo(
            "Training Complete",
            f"✓  {stats['page_count']} pages indexed successfully.\n\n"
            f"Searches now run locally (< 50 ms) — ultra-fast AI answers!",
            parent=self)

    def _ui_error(self, msg: str):
        self._training = False
        self._stop_spinner()
        self._train_btn.config(state="normal", bg=TERRA, text="▶  Train Now")
        self._stop_btn.config(state="disabled")
        self._progress_var.set("Training failed ✗")
        self._log.log("✗  Training error:", "err")
        for line in msg.splitlines():
            self._log.log(f"   {line}", "err")
        messagebox.showerror("Training Error", msg, parent=self)

    # ── Clear ──────────────────────────────────────────────────────────────────
    def _clear_index(self):
        if not messagebox.askyesno(
                "Clear Index",
                "Delete all locally indexed pages?\n\n"
                "You can re-train at any time. "
                "This will not affect Confluence itself.",
                parent=self):
            return
        try:
            clear_local_db()
            self._refresh_stats()
            self._log.log("🗑  Local index cleared.", "warn")
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)

    # ── Spinner ────────────────────────────────────────────────────────────────
    def _start_spinner(self):
        self._spin_active = True
        self._tick_spinner()

    def _stop_spinner(self):
        self._spin_active = False
        self._spinner_var.set("")

    def _tick_spinner(self):
        if not getattr(self, "_spin_active", False):
            return
        self._spinner_var.set(
            self._spin_frames[self._spin_idx % 10])
        self._spin_idx += 1
        self.after(80, self._tick_spinner)