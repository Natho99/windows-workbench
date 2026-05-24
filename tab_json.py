# tab_json.py
"""
JSON Generator panel — 3- or 4-section proportional layout (monitor optional).

Payment Form renders fields in 3 columns and gets ~60 % of the total width
when the Groq Monitor is hidden (default) and ~52 % when it is visible.

Privacy — mask-last-3 + lookup table
──────────────────────────────────────
Before sending to Groq, _build_privacy_table() finds every sensitive digit
sequence (8+ digits, solid or space-separated, optionally letter-prefixed),
masks its last 3 digit characters with ***, and records:

    masked_value  →  original_value

in a lookup table stored in _PRIVACY_DB.

What Groq sees for:
  "29/04/2026 USSD transfer JOHN BOSCO ORYEM 1,521,250  S45377947 NUMBER USED: 256774054723"
  →
  "29/04/2026 USSD transfer JOHN BOSCO ORYEM 1,521,250  S45377*** NUMBER USED: 256774054***"

Groq classifies from prefix + context:
  256774054***  → 256-prefix phone  → billRefNumber / mobile
  S45377***     → S-prefix bank ID  → transactionId

After response, _restore_dict() swaps masked forms back to originals.
Restore is star-count-agnostic: Groq returning "25677745**" (2 stars) or
"25677745***" (3 stars) both restore correctly via digit-prefix matching.
Then _normalise_restored_phones() applies per-field prefix rules to handle
any format the user may have entered (0-prefix, spaced, bare local, etc).

Amount cross-validation
────────────────────────
After Groq returns an amount, _validate_amount() re-parses the original raw
text (before masking) to extract the amount independently and compares.
If Groq's value deviates by more than 50 % from what the raw text says,
the raw-text value wins. This catches hallucinations like "500000" when the
source says "50,000".

Phone normalisation (post-restore)
────────────────────────────────────
  "0798766780"       → 256 prefix fields: "256798766780"
  "079 876 6780"     → 256 prefix fields: "256798766780"  (spaces stripped)
  "079-876-6780"     → 256 prefix fields: "256798766780"  (hyphens stripped)
  "798 766 780"      → 256 prefix fields: "256798766780"
  "+256 798 766 780" → 256 prefix fields: "256798766780"
  "0798766780"       → +256 prefix fields: "+256798766780"

Groq Monitor
────────────
The monitor column is shown or hidden based on the "show_groq_monitor"
setting (set in Settings ⚙). When hidden, section fractions are
redistributed evenly across the remaining three columns.
"""
import json
import re
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from config import (
    THEME_BG, THEME_ACCENT, THEME_INPUT, THEME_BORDER,
    TEXT_COLOR, TEXT_MUTED,
    FONT_BODY, FONT_BOLD, FONT_TITLE, FONT_SMALL,
    JSON_TYPE_OPTIONS, DROPDOWN_PLACEHOLDER,
)
from json_data      import get_json_fields, get_json_hints, build_json_payload
from groq_parser    import (
    groq_extract, _build_prompt,
    _normalise_256, _normalise_plus256, _extract_ug_phone_local,
)
from settings_store import load_settings

# ── Palette ───────────────────────────────────────────────────────────────────
FORM_BG      = THEME_BG
FORM_HDR_BG  = "#c9a66b"
FORM_HDR_FG  = "#3a2f24"

REF_BG       = "#fdf3d8"
REF_HDR_BG   = THEME_ACCENT
REF_HDR_FG   = TEXT_COLOR
REF_BORDER   = "#d4b483"

JSON_BG      = "#eaf4f4"
JSON_HDR_BG  = "#3d7a7a"
JSON_HDR_FG  = "#ffffff"
JSON_BORDER  = "#3d7a7a"
JSON_TEXT_BG = "#f4fafa"
JSON_TEXT_FG = "#1a3a3a"
JSON_BTN_BG  = "#3d7a7a"
JSON_BTN_HOV = "#2a5858"

# ── Savannah Brown Monitor Theme ──────────────────────────────────────────────
MON_BG       = "#f5edd6"
MON_HDR_BG   = "#c8a96e"
MON_HDR_FG   = "#3a2a10"
MON_TEXT_FG  = "#5a3e1b"
MON_TEXT_BG  = "#fdf6e3"
MON_BORDER   = "#b8935a"
MON_BTN_BG   = "#c8a96e"
MON_BTN_HOV  = "#a8844e"
MON_ERR_FG   = "#b33a1a"
MON_REQ_FG   = "#4a6fa5"
MON_RES_FG   = "#3a6b3a"
MON_LABEL_FG = "#7a4a10"
MON_MUTED_FG = "#a08060"
RULE_COLOR   = "#d4b896"
RULE_W       = 2

# ── Section fractions ─────────────────────────────────────────────────────────
_FRACS_4 = [0.46, 0.18, 0.18, 0.18]
_FRACS_3 = [0.52, 0.24, 0.24]

# ── Form layout ───────────────────────────────────────────────────────────────
FORM_COLS    = 3
ENTRY_WIDTH  = 16

_PLACEHOLDER     = "Click  ⚙ Generate  on the payment form to see output."
_REF_PLACEHOLDER = "Paste your source payment text here for reference…"
_MON_PLACEHOLDER = "Groq request/response details will appear here after Autofill…"

_AIRTEL_DATE_FIELDS = (
    "creationDate",
    "agentAssignmentDateTime",
    "paymentTransactionDateTime",
)

_MIN_SENSITIVE_DIGITS = 8

# ── Amount field names per payment type ──────────────────────────────────────
_AMOUNT_FIELDS: dict[str, str] = {
    "Beyonic":  "Amount",
    "Airtel":   "paymentAmount",
    "Bank":     "amount",
    "Flexipay": "amount",
}

