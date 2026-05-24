# groq_page.py
import tkinter as tk
from tkinter import ttk, messagebox
import http.client
import json
import ssl
import threading
import os
# ── Config imports ─────────────────────────────────────────────────────────────
from config import (
    THEME_BG, THEME_ACCENT, TEXT_COLOR,
    FONT_BODY, FONT_BOLD, FONT_HEADER, FONT_SMALL,
)
from settings_store import load_settings
# ══════════════════════════════════════════════════════════════════════════════
#  THEME CONSTANTS  —  Savannah Light Brown Palette
# ══════════════════════════════════════════════════════════════════════════════
BG_BASE         = "#F5EFE3"
BG_SURFACE      = "#EDE4D3"
BG_ELEVATED     = "#E3D7C3"
BG_INPUT        = "#FAF6EE"
BG_OUTPUT       = "#F8F3E8"
TERRA           = "#A0522D"
TERRA_BRIGHT    = "#C06030"
TERRA_MUTED     = "#8B6248"
TERRA_TINT      = "#A0522D18"
TEXT_PRIMARY    = "#2C1F0E"
TEXT_SECONDARY  = "#6B4F35"
TEXT_MUTED      = "#9B7D60"
TEXT_GHOST      = "#C4A882"
TEXT_INVERSE    = "#FAF6EE"
MODE_BLUE       = "#2E6DA4"
MODE_BLUE_LIGHT = "#D8E8F5"
MODE_GREEN      = "#2A7A50"
MODE_GREEN_LIGHT= "#D5EDE2"
BORDER_SUBTLE   = "#D9C9B0"
BORDER_MID      = "#C4A882"
BORDER_TERRA    = "#A0522D"
SUCCESS         = "#2A7A50"
WARNING         = "#A06010"
ERROR           = "#B03030"
FONT_DISPLAY    = ("Georgia",      13, "bold")
FONT_LABEL      = ("Consolas",      8, "bold")
FONT_BODY_UI    = ("Segoe UI",      9)
FONT_BODY_MED   = ("Segoe UI",      9, "bold")
FONT_MONO_OUT   = ("Consolas",     10)
FONT_BTN        = ("Segoe UI",      9, "bold")
FONT_MICRO      = ("Segoe UI",      7)
FONT_BADGE      = ("Segoe UI",      8, "italic")
# ══════════════════════════════════════════════════════════════════════════════
#  MODE DEFINITIONS
# ══════════════════════════════════════════════════════════════════════════════
MODES = {
    "first_response": {
        "label":       "First Response",
        "emoji":       "⚡",
        "description": "Draft the initial reply to a newly raised ticket",
        "color":       MODE_BLUE,
        "color_glow":  MODE_BLUE_LIGHT,
        "color_light": MODE_BLUE_LIGHT,
        "prompt_hint": (
            "Draft a FIRST RESPONSE to this Freshservice support ticket. "
            "Acknowledge receipt warmly, confirm the request is being looked into, "
            "and assure the customer an update will follow as soon as possible. "
            "Write ONE short paragraph only. "
            "Begin with 'Thank you for getting in touch with us.' "
            "Do NOT address the customer by name. "
            "Do NOT refer to the customer in the third person (no 'the customer', no 'they'). "
            "Write directly to the reader using 'you/your' where a personal reference is needed, "
            "but keep such references minimal. "
            "No salutation. No sign-off. No bullet points. No subject line."
        ),
    },
    "resolution_remarks": {
        "label":       "Resolution Remarks",
        "emoji":       "✅",
        "description": "Summarise how the issue was resolved and close the ticket",
        "color":       MODE_GREEN,
        "color_glow":  MODE_GREEN_LIGHT,
        "color_light": MODE_GREEN_LIGHT,
        "prompt_hint": (
            "Draft RESOLUTION REMARKS to close this Freshservice support ticket. "
            "State clearly and directly what action was taken (e.g. 'Business Photos have been Updated.', "
            "'Payment Reconciliation done.', 'Loan limit has been updated.'). "
            "Then add one warm closing sentence reassuring the customer of continued support, "
            "such as 'We value you and are committed to ensuring you have the best experience with us.' "
            "Write ONE short paragraph only. "
            "Do NOT address the customer by name. "
            "Do NOT refer to the customer in the third person (no 'the customer', no 'they'). "
            "No salutation. No sign-off. No bullet points. No subject line."
        ),
    },
}
# ══════════════════════════════════════════════════════════════════════════════
#  AI CLIENT
# ══════════════════════════════════════════════════════════════════════════════
GROQ_HOST = "api.groq.com"
GROQ_PATH = "/openai/v1/chat/completions"
_HEADERS  = {
    "Content-Type":    "application/json",
    "Accept":          "application/json",
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection":      "keep-alive",
}
class GroqClient:
    def generate_response(self, api_key: str, model: str, prompt: str) -> str:
        body_bytes = json.dumps({
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a professional support agent at 4G Capital. "
                        "Staff submit Freshservice tickets about customer issues and you draft the replies. "
                        "Your replies are sent directly to customers, so write as if addressing them. "
                        "STRICT FORMATTING RULES — violating any of these is unacceptable:\n"
                        "  • Output ONE short paragraph only — no bullet points, no numbered lists.\n"
                        "  • NO subject line (e.g. 'Subject: …').\n"
                        "  • NO salutation (e.g. 'Dear …', 'Hello …', 'Hi …').\n"
                        "  • NO sign-off or signature (e.g. 'Best regards', 'Yours sincerely').\n"
                        "  • Do NOT refer to 'the customer' or use third-person references.\n"
                        "  • Write action-first: state what was done or what is happening.\n"
                        "  • Keep the tone warm, professional, and concise.\n"
                        "  • Begin directly with the action or acknowledgement statement."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.7,
            "max_tokens":  700,
        }).encode("utf-8")
        headers = dict(_HEADERS)
        headers["Authorization"]  = f"Bearer {api_key.strip()}"
        headers["Content-Length"] = str(len(body_bytes))
        ctx = ssl.create_default_context()
        try:
            conn = http.client.HTTPSConnection(GROQ_HOST, timeout=20, context=ctx)
            conn.request("POST", GROQ_PATH, body=body_bytes, headers=headers)
            resp     = conn.getresponse()
            raw_resp = resp.read().decode("utf-8", errors="replace")
        except OSError as exc:
            raise ConnectionError(f"Network error: {exc}")
        finally:
            try:
                conn.close()
            except Exception:
                pass
        if resp.status not in (200, 201):
            raise ConnectionError(f"Groq API error {resp.status}: {raw_resp[:300]}")
        envelope = json.loads(raw_resp)
        return envelope["choices"][0]["message"]["content"]
