import tkinter as tk
from tkinter import ttk, messagebox
from config import (
    THEME_BG, THEME_ACCENT, THEME_INPUT, THEME_BORDER,
    TEXT_COLOR, FONT_BODY, FONT_BOLD, FONT_HEADER, FONT_SMALL,
)
from settings_store import load_settings, save_settings

# ── Colours ───────────────────────────────────────────────────────────────
CARD_BG     = "#fdf6e3"
CARD_BORDER = "#c9a66b"
HDR_BG      = "#c9a66b"
HDR_FG      = "#3a2f24"
LINK_COLOR  = "#0066cc"
SCOPE_COLOR = "#d32f2f"

GROQ_MODELS = ["llama-3.1-8b-instant", "llama-3.3-70b-versatile", "gemma2-9b-it"]


class SettingsPanel(tk.Frame):
    def __init__(self, parent: tk.Misc, **kwargs):
        super().__init__(parent, bg=THEME_BG, **kwargs)
        self._cfg = load_settings()

        # Variables
        self._api_key_var    = tk.StringVar(value=self._cfg.get("api_key", ""))
        self._model_var      = tk.StringVar(value=self._cfg.get("groq_model", "llama-3.1-8b-instant"))
        self._monitor_var    = tk.BooleanVar(value=self._cfg.get("show_groq_monitor", "1") == "1")

        # Confluence variables — commented out; uncomment to re-enable
        # self._conf_user_var  = tk.StringVar(value=self._cfg.get("conf_username", ""))
        # self._conf_token_var = tk.StringVar(value=self._cfg.get("conf_api_token", ""))
        # self._conf_url_var   = tk.StringVar(value=self._cfg.get("conf_base_url", ""))

        self._txn_vars = {k: tk.StringVar(value=self._cfg.get(k, "")) for k in
                          ["BeyonicTxnId", "NetworkTxnId", "AirtelTxnId", "BankTxnId", "FlexipayTxnId"]}

        self._key_vis = False
        # self._tok_vis = False   # Confluence token visibility — commented out

        self._build()

    def _copy_link(self, url):
        self.clipboard_clear()
        self.clipboard_append(url)
        messagebox.showinfo("Copied", f"Link copied to clipboard:\n{url}")

    def show(self):
        """
        Required by main.py _toggle_settings.
        Brings the frame to the top and ensures it is visible.
        """
        self.lift()
        self.update_idletasks()

    def hide(self):
        w = self.master
        while w:
            if hasattr(w, "_toggle_settings"):
                w._toggle_settings()
                return
            w = getattr(w, "master", None)

    def _build(self):
        # Header
        hdr = tk.Frame(self, bg=HDR_BG)
        hdr.pack(fill="x")
        tk.Label(hdr, text="⚙  System Settings", font=FONT_HEADER,
                 bg=HDR_BG, fg=HDR_FG, padx=16, pady=10).pack(side="left")
        tk.Button(hdr, text="✖ Close", font=FONT_BOLD, bg=HDR_BG, fg=HDR_FG,
                  relief="flat", command=self.hide).pack(side="right", padx=10)

        container = tk.Canvas(self, bg=THEME_BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=container.yview)
        scrollable_frame = tk.Frame(container, bg=THEME_BG)

        scrollable_frame.bind("<Configure>",
                              lambda e: container.configure(scrollregion=container.bbox("all")))
        container.create_window((0, 0), window=scrollable_frame, anchor="nw")
        container.configure(yscrollcommand=scrollbar.set)

        container.pack(side="left", fill="both", expand=True, padx=14)
        scrollbar.pack(side="right", fill="y")

        # 2-Column Grid (was 3 — Confluence column removed)
        main_grid = tk.Frame(scrollable_frame, bg=THEME_BG)
        main_grid.pack(fill="x", pady=20, anchor="nw")

        # --- COL 0: GROQ ---
        groq_card = self._build_card(main_grid, "1. Groq API Config")
        groq_card.grid(row=0, column=0, sticky="nw", padx=10)
        self._add_groq_fields(groq_card)

        # --- COL 1: CONFLUENCE — commented out; uncomment to re-enable ---
        # conf_card = self._build_card(main_grid, "2. Confluence API (Read-Only)")
        # conf_card.grid(row=0, column=1, sticky="nw", padx=10)
        # self._add_conf_fields(conf_card)

        # --- COL 1 (was COL 2): TRANSACTIONS ---
        txn_card = self._build_card(main_grid, "2. Sample Transaction IDs")
        txn_card.grid(row=0, column=1, sticky="nw", padx=10)
        self._add_txn_fields(txn_card)

        # Footer
        footer = tk.Frame(self, bg=THEME_BG)
        footer.pack(fill="x", padx=14, pady=30)
        tk.Button(footer, text="💾 Save All Settings", font=FONT_BOLD,
                  bg=THEME_ACCENT, fg=TEXT_COLOR, padx=30, pady=10,
                  command=self._save_all, relief="flat").pack(side="left")

    def _build_card(self, parent, title):
        card = tk.Frame(parent, bg=CARD_BG,
                        highlightbackground=CARD_BORDER, highlightthickness=1)
        tk.Label(card, text=title, font=FONT_BOLD,
                 bg=HDR_BG, fg=HDR_FG, pady=8).pack(fill="x")
        return card

    def _add_groq_fields(self, card):
        body = tk.Frame(card, bg=CARD_BG, padx=15, pady=15)
        body.pack(fill="both", expand=True)

        tk.Label(body, text="API Key", font=FONT_BOLD, bg=CARD_BG).pack(anchor="w")
        tk.Button(body, text="🔗 console.groq.com", fg=LINK_COLOR, font=FONT_SMALL,
                  bg=CARD_BG, relief="flat",
                  command=lambda: self._copy_link("https://console.groq.com/keys")).pack(anchor="w")

        entry_f = tk.Frame(body, bg=CARD_BG)
        entry_f.pack(fill="x", pady=(5, 0))
        self._api_entry = tk.Entry(entry_f, textvariable=self._api_key_var,
                                   show="*", bg=THEME_INPUT, width=30)
        self._api_entry.pack(side="left", fill="x", expand=True)
        tk.Button(entry_f, text="👁", bg=CARD_BG,
                  command=self._toggle_api).pack(side="right")

        tk.Label(body, text="Model", font=FONT_BOLD, bg=CARD_BG).pack(anchor="w", pady=(15, 0))
        ttk.Combobox(body, textvariable=self._model_var,
                     values=GROQ_MODELS, width=28).pack(fill="x", pady=(5, 0))

        # ── Groq Monitor toggle ───────────────────────────────────────────
        tk.Frame(body, bg=CARD_BG, height=1, highlightbackground="#d4b483",
                 highlightthickness=1).pack(fill="x", pady=(18, 10))
        monitor_row = tk.Frame(body, bg=CARD_BG)
        monitor_row.pack(fill="x")
        tk.Checkbutton(
            monitor_row,
            text="Show Groq Monitor panel in JSON Tool",
            variable=self._monitor_var,
            bg=CARD_BG, fg=TEXT_COLOR,
            activebackground=CARD_BG,
            font=FONT_BODY,
            cursor="hand2",
        ).pack(side="left")
        tk.Label(
            body,
            text="Hides the Groq request/response monitor column.\nTakes effect after closing and reopening the Application.",
            font=("Segoe UI", 8), bg=CARD_BG, fg="#a08060",
            justify="left",
        ).pack(anchor="w", pady=(3, 0))

    # ── Confluence card — commented out; uncomment to re-enable ──────────
    # def _add_conf_fields(self, card):
    #     body = tk.Frame(card, bg=CARD_BG, padx=15, pady=15)
    #     body.pack(fill="both", expand=True)
    #
    #     instr_f = tk.Frame(body, bg="#fff9e6",
    #                        highlightthickness=1, highlightbackground="#ffe58f")
    #     instr_f.pack(fill="x", pady=(0, 15))
    #
    #     tk.Button(instr_f, text="🔗 Create Scoped Token Here", fg=LINK_COLOR,
    #               font=FONT_BOLD, bg="#fff9e6", relief="flat",
    #               command=lambda: self._copy_link(
    #                   "https://id.atlassian.com/manage-profile/security/api-tokens")
    #               ).pack(anchor="w", padx=5)
    #
    #     guide_text = (
    #         "1. Label: Groq-Reader-Only\n"
    #         "2. Scopes (Confluence section):\n"
    #         "   • read:page:confluence\n"
    #         "   • read:space-details:confluence\n"
    #         "   • read:content-details:confluence\n"
    #         "3. Leave 'Write/Delete' UNCHECKED."
    #     )
    #     tk.Label(instr_f, text=guide_text, font=FONT_SMALL, bg="#fff9e6",
    #              justify="left", fg="#444").pack(anchor="w", padx=10, pady=5)
    #
    #     tk.Label(body, text="Email Address", font=FONT_BOLD, bg=CARD_BG).pack(anchor="w")
    #     tk.Entry(body, textvariable=self._conf_user_var,
    #              bg=THEME_INPUT, width=35).pack(fill="x", pady=(5, 10))
    #
    #     tk.Label(body, text="API Token", font=FONT_BOLD, bg=CARD_BG).pack(anchor="w")
    #     tok_f = tk.Frame(body, bg=CARD_BG)
    #     tok_f.pack(fill="x", pady=(5, 10))
    #     self._token_entry = tk.Entry(tok_f, textvariable=self._conf_token_var,
    #                                  show="*", bg=THEME_INPUT, width=30)
    #     self._token_entry.pack(side="left", fill="x", expand=True)
    #     tk.Button(tok_f, text="👁", bg=CARD_BG,
    #               command=self._toggle_token).pack(side="right")
    #
    #     tk.Label(body, text="Base URL", font=FONT_BOLD, bg=CARD_BG).pack(anchor="w")
    #     tk.Entry(body, textvariable=self._conf_url_var,
    #              bg=THEME_INPUT, width=35).pack(fill="x", pady=(5, 0))

    def _add_txn_fields(self, card):
        body = tk.Frame(card, bg=CARD_BG, padx=15, pady=15)
        body.pack(fill="both", expand=True)

        rows = [
            ("Beyonic ID",  "BeyonicTxnId"),
            ("Network ID",  "NetworkTxnId"),
            ("Airtel ID",   "AirtelTxnId"),
            ("Bank Ref",    "BankTxnId"),
            ("Flexipay",    "FlexipayTxnId"),
        ]
        for lbl, key in rows:
            tk.Label(body, text=lbl, font=FONT_BOLD, bg=CARD_BG).pack(anchor="w", pady=(5, 0))
            tk.Entry(body, textvariable=self._txn_vars[key],
                     bg=THEME_INPUT, width=35).pack(fill="x", pady=(2, 5))

    def _toggle_api(self):
        self._key_vis = not self._key_vis
        self._api_entry.config(show="" if self._key_vis else "*")

    # Confluence token toggle — commented out; uncomment to re-enable
    # def _toggle_token(self):
    #     self._tok_vis = not self._tok_vis
    #     self._token_entry.config(show="" if self._tok_vis else "*")

    def _save_all(self):
        self._cfg.update({
            "api_key":            self._api_key_var.get().strip(),
            "groq_model":         self._model_var.get(),
            "show_groq_monitor":  "1" if self._monitor_var.get() else "0",

            # Confluence fields — commented out; uncomment to re-enable
            # "conf_username":  self._conf_user_var.get().strip(),
            # "conf_api_token": self._conf_token_var.get().strip(),
            # "conf_base_url":  self._conf_url_var.get().strip(),
        })
        for k, v in self._txn_vars.items():
            self._cfg[k] = v.get().strip()
        try:
            save_settings(self._cfg)
            messagebox.showinfo("Success", "Settings saved. App is now in Read-Only mode.")
        except Exception as e:
            messagebox.showerror("Error", str(e))