# ── Phone field classifications per payment type ──────────────────────────────
_PHONE_FIELD_FORMAT: dict[str, dict[str, str]] = {
    "Beyonic":  {"PhoneNumber": "plus256"},
    "Airtel":   {"customerReferenceNumber": "256", "senderPhoneNumber": "256"},
    "Bank":     {"billRefNumber": "256", "mobile": "256"},
    "Flexipay": {"billRefNumber": "256", "mobile": "256"},
}


# ═══════════════════════════════════════════════════════════════════════════════
# IN-MEMORY PRIVACY DB
# ═══════════════════════════════════════════════════════════════════════════════
_PRIVACY_DB: dict = {"lookup": {}, "raw_text": ""}


# ═══════════════════════════════════════════════════════════════════════════════
# PRIVACY — BUILD MASKED TEXT + LOOKUP TABLE
# ═══════════════════════════════════════════════════════════════════════════════

def _build_privacy_table(text: str) -> tuple[str, dict]:
    """
    Scan *text* for sensitive digit sequences (8+ total digits) and:
      1. Replace the last 3 digit characters of each with ***
      2. Record  masked_value → original_value  in a lookup table

    Handled patterns
    ────────────────
    Pass 1 — letter-prefixed codes:  S45377947 → S45377***
    Pass 2 — digit spans:  solid or single-space-separated, optional leading +
      "0751 046 941"  → 10 digits total → "0751 046 ***"
      "256774054723"  → 12 digits solid → "256774054***"
      "29/04/2026"    → NOT masked (slashes break span into short chunks)
      "1,521,250"     → NOT masked (commas break span into short chunks)
    """
    n       = len(text)
    visited = [False] * n
    spans   = []

    # Pass 1: letter-prefixed codes
    for m in re.finditer(
        rf'(?<![A-Za-z\d])[A-Za-z]{{1,3}}(\d{{{_MIN_SENSITIVE_DIGITS},}})(?!\d)',
        text
    ):
        spans.append((m.start(), m.end()))
        for k in range(m.start(), m.end()):
            visited[k] = True

    # Pass 2: digit spans (solid or single-space-separated, optional +)
    i = 0
    while i < n:
        if text[i] == '+' and i + 1 < n and text[i + 1].isdigit() and not visited[i]:
            span_start, j = i, i + 1
        elif text[i].isdigit() and not visited[i]:
            span_start = j = i
        else:
            i += 1
            continue

        while j < n:
            if text[j].isdigit():
                j += 1
            elif text[j] == ' ' and j + 1 < n and text[j + 1].isdigit():
                j += 1   # single space inside span (e.g. "0751 046 941")
            else:
                break    # comma, slash, hyphen, letter → end span

        digit_count = sum(
            1 for k in range(span_start, j)
            if text[k].isdigit() and not visited[k]
        )
        if digit_count >= _MIN_SENSITIVE_DIGITS:
            spans.append((span_start, j))
        i = j if j > i else i + 1

    spans.sort(key=lambda x: x[0])
    deduped, last_end = [], -1
    for s, e in spans:
        if s >= last_end:
            deduped.append((s, e))
            last_end = e

    lookup_table = {}
    assignments  = []

    for s, e in deduped:
        original = text[s:e]
        digit_positions = [k for k in range(s, e) if text[k].isdigit()]
        if len(digit_positions) < _MIN_SENSITIVE_DIGITS:
            continue
        mask_set = set(digit_positions[-3:])
        masked = ''.join('*' if k in mask_set else text[k] for k in range(s, e))
        lookup_table[masked] = original
        assignments.append((s, e, masked))

    result = list(text)
    for s, e, masked in reversed(assignments):
        result[s:e] = list(masked)

    return ''.join(result), lookup_table


# ═══════════════════════════════════════════════════════════════════════════════
# PRIVACY — RESTORE FROM LOOKUP TABLE
# ═══════════════════════════════════════════════════════════════════════════════

def _split_trailing_stars(s: str) -> tuple[str, int]:
    """
    Strip non-digit/non-* chars, then split off trailing stars.
    Returns (digit_prefix, star_count).

    Examples:
      "40676469***"  → ("40676469", 3)
      "406764692**"  → ("406764692", 2)
      "+256777524***" → ("256777524", 3)   ← + is stripped
      "256777524300" → ("256777524300", 0)
    """
    core = re.sub(r'[^\d*]', '', s)
    stars = len(core) - len(core.rstrip('*'))
    return core.rstrip('*'), stars


def _restore_from_table(value: str, lookup_table: dict) -> str:
    """
    Swap a masked value returned by Groq back to its original.

    Strategies (in order):
    1. Exact key match:    "40676469***"   → "40676469223"
    2. Contains match:     "+256774054***" → "+256774054723" (Groq added prefix)
    3. Star-count-agnostic prefix match:
          "406764692**" (2 stars) matches lookup key "40676469***" (3 stars)
          because digit prefixes overlap: "406764692" starts with "40676469"
    4. Core digit match (original fallback).
    """
    if not lookup_table or not value:
        return value

    # 1. Exact match
    if value in lookup_table:
        return lookup_table[value]

    # 2. Contains match (e.g. Groq prepends "+256" to a masked phone)
    for masked, original in lookup_table.items():
        if masked in value:
            return value.replace(masked, original)

    # 3. Star-count-agnostic prefix match
    val_prefix, val_stars = _split_trailing_stars(value)
    if val_stars > 0:
        best_match = None
        best_overlap = 0
        for masked, original in lookup_table.items():
            mk_prefix, mk_stars = _split_trailing_stars(masked)
            if not mk_prefix or not val_prefix:
                continue
            # Accept if one prefix is a prefix of the other
            # (Groq may include one extra or one fewer digit before ***)
            if val_prefix.startswith(mk_prefix) or mk_prefix.startswith(val_prefix):
                overlap = min(len(val_prefix), len(mk_prefix))
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_match = original
        if best_match is not None:
            return best_match

    # 4. Core digit match (last resort — no stars in value)
    def _core(s: str) -> str:
        return re.sub(r'[^\d*]', '', s)

    val_core = _core(value)
    for masked, original in lookup_table.items():
        masked_core = _core(masked)
        if masked_core and (
            val_core.endswith(masked_core) or masked_core in val_core
        ):
            return original

    return value


