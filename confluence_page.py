# confluence_page.py
# ══════════════════════════════════════════════════════════════════════════════
#  CONFLUENCE KB PAGE  —  Compact Tabbed: Knowledge Base  |  AI Training Centre
#  Local-First architecture: removed bulky header to save vertical space.
# ══════════════════════════════════════════════════════════════════════════════
import tkinter as tk
from tkinter import ttk

from confluence_kb import KBPanel
from train_panel   import TrainPanel
from kb_local_search import get_db_stats

# ── Palette ───────────────────────────────────────────────────────────────────
BG_BASE      = "#F5EFE3"
BG_SURFACE   = "#EDE4D3"
BG_ELEVATED  = "#E3D7C3"
TERRA        = "#A0522D"
TERRA_BRIGHT = "#C06030"
TERRA_DEEP   = "#7A3B1E"
TERRA_TINT   = "#F0E6D8"
TERRA_MUTED  = "#8B6248"
TEXT_PRIMARY = "#2C1F0E"
TEXT_INVERSE = "#FAF6EE"
TEXT_MUTED   = "#9B7D60"
TEXT_GHOST   = "#C4A882"
BORDER_TERRA = "#A0522D"
BORDER_MID   = "#C4A882"
SUCCESS      = "#2A7A50"

FONT_UI_BOLD = ("Segoe UI",  9, "bold")
FONT_UI      = ("Segoe UI",  9)
FONT_SMALL   = ("Segoe UI",  8)
FONT_BADGE   = ("Segoe UI",  8, "italic")


class _TabBtn(tk.Frame):
    def __init__(self, parent, text: str, icon: str,
                 on_click, active: bool = False, **kw):
        super().__init__(parent, bg=BG_SURFACE, cursor="hand2", **kw)
        self._on_click = on_click
        self._active   = active
        self._text     = text
        self._icon     = icon

        self._inner = tk.Frame(self, bg=BG_SURFACE)
        self._inner.pack(fill="both", expand=True, padx=1, pady=1)

        self._label = tk.Label(
            self._inner,
            text=f" {icon}  {text} ",
            font=FONT_UI_BOLD if active else FONT_UI,
            bg=TERRA if active else BG_SURFACE,
            fg=TEXT_INVERSE if active else TEXT_MUTED,
            padx=10, pady=6, cursor="hand2", # Reduced padding
        )
        self._label.pack(fill="both", expand=True)
        self._accent = tk.Frame(
            self, bg=TERRA if active else BG_SURFACE, height=2)
        self._accent.pack(fill="x", side="bottom")

        for w in (self, self._inner, self._label):
            w.bind("<Button-1>", self._click)
            w.bind("<Enter>",    self._hover_on)
            w.bind("<Leave>",    self._hover_off)

    def _click(self, _=None):
        self._on_click()

    def _hover_on(self, _=None):
        if not self._active:
            self._label.config(bg=TERRA_TINT, fg=TEXT_PRIMARY)

    def _hover_off(self, _=None):
        if not self._active:
            self._label.config(bg=BG_SURFACE, fg=TEXT_MUTED)

    def set_active(self, active: bool):
        self._active = active
        self._label.config(
            bg=TERRA if active else BG_SURFACE,
            fg=TEXT_INVERSE if active else TEXT_MUTED,
            font=FONT_UI_BOLD if active else FONT_UI,
        )
        self._accent.config(bg=TERRA if active else BG_SURFACE)

    def set_badge(self, text: str, color: str = SUCCESS):
        self._label.config(text=f" {self._icon}  {self._text}  {text} ")


class _LocalIndexStrip(tk.Frame):
    """Compact banner showing local DB status."""
    def __init__(self, parent, on_train_click, **kw):
        super().__init__(parent, bg=TERRA_TINT, **kw)
        self._on_train_click = on_train_click

        self._icon_lbl = tk.Label(self, text="⬤", font=("Segoe UI", 8),
                                   bg=TERRA_TINT, fg=TEXT_GHOST)
        self._icon_lbl.pack(side="left", padx=(10, 4), pady=4)

        self._status_var = tk.StringVar(value="Local index status...")
        tk.Label(self, textvariable=self._status_var,
                 font=FONT_SMALL, bg=TERRA_TINT, fg=TERRA_MUTED).pack(
            side="left", pady=4)

        tk.Button(
            self, text="→ Train Now",
            font=("Segoe UI", 7, "bold"),
            bg=TERRA_TINT, fg=TERRA,
            relief="flat", bd=0, cursor="hand2",
            activebackground=TERRA_TINT, activeforeground=TERRA_BRIGHT,
            command=on_train_click,
        ).pack(side="right", padx=10, pady=2)

    def refresh(self):
        try:
            stats = get_db_stats()
            pages = stats["page_count"]
            sess  = stats.get("last_session")
            if pages == 0:
                self._status_var.set("⚡ Index empty — using live Confluence API")
                self._icon_lbl.config(fg="#C06030")
            else:
                when = ""
                if sess and sess.get("finished_at"):
                    try:
                        import datetime
                        dt = datetime.datetime.fromisoformat(sess["finished_at"])
                        when = f"  ·  trained {dt.strftime('%d %b %H:%M')}"
                    except: pass
                self._status_var.set(f"✓ Local index active — {pages} pages{when}")
                self._icon_lbl.config(fg=SUCCESS)
        except:
            self._status_var.set("Local index status unknown")