# ══════════════════════════════════════════════════════════════════════════════
#  TOOLTIP
# ══════════════════════════════════════════════════════════════════════════════
class Tooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text   = text
        self.tip    = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)
    def _show(self, _=None):
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + 20
        self.tip = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tk.Label(
            tw, text=self.text, bg=BG_ELEVATED, fg=TEXT_PRIMARY,
            font=FONT_MICRO, relief="flat", bd=1, padx=8, pady=4,
            highlightbackground=BORDER_TERRA, highlightthickness=1
        ).pack()
    def _hide(self, _=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None
# ══════════════════════════════════════════════════════════════════════════════
#  REUSABLE COMPONENTS
# ══════════════════════════════════════════════════════════════════════════════
def _section_label(parent, text, bg=BG_SURFACE):
    row = tk.Frame(parent, bg=bg)
    row.pack(fill="x", padx=16, pady=(12, 4))
    tk.Label(row, text=text, font=FONT_LABEL, bg=bg, fg=TEXT_MUTED).pack(side="left")
    tk.Frame(row, bg=BORDER_MID, height=1).pack(
        side="left", fill="x", expand=True, padx=(8, 0), pady=3)
def _input_field(parent, label, height=5, placeholder="", bg=BG_INPUT):
    wrap = tk.Frame(parent, bg=parent.cget("bg"))
    wrap.pack(fill="x", padx=16, pady=(0, 10))
    tk.Label(wrap, text=label, font=FONT_LABEL,
             bg=wrap.cget("bg"), fg=TEXT_MUTED).pack(anchor="w", pady=(0, 4))
    border = tk.Frame(wrap, bg=BORDER_MID, padx=1, pady=1)
    border.pack(fill="x")
    txt = tk.Text(
        border, height=height, font=FONT_BODY_UI, wrap="word",
        bg=bg, fg=TEXT_PRIMARY,
        bd=0, relief="flat",
        insertbackground=TERRA,
        padx=12, pady=10,
        selectbackground=TERRA_MUTED, selectforeground=TEXT_INVERSE,
    )
    txt.pack(fill="x")
    def _focus_in(_):
        border.config(bg=TERRA_MUTED)
        if txt.get("1.0", tk.END).strip() == placeholder:
            txt.delete("1.0", tk.END)
            txt.config(fg=TEXT_PRIMARY)
    def _focus_out(_):
        border.config(bg=BORDER_MID)
        if not txt.get("1.0", tk.END).strip():
            txt.insert("1.0", placeholder)
            txt.config(fg=TEXT_GHOST)
    if placeholder:
        txt.insert("1.0", placeholder)
        txt.config(fg=TEXT_GHOST)
        txt._placeholder = placeholder
    else:
        txt._placeholder = ""
    txt.bind("<FocusIn>",  _focus_in)
    txt.bind("<FocusOut>", _focus_out)
    return txt
def _get_text_value(txt_widget):
    val = txt_widget.get("1.0", tk.END).strip()
    if val == getattr(txt_widget, "_placeholder", ""):
        return ""
    return val
# ══════════════════════════════════════════════════════════════════════════════
#  MODE CARD
# ══════════════════════════════════════════════════════════════════════════════
class ModeCard(tk.Frame):
    def __init__(self, parent, mode_key, meta, on_select, **kw):
        super().__init__(
            parent,
            bg=BG_SURFACE, cursor="hand2",
            highlightbackground=BORDER_MID, highlightthickness=1,
            padx=0, pady=0, **kw
        )
        self.mode_key  = mode_key
        self.meta      = meta
        self.on_select = on_select
        self._selected = False
        inner = tk.Frame(self, bg=BG_SURFACE, padx=10, pady=8)
        inner.pack(fill="both", expand=True)
        self._icon = tk.Label(
            inner, text=meta["emoji"],
            font=("Segoe UI Symbol", 16), bg=BG_SURFACE, fg=meta["color"]
        )
        self._icon.pack()
        self._label = tk.Label(
            inner, text=meta["label"],
            font=("Segoe UI", 8, "bold"), bg=BG_SURFACE, fg=TEXT_SECONDARY
        )
        self._label.pack(pady=(2, 0))
        self._inner = inner
        self._all_widgets = [self, inner, self._icon, self._label]
        for w in self._all_widgets:
            w.bind("<Button-1>", self._click)
            w.bind("<Enter>",    self._hover_on)
            w.bind("<Leave>",    self._hover_off)
        Tooltip(self, meta["description"])
    def _click(self, _=None):
        self.on_select(self.mode_key)
    def _hover_on(self, _=None):
        if not self._selected:
            self._set_bg(self.meta["color_light"])
            self.config(highlightbackground=self.meta["color"])
    def _hover_off(self, _=None):
        if not self._selected:
            self._set_bg(BG_SURFACE)
            self.config(highlightbackground=BORDER_MID)
    def select(self):
        self._selected = True
        self._set_bg(self.meta["color_light"])
        self.config(highlightbackground=self.meta["color"], highlightthickness=2)
        self._label.config(fg=self.meta["color"])
    def deselect(self):
        self._selected = False
        self._set_bg(BG_SURFACE)
        self.config(highlightbackground=BORDER_MID, highlightthickness=1)
        self._label.config(fg=TEXT_SECONDARY)
    def _set_bg(self, color):
        for w in self._all_widgets:
            w.config(bg=color)
# ══════════════════════════════════════════════════════════════════════════════
#  MAIN PANEL
# ══════════════════════════════════════════════════════════════════════════════
class GroqPanel(tk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=BG_BASE, **kwargs)
        self.ai_client   = GroqClient()
        self._sel_mode   = None
        self._mode_cards = {}
        self._setup_ui()
    # ── UI BUILD ───────────────────────────────────────────────────────────────
    def _setup_ui(self):
        # ── Top header bar ─────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=BG_ELEVATED, height=48)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        logo_area = tk.Frame(hdr, bg=BG_ELEVATED)
        logo_area.pack(side="left", fill="y", padx=16)
        tk.Label(logo_area, text="GroqReply",
                 font=("Georgia", 13, "bold"),
                 bg=BG_ELEVATED, fg=TERRA).pack(side="left", pady=12)
        tk.Label(logo_area, text=" AI",
                 font=("Georgia", 13),
                 bg=BG_ELEVATED, fg=TEXT_SECONDARY).pack(side="left", pady=12)
        tk.Frame(hdr, bg=BORDER_TERRA, width=1).pack(side="left", fill="y", pady=8)
        tk.Label(hdr, text="  Freshservice Ticket Reply Assistant",
                 font=("Segoe UI", 9), bg=BG_ELEVATED, fg=TEXT_MUTED
                 ).pack(side="left", padx=12, pady=12)
        self._hdr_status = tk.Label(
            hdr, text="● Ready",
            font=("Segoe UI", 8, "bold"),
            bg=BG_ELEVATED, fg=SUCCESS)
        self._hdr_status.pack(side="right", padx=20)
        tk.Frame(self, bg=BORDER_TERRA, height=1).pack(fill="x")
        # ── Mode selector bar ────────────────────────────────────────────────
        mode_strip = tk.Frame(self, bg=BG_SURFACE)
        mode_strip.pack(fill="x")
        tk.Label(mode_strip, text="RESPONSE MODE", font=FONT_LABEL,
                 bg=BG_SURFACE, fg=TEXT_MUTED).pack(side="left", padx=(16, 12), pady=10)
        tk.Frame(mode_strip, bg=BORDER_MID, width=1).pack(side="left", fill="y", pady=6)
        cards_area = tk.Frame(mode_strip, bg=BG_SURFACE)
        cards_area.pack(side="left", fill="y", padx=10, pady=6)
        for key, meta in MODES.items():
            card = ModeCard(cards_area, key, meta, self._on_mode_select)
            card.pack(side="left", padx=4)
            self._mode_cards[key] = card
        self._mode_badge_var = tk.StringVar(value="Select a mode to get started")
        self._mode_badge = tk.Label(
            mode_strip, textvariable=self._mode_badge_var,
            font=FONT_BADGE, bg=BG_SURFACE, fg=TEXT_MUTED, anchor="e", padx=16)
        self._mode_badge.pack(side="right", fill="y")
        tk.Frame(self, bg=BORDER_MID, height=1).pack(fill="x")
        # ── Two-column body ─────────────────────────────────────────────────
        body = tk.PanedWindow(
            self, orient=tk.HORIZONTAL,
            bg=BORDER_TERRA, sashwidth=4,
            sashpad=0, sashrelief="flat", handlesize=0,
        )
        body.pack(fill="both", expand=True)
        self._left_outer = tk.Frame(body, bg=BG_SURFACE)
        body.add(self._left_outer, stretch="always", minsize=320)
        self._right_outer = tk.Frame(body, bg=BG_BASE)
        body.add(self._right_outer, stretch="always", minsize=320)
        self._build_left(self._left_outer)
        self._build_right_ticket(self._right_outer)
        self.update_idletasks()
        body.after(50, lambda: body.sash_place(0, body.winfo_width() // 2, 0))
    # ── LEFT INPUT PANEL ──────────────────────────────────────────────────────
    def _build_left(self, parent):
        lbl_bar = tk.Frame(parent, bg=BG_SURFACE)
        lbl_bar.pack(fill="x", padx=16, pady=(14, 0))
        tk.Label(lbl_bar, text="INPUT", font=FONT_LABEL,
                 bg=BG_SURFACE, fg=TERRA).pack(side="left")
        tk.Frame(lbl_bar, bg=BORDER_TERRA, height=1).pack(
            side="left", fill="x", expand=True, padx=(8, 0), pady=5)
        canvas = tk.Canvas(parent, bg=BG_SURFACE, highlightthickness=0, bd=0)
        sb = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(fill="both", expand=True)
        inner = tk.Frame(canvas, bg=BG_SURFACE)
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig(win_id, width=e.width))
        tk.Frame(inner, bg=BG_SURFACE, height=8).pack()
        _section_label(inner, "TICKET CONTENT or Subject", bg=BG_SURFACE)
        self.ticket_text = _input_field(
            inner, "PASTE TICKET TEXT",
            height=12,
            placeholder="Paste the Freshservice ticket content or Subject here…",
            bg=BG_INPUT
        )
        _section_label(inner, "ADDITIONAL CONTEXT  (optional)", bg=BG_SURFACE)
        self.custom_context = _input_field(
            inner, "EXTRA NOTES / INSTRUCTIONS",
            height=4,
            placeholder="Special instructions, or any relevant context…",
            bg=BG_INPUT
        )
        tk.Frame(inner, bg=BG_SURFACE, height=14).pack()
    # ── RIGHT PANEL ───────────────────────────────────────────────────────────
    def _build_right_ticket(self, parent):
        self._ticket_panel = tk.Frame(parent, bg=BG_BASE)
        self._ticket_panel.pack(fill="both", expand=True)
        out_hdr = tk.Frame(self._ticket_panel, bg=BG_BASE)
        out_hdr.pack(fill="x", padx=16, pady=(14, 0))
        tk.Label(out_hdr, text="OUTPUT", font=FONT_LABEL,
                 bg=BG_BASE, fg=TERRA).pack(side="left")
        tk.Frame(out_hdr, bg=BORDER_TERRA, height=1).pack(
            side="left", fill="x", expand=True, padx=(8, 0), pady=5)
        tk.Frame(self._ticket_panel, bg=BORDER_SUBTLE, height=1).pack(
            fill="x", padx=16)
        btn_area = tk.Frame(self._ticket_panel, bg=BG_BASE, pady=10)
        btn_area.pack(fill="x")
        self.btn_gen = tk.Button(
            btn_area, text="▶   Generate Reply",
            bg=TERRA, fg=TEXT_INVERSE,
            font=FONT_BTN, relief="flat", cursor="hand2",
            pady=9, bd=0,
            activebackground=TERRA_BRIGHT, activeforeground=TEXT_INVERSE,
            command=self.generate_ai_reply
        )
        self.btn_gen.pack(fill="x", padx=16)
        self.btn_gen.bind("<Enter>", lambda _: self.btn_gen.config(bg=TERRA_BRIGHT))
        self.btn_gen.bind("<Leave>", lambda _: self.btn_gen.config(bg=TERRA))
        Tooltip(self.btn_gen, "Send ticket to AI and generate reply")
        tk.Frame(self._ticket_panel, bg=BORDER_SUBTLE, height=1).pack(
            fill="x", padx=16, pady=(0, 2))
        act = tk.Frame(self._ticket_panel, bg=BG_BASE)
        act.pack(fill="x", padx=16, pady=(6, 0))
        self._copy_btn = tk.Button(
            act, text="⎘  Copy",
            bg=BG_ELEVATED, fg=TEXT_PRIMARY,
            font=FONT_BTN, relief="flat", cursor="hand2",
            padx=12, pady=5, bd=0,
            activebackground=TERRA_MUTED, activeforeground=TEXT_INVERSE,
            command=self._copy_to_clipboard
        )
        self._copy_btn.pack(side="left", padx=(0, 6))
        self._copy_btn.bind("<Enter>",
            lambda _: self._copy_btn.config(bg=TERRA_MUTED, fg=TEXT_INVERSE))
        self._copy_btn.bind("<Leave>",
            lambda _: self._copy_btn.config(bg=BG_ELEVATED, fg=TEXT_PRIMARY))
        self._clear_btn = tk.Button(
            act, text="✕  Clear",
            bg=BG_ELEVATED, fg=TEXT_MUTED,
            font=FONT_BTN, relief="flat", cursor="hand2",
            padx=12, pady=5, bd=0,
            activebackground=BG_ELEVATED, activeforeground=ERROR,
            command=self._clear_reply
        )
        self._clear_btn.pack(side="left")
        self._clear_btn.bind("<Enter>",
            lambda _: self._clear_btn.config(fg=ERROR))
        self._clear_btn.bind("<Leave>",
            lambda _: self._clear_btn.config(fg=TEXT_MUTED))
        status_row = tk.Frame(self._ticket_panel, bg=BG_BASE)
        status_row.pack(fill="x", padx=16, pady=(8, 4))
        self._spinner_var = tk.StringVar(value="")
        tk.Label(status_row, textvariable=self._spinner_var,
                 font=("Segoe UI", 13), bg=BG_BASE, fg=TERRA).pack(side="left")
        self.status_var = tk.StringVar(value="Awaiting input")
        tk.Label(status_row, textvariable=self.status_var,
                 font=("Segoe UI", 8), bg=BG_BASE, fg=TEXT_MUTED
                 ).pack(side="left", padx=4)
        self._char_var = tk.StringVar(value="")
        tk.Label(status_row, textvariable=self._char_var,
                 font=FONT_LABEL, bg=BG_BASE, fg=TEXT_MUTED).pack(side="right")
        self._watermark_var = tk.StringVar(value="")
        self._watermark_lbl = tk.Label(
            self._ticket_panel, textvariable=self._watermark_var,
            font=FONT_BADGE, bg=BG_BASE, fg=TEXT_GHOST, anchor="e", padx=16)
        self._watermark_lbl.pack(fill="x")
        out_frame = tk.Frame(self._ticket_panel, bg=BG_BASE)
        out_frame.pack(fill="both", expand=True, padx=16, pady=(4, 16))
        self._reply_border = tk.Frame(out_frame, bg=BORDER_MID, padx=1, pady=1)
        self._reply_border.pack(fill="both", expand=True)
        out_card = tk.Frame(self._reply_border, bg=BG_OUTPUT)
        out_card.pack(fill="both", expand=True)
        self._accent_line = tk.Frame(out_card, bg=BORDER_MID, height=3)
        self._accent_line.pack(fill="x")
        self.reply_text = tk.Text(
            out_card, font=FONT_MONO_OUT, wrap="word",
            bg=BG_OUTPUT, fg=TEXT_PRIMARY,
            padx=20, pady=18, relief="flat", bd=0,
            insertbackground=TERRA, state="disabled",
            spacing1=4, spacing3=4,
            selectbackground=TERRA_MUTED, selectforeground=TEXT_INVERSE,
        )
        reply_sb = ttk.Scrollbar(out_card, command=self.reply_text.yview)
        self.reply_text.configure(yscrollcommand=reply_sb.set)
        reply_sb.pack(side="right", fill="y")
        self.reply_text.pack(fill="both", expand=True)
        self._set_reply_placeholder()
        self._spinner_frames = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
        self._spin_idx = 0
        self._spinning = False
    # ── MODE SELECTION ────────────────────────────────────────────────────────
    def _on_mode_select(self, mode_key: str):
        for k, card in self._mode_cards.items():
            card.deselect() if k != mode_key else card.select()
        self._sel_mode = mode_key
        meta = MODES[mode_key]
        self._mode_badge_var.set(f"{meta['emoji']}  {meta['description']}")
        self._mode_badge.config(fg=meta["color"])
        self._show_ticket_panel(meta)
    def _show_ticket_panel(self, meta: dict):
        self._ticket_panel.pack(fill="both", expand=True)
        self._watermark_var.set(f"{meta['emoji']}  {meta['label']}")
        self._watermark_lbl.config(fg=meta["color"])
        self._reply_border.config(bg=meta["color"])
        self._accent_line.config(bg=meta["color"])
    # ── PLACEHOLDER ───────────────────────────────────────────────────────────
    def _set_reply_placeholder(self):
        self.reply_text.config(state="normal")
        self.reply_text.delete("1.0", tk.END)
        self.reply_text.insert(tk.END, (
            "\n\n"
            "  Ready to generate.\n\n"
            "  ① Select a response mode above\n\n"
            "  ② Paste the Freshservice ticket on the left\n\n"
            "  ③ Optionally add extra context or notes\n\n"
            "  ④ Press  ▶ Generate Reply"
        ))
        self.reply_text.config(state="disabled", fg=TEXT_GHOST)
        self._reply_border.config(bg=BORDER_MID)
        self._accent_line.config(bg=BORDER_MID)
    # ── GENERATE ──────────────────────────────────────────────────────────────
    def generate_ai_reply(self):
        settings = load_settings()
        api_key  = settings.get("api_key")
        model    = settings.get("groq_model")
        if not api_key:
            messagebox.showwarning(
                "API Key Missing",
                "Please enter your Groq API Key in Settings.",
                parent=self
            )
            return
        if not self._sel_mode:
            messagebox.showinfo(
                "No Mode Selected",
                "Please select ⚡ First Response or ✅ Resolution Remarks.",
                parent=self
            )
            return
        ticket_body = _get_text_value(self.ticket_text)
        if not ticket_body:
            messagebox.showinfo(
                "No Ticket Content",
                "Please paste the ticket content before generating a reply.",
                parent=self
            )
            return
        context = _get_text_value(self.custom_context)
        self._start_spinner()
        self.btn_gen.config(state="disabled", bg=TERRA_MUTED)
        self._hdr_status.config(text="● Generating…", fg=WARNING)
        threading.Thread(
            target=self._ai_thread,
            args=(api_key, model, self._sel_mode, ticket_body, context),
            daemon=True,
        ).start()
    def _ai_thread(self, api_key, model, mode_key, ticket_body, ctx):
        meta  = MODES[mode_key]
        parts = [f"TICKET CONTENT:\n{ticket_body}"]
        if ctx:
            parts.append(f"Additional context / instructions: {ctx}")
        parts.append(f"\n{meta['prompt_hint']}")
        prompt = "\n\n".join(parts)
        try:
            response = self.ai_client.generate_response(api_key, model, prompt)
            self.after(0, lambda r=response: self._update_ui_text(r))
        except Exception as e:
            self.after(0, lambda err=e: messagebox.showerror(
                "AI Error", f"Failed to connect:\n{err}", parent=self))
        finally:
            self.after(0, self._stop_spinner)
            self.after(0, lambda: self.btn_gen.config(state="normal", bg=TERRA))
            self.after(0, lambda: self.status_var.set("Done"))
            self.after(0, lambda: self._hdr_status.config(text="● Ready", fg=SUCCESS))
    # ── SPINNER ───────────────────────────────────────────────────────────────
    def _start_spinner(self):
        self._spinning = True
        self.status_var.set("AI is drafting your reply…")
        self._tick_spinner()
    def _stop_spinner(self):
        self._spinning = False
        self._spinner_var.set("")
    def _tick_spinner(self):
        if not self._spinning:
            return
        self._spinner_var.set(
            self._spinner_frames[self._spin_idx % len(self._spinner_frames)])
        self._spin_idx += 1
        self.after(80, self._tick_spinner)
    # ── REPLY HELPERS ─────────────────────────────────────────────────────────
    def _update_ui_text(self, text):
        self.reply_text.config(state="normal", fg=TEXT_PRIMARY)
        self.reply_text.delete("1.0", tk.END)
        self.reply_text.insert(tk.END, "\n" + text + "\n")
        self.reply_text.config(state="disabled")
        n_words = len(text.split())
        n_chars = len(text)
        self._char_var.set(f"{n_words} words  ·  {n_chars} chars")
        self.status_var.set("Reply generated")
    def _copy_to_clipboard(self):
        content = self.reply_text.get("1.0", tk.END).strip()
        if content:
            self.clipboard_clear()
            self.clipboard_append(content)
            old_text = self._copy_btn.cget("text")
            self._copy_btn.config(text="✓  Copied!", fg=SUCCESS, bg=BG_ELEVATED)
            self.after(2200, lambda: self._copy_btn.config(
                text=old_text, fg=TEXT_PRIMARY, bg=BG_ELEVATED))
            self.status_var.set("Copied to clipboard")
            self.after(2200, lambda: self.status_var.set("Done"))
    def _clear_reply(self):
        self._set_reply_placeholder()
        self._char_var.set("")
        self.status_var.set("Awaiting input")
    def show(self):
        self.pack(fill="both", expand=True)