def _restore_dict(values: dict, lookup_table: dict) -> dict:
    """Apply _restore_from_table to every string value in *values*."""
    if not lookup_table:
        return values
    return {k: _restore_from_table(str(v), lookup_table) for k, v in values.items()}


# ═══════════════════════════════════════════════════════════════════════════════
# AMOUNT CROSS-VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_raw_amount(text: str) -> str:
    """
    Parse *text* for an amount figure, stripping commas/spaces.
    Looks for keywords like AMOUNT, TOTAL, PAID, UGX, SHS, etc.
    Returns a plain integer/decimal string, or "" if not found.
    """
    patterns = [
        # Keyword followed by optional colon/equals then number
        r'(?:amount|total paid|total|paid|payment|ugx|ush|shs?)'
        r'[:\s=]*([0-9][0-9,\s]*(?:\.\d+)?)',
        # Standalone large number (≥3 digits, with comma separators)
        r'(?<!\d)([1-9]\d{0,2}(?:,\d{3})+(?:\.\d+)?)(?!\d)',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            raw = re.sub(r'[,\s]', '', m.group(1)).strip()
            if raw and re.fullmatch(r'\d+(?:\.\d+)?', raw):
                return raw
    return ""


def _validate_amount(groq_amount: str, raw_text: str, decimal_places: int = 0) -> str:
    """
    Cross-validate *groq_amount* (string from Groq, commas already stripped)
    against the amount found in *raw_text*.

    If Groq's value deviates by more than 50% from the raw-text amount, the
    raw-text value wins.  Applies *decimal_places* formatting to the winner
    (0 = whole number for Flexipay/Airtel, 2 = Bank).

    Also strips any residual commas/spaces that Groq may have left in.
    """
    # Always strip commas/spaces from whatever Groq gave us first
    cleaned = re.sub(r'[,\s]', '', groq_amount).strip()
    if not cleaned:
        return groq_amount

    raw_amt_str = _extract_raw_amount(raw_text)

    if raw_amt_str:
        try:
            groq_val = float(cleaned)
            raw_val  = float(raw_amt_str)
            if raw_val > 0:
                ratio = groq_val / raw_val
                # If Groq is off by more than 50% in either direction → use raw text value
                if ratio > 1.5 or ratio < 0.5:
                    cleaned = raw_amt_str
        except (ValueError, ZeroDivisionError):
            pass

    # Apply decimal formatting
    if decimal_places > 0:
        try:
            cleaned = f"{float(cleaned):.{decimal_places}f}"
        except ValueError:
            pass
    else:
        # Strip any decimals for whole-number fields
        try:
            cleaned = str(int(float(cleaned)))
        except ValueError:
            pass

    return cleaned


# ═══════════════════════════════════════════════════════════════════════════════
# POST-RESTORE PHONE NORMALISATION
# ═══════════════════════════════════════════════════════════════════════════════

def _normalise_restored_phones(json_type: str, values: dict) -> dict:
    """
    After lookup-table restoration, phone field values may still be in whatever
    format the user originally typed (e.g. "0798766780", "079 876 6780",
    "798766780", "+256798766780").

    This function converts every phone field to the correct prefix format
    required by the payment type:
      +256XXXXXXXXX  for Beyonic PhoneNumber
      256XXXXXXXXX   for Airtel / Bank / Flexipay phone fields
    """
    phone_fields = _PHONE_FIELD_FORMAT.get(json_type, {})
    result = dict(values)

    for field, fmt in phone_fields.items():
        raw = result.get(field, "")
        if not raw:
            continue
        if '***' in raw:
            continue   # still masked — leave for manual correction
        local = _extract_ug_phone_local(raw)
        if not local:
            continue
        if fmt == "plus256":
            result[field] = "+256" + local
        else:
            result[field] = "256" + local

    # Cross-fill for types that share the same phone in multiple fields
    if json_type == "Airtel":
        crn = result.get("customerReferenceNumber", "")
        spn = result.get("senderPhoneNumber", "")
        master = crn or spn
        if master:
            result["customerReferenceNumber"] = master
            result["senderPhoneNumber"]        = master

    elif json_type in ("Bank", "Flexipay"):
        brn    = result.get("billRefNumber", "")
        mobile = result.get("mobile", "")
        master = brn or mobile
        if master:
            result["billRefNumber"] = master
            result["mobile"]        = master

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# POST-RESTORE AMOUNT NORMALISATION
# ═══════════════════════════════════════════════════════════════════════════════

def _normalise_restored_amounts(json_type: str, values: dict, raw_text: str) -> dict:
    """
    After lookup-table restoration, validate and reformat amount fields.

    Flexipay / Airtel : whole number, no decimals
    Bank              : 2 decimal places
    Beyonic           : whole number, no decimals

    Cross-validates against *raw_text* to catch Groq hallucinations
    (e.g. "500000" when the source clearly says "50,000").
    """
    amount_field = _AMOUNT_FIELDS.get(json_type, "")
    if not amount_field:
        return values

    result = dict(values)
    raw_val = result.get(amount_field, "")
    if not raw_val:
        return result

    if json_type == "Bank":
        corrected = _validate_amount(raw_val, raw_text, decimal_places=2)
    else:
        corrected = _validate_amount(raw_val, raw_text, decimal_places=0)

    if corrected:
        result[amount_field] = corrected

    return result


# ── Button helper ─────────────────────────────────────────────────────────────
def _btn(parent, text, cmd, bg, fg="#3a2f24", hover_bg=None,
         font=FONT_SMALL, padx=8, pady=3):
    return tk.Button(
        parent, text=text, command=cmd,
        font=font, bg=bg, fg=fg,
        relief="flat", bd=0, cursor="hand2",
        padx=padx, pady=pady,
        activebackground=hover_bg or bg,
        activeforeground=fg,
    )


class JsonGeneratorPanel(tk.Frame):
    """
    3- or 4-section JSON Generator.

    When show_groq_monitor=1 (Settings): Payment Form | Reference | JSON | Monitor
    When show_groq_monitor=0 (Settings): Payment Form | Reference | JSON

    Privacy flow per autofill:
      1. _build_privacy_table(raw_text)
             → masked_text   (last 3 digits of 8+-digit numbers replaced with ***)
             → lookup_table  (masked → original, stored in _PRIVACY_DB)
      2. Send masked_text to Groq
      3. Groq classifies numbers from prefix/context; returns masked values
      4. _restore_dict(values, lookup_table)
             → real values restored (star-count-agnostic prefix matching)
      5. _normalise_restored_amounts(json_type, values, raw_text)
             → cross-validates amounts against raw text; fixes hallucinations
      6. _normalise_restored_phones(json_type, values)
             → converts any phone format to correct prefix for each field
      7. Form filled with normalised real values
    """

    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=FORM_BG, **kwargs)
        self._json_type_var = tk.StringVar(value=DROPDOWN_PLACEHOLDER)
        self._entry_vars: dict[str, tk.StringVar] = {}
        self._monitor_visible = load_settings().get("show_groq_monitor", "1") == "1"
        self._build()
        self._on_type_change()
        self._clear_preview()

    # ══════════════════════════════════════════════════════════════════════════
    # TOP-LEVEL BUILD
    # ══════════════════════════════════════════════════════════════════════════
    def _build(self):
        self._container = tk.Frame(self, bg=RULE_COLOR)
        self._container.place(relx=0, rely=0, relwidth=1, relheight=1)

        self._sec_form = tk.Frame(self._container, bg=FORM_BG)
        self._sec_ref  = tk.Frame(self._container, bg=REF_BG)
        self._sec_json = tk.Frame(self._container, bg=JSON_BG)
        self._sec_mon  = tk.Frame(self._container, bg=MON_BG)

        if self._monitor_visible:
            self._sections = [
                self._sec_form,
                self._sec_ref,
                self._sec_json,
                self._sec_mon,
            ]
            self._fracs = _FRACS_4
        else:
            self._sections = [
                self._sec_form,
                self._sec_ref,
                self._sec_json,
            ]
            self._fracs = _FRACS_3

        self._rules = [
            tk.Frame(self._container, bg=RULE_COLOR, width=RULE_W)
            for _ in range(len(self._sections) - 1)
        ]

        self._build_form_column(self._sec_form)
        self._build_reference_column(self._sec_ref)
        self._build_json_column(self._sec_json)
        self._build_monitor_column(self._sec_mon)

        self._container.bind("<Configure>", self._relayout)

    def _relayout(self, event=None):
        W = self._container.winfo_width()
        H = self._container.winfo_height()
        if W <= 1:
            return
        rules_px = RULE_W * len(self._rules)
        avail    = W - rules_px
        widths   = [max(1, int(avail * f)) for f in self._fracs]
        widths[-1] = max(1, avail - sum(widths[:-1]))
        x = 0
        for i, sec in enumerate(self._sections):
            sec.place(x=x, y=0, width=widths[i], height=H)
            x += widths[i]
            if i < len(self._rules):
                self._rules[i].place(x=x, y=0, width=RULE_W, height=H)
                x += RULE_W
        if not self._monitor_visible:
            self._sec_mon.place_forget()

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 0 — PAYMENT FORM
    # ══════════════════════════════════════════════════════════════════════════
    def _build_form_column(self, parent: tk.Frame):
        hdr = tk.Frame(parent, bg=FORM_HDR_BG)
        hdr.pack(fill="x")
        tk.Label(hdr, text="📝  Payment Form",
                 font=FONT_BOLD, bg=FORM_HDR_BG, fg=FORM_HDR_FG,
                 padx=10, pady=6).pack(side="left")

        sel = tk.Frame(parent, bg=FORM_BG)
        sel.pack(fill="x", padx=8, pady=(6, 3))
        tk.Label(sel, text="Payment Type:", font=FONT_BOLD,
                 bg=FORM_BG, fg=TEXT_COLOR).pack(side="left", padx=(0, 6))
        self._type_box = ttk.Combobox(
            sel, textvariable=self._json_type_var,
            values=JSON_TYPE_OPTIONS, state="readonly",
            width=14, font=FONT_BODY,
        )
        self._type_box.pack(side="left")
        self._type_box.bind("<<ComboboxSelected>>", self._on_type_change)

        tk.Frame(parent, bg=RULE_COLOR, height=1).pack(fill="x", padx=4)

        clear_bar = tk.Frame(parent, bg=FORM_BG)
        clear_bar.pack(fill="x", pady=(5, 0))
        tk.Button(
            clear_bar, text="🗑  Clear All Panels",
            command=self._clear_all_panels,
            font=FONT_SMALL, bg="#e8d5a3",
            fg="#cc0000", activeforeground="#990000",
            relief="flat", bd=0, cursor="hand2",
            padx=12, pady=4, activebackground="#d4b483",
        ).pack(anchor="center")

        tk.Frame(parent, bg=RULE_COLOR, height=1).pack(fill="x", padx=4, pady=(5, 0))

        act = tk.Frame(parent, bg=FORM_BG)
        act.pack(side="bottom", fill="x", padx=8, pady=4)
        tk.Frame(parent, bg=RULE_COLOR, height=1).pack(side="bottom", fill="x", padx=4)
        _btn(act, "⚙️  Generate JSON", self._generate,
             bg=THEME_ACCENT, hover_bg="#b58955",
             font=FONT_BOLD, padx=14, pady=5).pack(side="left", padx=(0, 6))
        _btn(act, "🗑️  Clear Fields", self._clear_fields,
             bg="#e8d5a3", hover_bg="#d4b483",
             font=FONT_BOLD, padx=10, pady=5).pack(side="left")

        grid_wrap = tk.Frame(parent, bg=FORM_BG)
        grid_wrap.pack(fill="both", expand=True, padx=4, pady=2)
        grid_wrap.rowconfigure(0, weight=1)
        grid_wrap.columnconfigure(0, weight=1)

        self._canvas = tk.Canvas(grid_wrap, bg=FORM_BG, highlightthickness=0)
        vsb = ttk.Scrollbar(grid_wrap, orient="vertical",   command=self._canvas.yview)
        hsb = ttk.Scrollbar(grid_wrap, orient="horizontal", command=self._canvas.xview)
        self._canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self._canvas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        self._grid_frame = tk.Frame(self._canvas, bg=FORM_BG)
        self._canvas_win = self._canvas.create_window(
            (0, 0), window=self._grid_frame, anchor="nw"
        )
        self._grid_frame.bind(
            "<Configure>",
            lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")),
        )
        self._canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 1 — REFERENCE HOLDER
    # ══════════════════════════════════════════════════════════════════════════
    def _build_reference_column(self, parent: tk.Frame):
        hdr = tk.Frame(parent, bg=REF_HDR_BG)
        hdr.pack(fill="x")
        tk.Label(hdr, text="📋  Reference Holder",
                 font=FONT_BOLD, bg=REF_HDR_BG, fg=REF_HDR_FG,
                 padx=10, pady=6).pack(side="left")

        tk.Label(
            parent,
            text="💡 Provide clear and relevant details to help the AI generate accurate results.",
            font=("Segoe UI", 9, "italic"), fg="#6b7280",
            bg=parent.cget("bg"), wraplength=200, justify="left", padx=10, pady=4,
        ).pack(fill="x")

        act = tk.Frame(parent, bg=REF_BG)
        act.pack(side="bottom", fill="x", padx=6, pady=4)
        tk.Frame(parent, bg=REF_BORDER, height=1).pack(side="bottom", fill="x", padx=4)
        self._autofill_btn = _btn(
            act, "🤖  Autofill with AI", self._run_ai_autofill,
            bg=THEME_ACCENT, hover_bg="#b58955", font=FONT_BOLD, padx=10, pady=4,
        )
        self._autofill_btn.pack(side="left", padx=(0, 4))
        _btn(act, "🗑️  Clear", self._clear_reference,
             bg="#e8d5a3", hover_bg="#d4b483", font=FONT_BOLD, padx=8, pady=4).pack(side="left")

        txt_wrap = tk.Frame(parent, bg=REF_BG)
        txt_wrap.pack(fill="both", expand=True, padx=4, pady=(4, 0))
        sb_y = ttk.Scrollbar(txt_wrap, orient="vertical")
        self._ref_text = tk.Text(
            txt_wrap, font=("Consolas", 9),
            bg=THEME_INPUT, fg=TEXT_COLOR, relief="flat", wrap="word",
            highlightbackground=REF_BORDER, highlightthickness=1,
            insertbackground=TEXT_COLOR, yscrollcommand=sb_y.set, undo=True,
        )
        sb_y.config(command=self._ref_text.yview)
        sb_y.pack(side="right", fill="y")
        self._ref_text.pack(fill="both", expand=True)
        self._ref_text.insert("1.0", _REF_PLACEHOLDER)
        self._ref_text.config(fg="#b0997a")
        self._ref_text.bind("<FocusIn>",  self._ref_focus_in)
        self._ref_text.bind("<FocusOut>", self._ref_focus_out)

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 2 — GENERATED JSON
    # ══════════════════════════════════════════════════════════════════════════
    def _build_json_column(self, parent: tk.Frame):
        hdr = tk.Frame(parent, bg=JSON_HDR_BG)
        hdr.pack(fill="x")
        tk.Label(hdr, text="{ } JSON Generated",
                 font=FONT_BOLD, bg=JSON_HDR_BG, fg=JSON_HDR_FG,
                 padx=8, pady=6).pack(side="left")
        tk.Label(hdr, text="editable", font=FONT_SMALL,
                 bg=JSON_HDR_BG, fg="#a8d8d8", padx=4).pack(side="right")

        act = tk.Frame(parent, bg=JSON_BG)
        act.pack(side="bottom", fill="x", padx=4, pady=4)
        tk.Frame(parent, bg=JSON_BORDER, height=1).pack(side="bottom", fill="x", padx=4)
        _btn(act, "📋 Copy", self._copy_json,
             bg=JSON_BTN_BG, fg="#ffffff", hover_bg=JSON_BTN_HOV,
             font=FONT_SMALL, padx=7, pady=3).pack(side="left", padx=(0, 3))
        _btn(act, "🗑 Clear", self._clear_preview,
             bg="#d0eaea", fg="#1a3a3a", hover_bg="#b8d8d8",
             font=FONT_SMALL, padx=7, pady=3).pack(side="left")

        txt_wrap = tk.Frame(parent, bg=JSON_BG)
        txt_wrap.pack(fill="both", expand=True, padx=4, pady=(4, 0))
        sb_y = ttk.Scrollbar(txt_wrap, orient="vertical")
        self._preview_text = tk.Text(
            txt_wrap, font=("Consolas", 8),
            bg=JSON_TEXT_BG, fg=JSON_TEXT_FG, relief="flat", wrap="word",
            highlightbackground=JSON_BORDER, highlightthickness=1,
            insertbackground=JSON_HDR_BG,
            selectbackground=JSON_HDR_BG, selectforeground="#ffffff",
            yscrollcommand=sb_y.set,
        )
        sb_y.config(command=self._preview_text.yview)
        sb_y.pack(side="right", fill="y")
        self._preview_text.pack(fill="both", expand=True)

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 3 — GROQ MONITOR
    # ══════════════════════════════════════════════════════════════════════════
    def _build_monitor_column(self, parent: tk.Frame):
        hdr = tk.Frame(parent, bg=MON_HDR_BG)
        hdr.pack(fill="x")
        tk.Label(hdr, text="🔬  Groq Monitor",
                 font=FONT_BOLD, bg=MON_HDR_BG, fg=MON_HDR_FG,
                 padx=8, pady=6).pack(side="left")
        self._mon_status_var = tk.StringVar(value="idle")
        self._mon_status_lbl = tk.Label(
            hdr, textvariable=self._mon_status_var,
            font=FONT_SMALL, bg=MON_HDR_BG, fg="#3a6b3a", padx=6,
        )
        self._mon_status_lbl.pack(side="right")

        act = tk.Frame(parent, bg=MON_BG)
        act.pack(side="bottom", fill="x", padx=4, pady=4)
        tk.Frame(parent, bg=MON_BORDER, height=1).pack(side="bottom", fill="x", padx=4)
        _btn(act, "📋 Copy", self._copy_monitor,
             bg=MON_BTN_BG, fg=MON_HDR_FG, hover_bg=MON_BTN_HOV,
             font=FONT_SMALL, padx=7, pady=3).pack(side="left", padx=(0, 3))
        _btn(act, "🗑 Clear", self._clear_monitor,
             bg="#e8d5a3", fg="#3a2a10", hover_bg="#d4b483",
             font=FONT_SMALL, padx=7, pady=3).pack(side="left")

        txt_wrap = tk.Frame(parent, bg=MON_BG)
        txt_wrap.pack(fill="both", expand=True, padx=4, pady=(4, 0))
        sb_y = ttk.Scrollbar(txt_wrap, orient="vertical")
        self._monitor_text = tk.Text(
            txt_wrap, font=("Consolas", 8),
            bg=MON_TEXT_BG, fg=MON_TEXT_FG, relief="flat", wrap="word",
            highlightbackground=MON_BORDER, highlightthickness=1,
            insertbackground=MON_HDR_FG,
            selectbackground=MON_BTN_BG, selectforeground=MON_HDR_FG,
            yscrollcommand=sb_y.set, state="disabled",
        )
        sb_y.config(command=self._monitor_text.yview)
        sb_y.pack(side="right", fill="y")
        self._monitor_text.pack(fill="both", expand=True)

        self._monitor_text.tag_configure("label",    foreground=MON_LABEL_FG,
                                         font=("Consolas", 8, "bold"))
        self._monitor_text.tag_configure("request",  foreground=MON_REQ_FG)
        self._monitor_text.tag_configure("response", foreground=MON_RES_FG)
        self._monitor_text.tag_configure("error",    foreground=MON_ERR_FG)
        self._monitor_text.tag_configure("muted",    foreground=MON_MUTED_FG)
        self._monitor_text.tag_configure("divider",  foreground=MON_BORDER)
        self._monitor_text.tag_configure("privacy",  foreground="#b06000",
                                         font=("Consolas", 8, "italic"))
        self._monitor_write(_MON_PLACEHOLDER, "muted")

    # ── Monitor helpers ────────────────────────────────────────────────────
    def _monitor_write(self, text: str, tag: str = "response"):
        if not self._monitor_visible:
            return
        self._monitor_text.config(state="normal")
        self._monitor_text.insert("end", text, tag)
        self._monitor_text.see("end")
        self._monitor_text.config(state="disabled")

    def _monitor_clear_internal(self):
        if not self._monitor_visible:
            return
        self._monitor_text.config(state="normal")
        self._monitor_text.delete("1.0", "end")
        self._monitor_text.config(state="disabled")

    def _clear_monitor(self):
        self._monitor_clear_internal()
        self._monitor_write(_MON_PLACEHOLDER, "muted")
        self._mon_status_var.set("idle")
        self._mon_status_lbl.config(fg="#3a6b3a")

    def _copy_monitor(self):
        if not self._monitor_visible:
            return
        content = self._monitor_text.get("1.0", "end-1c").strip()
        if not content or content == _MON_PLACEHOLDER:
            messagebox.showinfo("Notice", "Nothing to copy.", parent=self)
            return
        self.clipboard_clear()
        self.clipboard_append(content)
        self.update()
        messagebox.showinfo("Copied!", "Monitor content copied to clipboard.", parent=self)

    def _monitor_show_request(self, json_type: str, model: str,
                               masked_text: str, lookup_table: dict, prompt: str):
        if not self._monitor_visible:
            return
        self._monitor_clear_internal()
        self._monitor_write("━━━ REQUEST ━━━\n", "divider")
        self._monitor_write("Model : ", "label"); self._monitor_write(f"{model}\n", "request")
        self._monitor_write("Type  : ", "label"); self._monitor_write(f"{json_type}\n", "request")

        if lookup_table:
            self._monitor_write("\n── Privacy Lookup Table ──\n", "label")
            self._monitor_write(
                f"  {len(lookup_table)} number(s) masked — last 3 digits replaced with ***\n"
                "  Groq sees prefix+context to classify correctly.\n"
                "  Originals restored after response (star-count-agnostic matching),\n"
                "  then phone prefix and amount validated.\n",
                "privacy",
            )
            for masked, original in lookup_table.items():
                self._monitor_write(f"  sent : {masked}\n", "request")
                self._monitor_write(f"  real : {original}\n", "muted")
                self._monitor_write("  " + "─" * 28 + "\n", "muted")

        self._monitor_write("\n── System Prompt ──\n", "label")
        self._monitor_write(prompt + "\n", "muted")
        self._monitor_write("\n── User Message (masked) ──\n", "label")
        self._monitor_write(masked_text + "\n", "request")

    def _monitor_show_response(self, raw_ai: dict, restored: dict, final: dict):
        if not self._monitor_visible:
            return
        self._monitor_write("\n━━━ RESPONSE ━━━\n", "divider")
        self._monitor_write("── Raw AI Output ──\n", "label")
        self._monitor_write(json.dumps(raw_ai,    ensure_ascii=False, indent=2) + "\n", "response")
        self._monitor_write("\n── After Restore ──\n", "label")
        self._monitor_write(json.dumps(restored,  ensure_ascii=False, indent=2) + "\n", "response")
        self._monitor_write("\n── After Amount + Phone Normalise ──\n", "label")
        self._monitor_write(json.dumps(final,     ensure_ascii=False, indent=2) + "\n", "response")

    def _monitor_show_error(self, error_msg: str):
        if not self._monitor_visible:
            return
        self._monitor_write("\n━━━ ERROR ━━━\n", "divider")
        self._monitor_write(error_msg + "\n", "error")

    # ══════════════════════════════════════════════════════════════════════════
    # REFERENCE TEXT HELPERS
    # ══════════════════════════════════════════════════════════════════════════
    def _ref_focus_in(self, _=None):
        if self._ref_text.get("1.0", "end-1c") == _REF_PLACEHOLDER:
            self._ref_text.delete("1.0", "end")
            self._ref_text.config(fg=TEXT_COLOR)

    def _ref_focus_out(self, _=None):
        if not self._ref_text.get("1.0", "end-1c").strip():
            self._ref_text.insert("1.0", _REF_PLACEHOLDER)
            self._ref_text.config(fg="#b0997a")

    def _clear_reference(self):
        self._ref_text.delete("1.0", "end")
        self._ref_text.insert("1.0", _REF_PLACEHOLDER)
        self._ref_text.config(fg="#b0997a")

    # ══════════════════════════════════════════════════════════════════════════
    # FORM FIELD RENDERING
    # ══════════════════════════════════════════════════════════════════════════
    def _on_mousewheel(self, event):
        try:
            self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except Exception:
            pass

    def _on_type_change(self, event=None):
        json_type = self._json_type_var.get()
        for w in self._grid_frame.winfo_children():
            w.destroy()
        self._entry_vars.clear()
        self._clear_preview()

        JSON_FIELDS = get_json_fields()
        JSON_HINTS  = get_json_hints()

        if json_type not in JSON_FIELDS:
            tk.Label(
                self._grid_frame,
                text="Select a payment type above to load the form.",
                font=FONT_BODY, bg=FORM_BG, fg=TEXT_MUTED,
            ).grid(row=0, column=0, columnspan=10, pady=30, padx=10, sticky="w")
            return

        fields = JSON_FIELDS[json_type]
        hints  = JSON_HINTS.get(json_type, {})

        self._grid_frame.columnconfigure(0, weight=0, minsize=6)
        self._grid_frame.columnconfigure(1, weight=0)
        self._grid_frame.columnconfigure(2, weight=1)
        self._grid_frame.columnconfigure(3, weight=0, minsize=10)
        self._grid_frame.columnconfigure(4, weight=0)
        self._grid_frame.columnconfigure(5, weight=1)
        self._grid_frame.columnconfigure(6, weight=0, minsize=10)
        self._grid_frame.columnconfigure(7, weight=0)
        self._grid_frame.columnconfigure(8, weight=1)
        self._grid_frame.columnconfigure(9, weight=0, minsize=6)

        _COL_START = {0: 1, 1: 4, 2: 7}

        for idx, (key, label, default, is_numeric) in enumerate(fields):
            row_group = idx // FORM_COLS
            col_slot  = idx  % FORM_COLS
            lc        = _COL_START[col_slot]
            base_row  = row_group * 3

            tk.Label(
                self._grid_frame, text=label,
                font=FONT_BOLD, bg=FORM_BG, fg=TEXT_COLOR, anchor="w",
            ).grid(row=base_row, column=lc, columnspan=2,
                   sticky="w", padx=(0, 4), pady=(8, 0))

            var = tk.StringVar(value=default)
            tk.Entry(
                self._grid_frame, textvariable=var,
                font=FONT_BODY, width=ENTRY_WIDTH,
                bg=THEME_INPUT, fg=TEXT_COLOR, relief="flat",
                highlightbackground=THEME_BORDER, highlightcolor=THEME_ACCENT,
                highlightthickness=1, bd=0, insertbackground=TEXT_COLOR,
            ).grid(row=base_row + 1, column=lc, columnspan=2,
                   sticky="ew", padx=(0, 4), pady=(2, 0))

            self._entry_vars[key] = var

            hint = hints.get(key, "")
            if hint:
                tk.Label(
                    self._grid_frame, text=hint,
                    font=("Poppins", 8), bg=FORM_BG,
                    fg="#a08060", anchor="w", wraplength=160,
                ).grid(row=base_row + 2, column=lc, columnspan=2,
                       sticky="w", padx=(0, 4), pady=(0, 1))

        last_row = (len(fields) // FORM_COLS + 1) * 3
        tk.Frame(self._grid_frame, bg=FORM_BG, height=10).grid(
            row=last_row, column=0, columnspan=10
        )
        self._grid_frame.update_idletasks()
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    # ══════════════════════════════════════════════════════════════════════════
    # CLEAR ALL PANELS
    # ══════════════════════════════════════════════════════════════════════════
    def _clear_all_panels(self):
        self._clear_fields()
        self._clear_reference()
        self._clear_preview()
        self._clear_monitor()
        _PRIVACY_DB["lookup"]   = {}
        _PRIVACY_DB["raw_text"] = ""

    # ══════════════════════════════════════════════════════════════════════════
    # AI AUTOFILL
    # ══════════════════════════════════════════════════════════════════════════
    def _run_ai_autofill(self):
        json_type = self._json_type_var.get()
        JSON_FIELDS = get_json_fields()
        if json_type not in JSON_FIELDS:
            messagebox.showwarning("Select Type", "Select a Payment Type first.", parent=self)
            return

        raw = self._ref_text.get("1.0", "end-1c").strip()
        if not raw or raw == _REF_PLACEHOLDER:
            messagebox.showwarning("No Text", "Paste your source text first.", parent=self)
            return

        cfg = load_settings()
        api_key = cfg.get("api_key", "").strip()
        if not api_key:
            messagebox.showerror("No API Key", "API key missing. Visit Settings (⚙).", parent=self)
            return

        model = cfg.get("groq_model", "llama-3.1-8b-instant")

        # Step 1 — mask sensitive numbers, build lookup table
        masked_text, lookup_table = _build_privacy_table(raw)

        # Step 2 — persist lookup table AND original raw text for amount validation
        _PRIVACY_DB["lookup"]   = lookup_table
        _PRIVACY_DB["raw_text"] = raw

        self._autofill_btn.config(state="disabled", text="⏳  AI…")
        self._mon_status_var.set("⏳ sending…")
        self._mon_status_lbl.config(fg="#a87a1a")

        prompt = _build_prompt(json_type)
        self._monitor_show_request(json_type, model, masked_text, lookup_table, prompt)
        self.update_idletasks()

        def _worker():
            try:
                values, raw_ai_output = groq_extract(
                    masked_text, json_type, api_key, model, return_raw=True,
                )
                self.after(
                    0,
                    lambda: self._on_ai_success(
                        json_type, values, raw_ai_output, lookup_table, raw,
                    ),
                )
            except Exception as exc:
                self.after(0, lambda: self._on_ai_error(str(exc)))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_ai_success(self, json_type: str, values: dict,
                        raw_ai_output: dict, lookup_table: dict, raw_text: str):
        self._autofill_btn.config(state="normal", text="🤖  Autofill with AI")
        self._mon_status_var.set("✅ done")
        self._mon_status_lbl.config(fg="#3a6b3a")

        # Step 4 — restore masked values to originals (star-count-agnostic)
        restored = _restore_dict(values, lookup_table)

        # Step 5a — validate and correct amount fields against raw text
        amount_fixed = _normalise_restored_amounts(json_type, restored, raw_text)

        # Step 5b — normalise phone fields to correct prefix format
        final = _normalise_restored_phones(json_type, amount_fixed)

        self._monitor_show_response(raw_ai_output, restored, final)

        if not final:
            messagebox.showinfo("AI Result", "No values could be extracted.", parent=self)
            return

        # Step 6 — fill the form
        filled = []
        for key, var in self._entry_vars.items():
            if key in final and final[key]:
                var.set(final[key])
                filled.append(key)

        lines = [f"Filled {len(filled)} field(s)."]
        if lookup_table:
            lines += ["", f"🔒 {len(lookup_table)} number(s) masked in transit, restored after."]

        amt_field = _AMOUNT_FIELDS.get(json_type, "")
        if amt_field and amt_field in final:
            lines += ["", f"💰 Amount → {final[amt_field]}"]

        if json_type == "Beyonic":
            phone = final.get("PhoneNumber", "")
            if phone:
                lines += ["", f"📱 PhoneNumber → {phone}"]
        elif json_type == "Airtel":
            phone = final.get("customerReferenceNumber", "")
            if phone:
                lines += ["", f"📱 customerReferenceNumber & senderPhoneNumber → {phone}"]
            date_val = final.get("creationDate", "")
            if date_val:
                lines += ["", "📅 All three date fields set to:", f"   {date_val}"]
        elif json_type in ("Bank", "Flexipay"):
            phone = final.get("billRefNumber", "")
            if phone:
                lines += ["", f"📱 billRefNumber & mobile → {phone}"]

        messagebox.showinfo("Autofill Complete", "\n".join(lines), parent=self)

    def _on_ai_error(self, error_msg: str):
        self._autofill_btn.config(state="normal", text="🤖  Autofill with AI")
        self._mon_status_var.set("❌ error")
        self._mon_status_lbl.config(fg=MON_ERR_FG)
        self._monitor_show_error(error_msg)
        messagebox.showerror("AI Error", error_msg, parent=self)

    # ══════════════════════════════════════════════════════════════════════════
    # GENERATE / COPY / CLEAR
    # ══════════════════════════════════════════════════════════════════════════
    def _generate(self):
        json_type = self._json_type_var.get()
        JSON_FIELDS = get_json_fields()
        if json_type not in JSON_FIELDS:
            messagebox.showwarning("Error", "Select type first.", parent=self)
            return
        values = {k: v.get() for k, v in self._entry_vars.items()}
        blanks = [
            lbl for k, lbl, _d, _n in JSON_FIELDS[json_type]
            if not values.get(k, "").strip()
        ]
        if blanks:
            messagebox.showwarning("Missing Fields",
                                   "Please fill in all required fields.", parent=self)
            return
        payload  = build_json_payload(json_type, values)
        json_str = json.dumps(payload, ensure_ascii=False, indent=4)
        self._set_preview(json_str)

    def _copy_json(self):
        content = self._preview_text.get("1.0", "end-1c").strip()
        if not content or content == _PLACEHOLDER:
            messagebox.showinfo("Notice", "Click Generate first.", parent=self)
            return
        self.clipboard_clear()
        self.clipboard_append(content)
        self.update()
        messagebox.showinfo("Copied!", "JSON copied to clipboard.", parent=self)

    def _clear_fields(self):
        json_type = self._json_type_var.get()
        JSON_FIELDS = get_json_fields()
        if json_type in JSON_FIELDS:
            for k, _lbl, default, _n in JSON_FIELDS[json_type]:
                if k in self._entry_vars:
                    self._entry_vars[k].set(default)
        self._clear_preview()

    def _set_preview(self, text: str):
        self._preview_text.delete("1.0", "end")
        self._preview_text.insert("end", text)

    def _clear_preview(self):
        self._set_preview(_PLACEHOLDER)