class ConfluencePanel(tk.Frame):
    def __init__(self, parent, settings_loader=None, **kw):
        super().__init__(parent, bg=BG_BASE, **kw)
        self._settings_loader = settings_loader
        self._active_tab      = "kb"
        self._build()

    def _build(self):
        # ── Consolidated Tab Bar (Removed separate header row) ────────────────
        tab_bar = tk.Frame(self, bg=BG_SURFACE)
        tab_bar.pack(fill="x")

        # Tab: Knowledge Base
        self._tab_kb = _TabBtn(
            tab_bar, "Knowledge Base", "🔍",
            on_click=lambda: self._switch_tab("kb"),
            active=True)
        self._tab_kb.pack(side="left")

        # Tab: Training
        self._tab_train = _TabBtn(
            tab_bar, "AI Training", "🧠",
            on_click=lambda: self._switch_tab("train"),
            active=False)
        self._tab_train.pack(side="left")

        # Right-side Status Pill (replaces the header pill)
        self._header_pill = tk.Label(
            tab_bar, text="",
            font=("Segoe UI", 7, "bold"),
            bg=BG_SURFACE, fg=TEXT_GHOST,
            padx=10
        )
        self._header_pill.pack(side="right", fill="y")

        tk.Frame(self, bg=BORDER_MID, height=1).pack(fill="x")

        # ── Content Host ──────────────────────────────────────────────────────
        self._host = tk.Frame(self, bg=BG_BASE)
        self._host.pack(fill="both", expand=True)

        # KB Panel
        self._kb_frame = tk.Frame(self._host, bg=BG_BASE)
        self._index_strip = _LocalIndexStrip(
            self._kb_frame,
            on_train_click=lambda: self._switch_tab("train"))
        self._index_strip.pack(fill="x")

        self._kb = KBPanel(self._kb_frame,
                            use_local_first=True,
                            settings_loader=self._settings_loader)
        self._kb.pack(fill="both", expand=True)

        # Train Panel
        self._train_frame = tk.Frame(self._host, bg=BG_BASE)
        self._train_panel = TrainPanel(
            self._train_frame,
            settings_loader=self._settings_loader)
        self._train_panel.pack(fill="both", expand=True)

        self._kb.on_client_ready = self._on_client_ready
        self._kb_frame.pack(fill="both", expand=True)
        self._refresh_header_pill()

    def _switch_tab(self, tab: str):
        if tab == self._active_tab: return
        self._active_tab = tab

        self._tab_kb.set_active(tab == "kb")
        self._tab_train.set_active(tab == "train")

        for f in (self._kb_frame, self._train_frame):
            f.pack_forget()

        if tab == "kb":
            self._index_strip.refresh()
            self._kb_frame.pack(fill="both", expand=True)
        else:
            self._train_panel._refresh_stats()
            self._train_frame.pack(fill="both", expand=True)
        
        self._refresh_header_pill()

    def _on_client_ready(self, client):
        self._train_panel.attach_client(client)
        self._train_tab_badge()

    def _train_tab_badge(self):
        try:
            stats = get_db_stats()
            if stats["page_count"] == 0:
                self._tab_train.set_badge("●", color="#C06030")
        except: pass

    def _refresh_header_pill(self):
        try:
            stats = get_db_stats()
            pages = stats["page_count"]
            if pages:
                self._header_pill.config(text=f"● {pages} PAGES INDEXED", fg=SUCCESS)
            else:
                self._header_pill.config(text="● LIVE SEARCH", fg=TERRA_BRIGHT)
        except: pass

    def show(self):
        self._index_strip.refresh()
        self._refresh_header_pill()

    def autosave(self):
        pass