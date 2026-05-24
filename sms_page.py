"""
SMS Blast Panel — 4G Workbench
Upload CSV → compose template with clickable placeholders → preview → export
"""
import os
import re
import csv
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime

try:
    import pandas as pd
    _HAS_PANDAS = True
except ImportError:
    _HAS_PANDAS = False

# ── Paths ─────────────────────────────────────────────────────────────────────
DESKTOP   = os.path.join(os.path.expanduser("~"), "Desktop")
BLAST_DIR = os.path.join(DESKTOP, "Blast-SMS")

def _ensure_blast_dir():
    os.makedirs(BLAST_DIR, exist_ok=True)

# ── Country config ────────────────────────────────────────────────────────────
COUNTRY_CONFIG = {
    "🇺🇬  Uganda (+256)": {"prefix": "256", "strip": ["0", "+256", "256"]},
    "🇰🇪  Kenya  (+254)": {"prefix": "254", "strip": ["0", "+254", "254"]},
}
COUNTRY_DISPLAY = list(COUNTRY_CONFIG.keys())

# ── Helpers ───────────────────────────────────────────────────────────────────
def _clean_phone(raw: str, prefix: str, strips: list) -> str:
    num = re.sub(r"\s+", "", str(raw).strip())
    for s in sorted(strips, key=len, reverse=True):
        if num.startswith(s):
            num = num[len(s):]
            break
    return prefix + num

def _read_csv(path: str):
    if _HAS_PANDAS:
        df = pd.read_csv(path, dtype=str).fillna("")
        return list(df.columns), df.to_dict(orient="records")
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        records = [{k: str(v) for k, v in row.items()} for row in reader]
        headers = list(records[0].keys()) if records else []
    return headers, records


# ─────────────────────────────────────────────────────────────────────────────
class SmsPanel(tk.Frame):

    BG         = "#FAF3E6"
    HINT_COLOR = "#9e9e9e"
    ACCENT     = "#c9a66b"
    GREEN      = "#2e7d32"
    ORANGE     = "#ef6c00"
    BLUE       = "#283593"

    TEMPLATE_HINT = (
        "Type your SMS here. Use the placeholder dropdown on the left to insert fields at the cursor."
    )

    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=self.BG, **kwargs)
        self.headers:   list = []
        self.records:   list = []
        self.ready_df:  list = []
        self._template_has_hint = True

        self.country_var     = tk.StringVar(value=COUNTRY_DISPLAY[0])
        self.placeholder_var = tk.StringVar(value="— select placeholder —")
        self.first_name_var  = tk.BooleanVar(value=False)

        self.country_var.trace_add("write", self._on_country_change)

        self._build_ui()

    # ─────────────────────────────────────────────────────────────────────
    # UI BUILD
    # ─────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        # ── TOP BAR (title + controls + template) ────────────────────────
        top_bar = tk.Frame(self, bg="#fff8ee", bd=1, relief="solid")
        top_bar.pack(fill="x", padx=10, pady=(8, 4))

        # Row 1: title left, controls right
        row1 = tk.Frame(top_bar, bg="#fff8ee")
        row1.pack(fill="x", padx=10, pady=(6, 3))

        # Title + workflow hint
        info = tk.Frame(row1, bg="#fff8ee")
        info.pack(side="left", fill="both", expand=True)

        tk.Label(info, text="💬  SMS Blast Composer",
                 font=("Segoe UI", 11, "bold"),
                 bg="#fff8ee", fg="#3a2f24").pack(anchor="w")

        hint_f = tk.Frame(info, bg="#fff8ee")
        hint_f.pack(anchor="w", pady=(1, 0))
        steps = [
            ("YOU",    "#c9a66b",
             "① Upload CSV  ② Write template using placeholders  ③ Preview  ④ Save CSV"),
            ("SYSTEM", "#2e7d32",
             "Cleans phone numbers · substitutes placeholders · exports 2-col file → Desktop/Blast-SMS/"),
        ]
        for role, color, text in steps:
            r = tk.Frame(hint_f, bg="#fff8ee")
            r.pack(anchor="w")
            tk.Label(r, text=f"[{role}]", font=("Segoe UI", 8, "bold"),
                     bg="#fff8ee", fg=color, width=7, anchor="e").pack(side="left")
            tk.Label(r, text=text, font=("Segoe UI", 8),
                     bg="#fff8ee", fg="#5a4530").pack(side="left", padx=(4, 0))

        # Controls: country, name toggle, reset
        ctrl = tk.Frame(row1, bg="#fff8ee")
        ctrl.pack(side="right", padx=(12, 0))

        cf = tk.Frame(ctrl, bg="#fff8ee")
        cf.pack(anchor="e", pady=(0, 3))
        tk.Label(cf, text="Country:", font=("Segoe UI", 9, "bold"),
                 bg="#fff8ee", fg="#3a2f24").pack(side="left", padx=(0, 5))
        self.country_box = ttk.Combobox(
            cf, textvariable=self.country_var,
            values=COUNTRY_DISPLAY, state="readonly", width=20,
            font=("Segoe UI", 9))
        self.country_box.pack(side="left")

        tk.Button(ctrl, text="🔄 Reset All",
                  font=("Segoe UI", 8, "bold"),
                  bg="#d4b896", fg="#3a2f24",
                  relief="flat", cursor="hand2",
                  command=self._reset).pack(anchor="e")

        # Separator
        ttk.Separator(top_bar, orient="horizontal").pack(
            fill="x", padx=0, pady=(4, 0))

        # Row 2: placeholder selector (left) + template textarea (right)
        row2 = tk.Frame(top_bar, bg="#fff8ee")
        row2.pack(fill="x", padx=10, pady=(6, 8))

        # Placeholder column
        ph_col = tk.Frame(row2, bg="#fff8ee", width=200)
        ph_col.pack(side="left", fill="y", padx=(0, 12))
        ph_col.pack_propagate(False)

        tk.Label(ph_col, text="📌 Placeholder",
                 font=("Segoe UI", 9, "bold"),
                 bg="#fff8ee", fg="#3a2f24").pack(anchor="w")
        tk.Label(ph_col,
                 text="Click in the template →\nthen select to insert at cursor.",
                 font=("Segoe UI", 8), bg="#fff8ee", fg="#7A614A",
                 justify="left").pack(anchor="w", pady=(2, 5))

        self.ph_box = ttk.Combobox(
            ph_col, textvariable=self.placeholder_var,
            values=[], state="readonly", width=24,
            font=("Segoe UI", 9))
        self.ph_box.pack(anchor="w")
        self.ph_box.bind("<<ComboboxSelected>>", self._insert_placeholder)

        tk.Label(ph_col,
                 text="Used placeholders are\nremoved from this list.",
                 font=("Segoe UI", 7), bg="#fff8ee", fg="#9e9e9e",
                 justify="left").pack(anchor="w", pady=(4, 0))

        # Template column
        tmpl_col = tk.Frame(row2, bg="#fff8ee")
        tmpl_col.pack(side="left", fill="both", expand=True)

        tmpl_hdr = tk.Frame(tmpl_col, bg="#fff8ee")
        tmpl_hdr.pack(fill="x", pady=(0, 4))

        tk.Label(tmpl_hdr, text="SMS Template",
                 font=("Segoe UI", 9, "bold"),
                 bg="#fff8ee", fg="#3a2f24").pack(side="left")

        # Checkbox lives right beside the title
        self.chk_firstname = tk.Checkbutton(
            tmpl_hdr,
            text="Use first name only",
            variable=self.first_name_var,
            bg="#fff8ee", font=("Segoe UI", 8),
            fg="#3a2f24", selectcolor="#fff8ee",
            command=self._on_option_change)
        self.chk_firstname.pack(side="left", padx=(10, 0))

        # Char counter + Preview button on the right of the header
        self.lbl_char = tk.Label(tmpl_hdr, text="Characters: 0",
                                  font=("Segoe UI", 8),
                                  bg="#fff8ee", fg="#555")
        self.lbl_char.pack(side="right", padx=(8, 0))

        tk.Button(tmpl_hdr, text="👁 Preview SMS",
                  font=("Segoe UI", 8, "bold"),
                  bg=self.ORANGE, fg="white",
                  relief="flat", cursor="hand2",
                  command=self._build_preview).pack(side="right", padx=(8, 0))

        self.txt_template = tk.Text(
            tmpl_col, height=4,
            font=("Segoe UI", 10),
            bg="#fffdf7", fg=self.HINT_COLOR,
            wrap="word", relief="sunken", bd=1,
            padx=6, pady=4)
        self.txt_template.insert("1.0", self.TEMPLATE_HINT)
        self.txt_template.pack(fill="both", expand=True)
        self.txt_template.bind("<FocusIn>",    self._clear_hint)
        self.txt_template.bind("<FocusOut>",   self._restore_hint)
        self.txt_template.bind("<KeyRelease>", self._on_template_edit)

        # ── BOTTOM: two-panel work area ───────────────────────────────────
        work = tk.Frame(self, bg=self.BG)
        work.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        # Equal 50/50 split — uniform group locks them to identical width
        work.grid_columnconfigure(0, weight=1, uniform="panels")
        work.grid_columnconfigure(1, weight=1, uniform="panels")
        work.grid_rowconfigure(0, weight=1)

        # ── COL 0: Raw Data (narrow) ──────────────────────────────────────
        raw_panel = tk.Frame(work, bg=self.BG, bd=1, relief="ridge")
        raw_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        rh = tk.Frame(raw_panel, bg="#e8f5e9")
        rh.pack(fill="x")
        tk.Label(rh, text="① Raw Data",
                 font=("Segoe UI", 9, "bold"),
                 bg="#e8f5e9", fg=self.GREEN).pack(side="left", padx=6, pady=4)
        tk.Button(rh, text="📂 Upload CSV",
                  font=("Segoe UI", 8, "bold"),
                  bg=self.GREEN, fg="white",
                  relief="flat", cursor="hand2",
                  command=self._load_csv).pack(side="right", padx=6, pady=4)

        self.lbl_file = tk.Label(raw_panel,
                                  text="No file loaded",
                                  font=("Segoe UI", 8),
                                  bg=self.BG, fg=self.HINT_COLOR)
        self.lbl_file.pack(anchor="w", padx=6, pady=(2, 0))

        raw_tree_f = tk.Frame(raw_panel, bg="white")
        raw_tree_f.pack(fill="both", expand=True, padx=3, pady=3)
        self.tree_raw = self._make_tree(raw_tree_f)

        self.lbl_raw_count = tk.Label(raw_panel, text="Total rows: 0",
                                       font=("Segoe UI", 8, "bold"),
                                       bg=self.BG, fg="#3a2f24")
        self.lbl_raw_count.pack(anchor="e", padx=6, pady=(0, 3))

        # ── COL 1: Preview (wide) ─────────────────────────────────────────
        prev_panel = tk.Frame(work, bg=self.BG, bd=1, relief="ridge")
        prev_panel.grid(row=0, column=1, sticky="nsew")

        pvh = tk.Frame(prev_panel, bg="#e8eaf6")
        pvh.pack(fill="x")
        tk.Label(pvh, text="② SMS Preview",
                 font=("Segoe UI", 9, "bold"),
                 bg="#e8eaf6", fg=self.BLUE).pack(side="left", padx=6, pady=4)
        tk.Button(pvh, text="💾 Save CSV",
                  font=("Segoe UI", 8, "bold"),
                  bg=self.BLUE, fg="white",
                  relief="flat", cursor="hand2",
                  command=self._save_csv).pack(side="right", padx=6, pady=4)

        tk.Label(prev_panel,
                 text="Scroll right →  to read full message. Verify before saving.",
                 font=("Segoe UI", 8), bg=self.BG, fg="#7A614A").pack(
                     anchor="w", padx=6, pady=(3, 0))

        prev_tree_f = tk.Frame(prev_panel, bg="white")
        prev_tree_f.pack(fill="both", expand=True, padx=3, pady=3)
        self.tree_prev = self._make_tree_wide(prev_tree_f)

        bot = tk.Frame(prev_panel, bg=self.BG)
        bot.pack(fill="x", padx=6, pady=(0, 3))

        self.lbl_status = tk.Label(bot, text="",
                                    font=("Segoe UI", 8),
                                    bg=self.BG, fg=self.GREEN)
        self.lbl_status.pack(side="left")

        self.lbl_prev_count = tk.Label(bot, text="Total rows: 0",
                                        font=("Segoe UI", 8, "bold"),
                                        bg=self.BG, fg="#3a2f24")
        self.lbl_prev_count.pack(side="right")

    # ─────────────────────────────────────────────────────────────────────
    # TREE HELPERS
    # ─────────────────────────────────────────────────────────────────────
    def _attach_copy_menu(self, tree):
        """Right-click context menu: copy cell value or whole row."""
        menu = tk.Menu(tree, tearoff=0)

        def _copy_cell():
            col = tree._rc_col
            iid = tree._rc_iid
            if not iid:
                return
            cols = tree["columns"]
            try:
                ci   = list(cols).index(col)
                vals = tree.item(iid, "values")
                text = vals[ci] if ci < len(vals) else ""
            except (ValueError, IndexError):
                text = ""
            tree.clipboard_clear()
            tree.clipboard_append(text)

        def _copy_row():
            iid = tree._rc_iid
            if not iid:
                return
            vals = tree.item(iid, "values")
            tree.clipboard_clear()
            tree.clipboard_append("\t".join(str(v) for v in vals))

        menu.add_command(label="Copy cell",      command=_copy_cell)
        menu.add_command(label="Copy whole row", command=_copy_row)

        def _show_menu(event):
            iid     = tree.identify_row(event.y)
            col     = tree.identify_column(event.x)   # e.g. "#1", "#2"
            cols    = tree["columns"]
            try:
                ci       = int(col.lstrip("#")) - 1
                col_name = cols[ci] if 0 <= ci < len(cols) else ""
            except (ValueError, IndexError):
                col_name = ""
            tree._rc_iid = iid
            tree._rc_col = col_name
            if iid:
                tree.selection_set(iid)
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()

        tree._rc_iid = None
        tree._rc_col = None
        tree.bind("<Button-3>", _show_menu)   # Windows / Linux
        tree.bind("<Button-2>", _show_menu)   # macOS

    def _make_tree(self, parent):
        f = tk.Frame(parent, bg="white")
        f.pack(fill="both", expand=True)
        tree = ttk.Treeview(f, show="headings")
        vsb = ttk.Scrollbar(f, orient="vertical",   command=tree.yview)
        hsb = ttk.Scrollbar(f, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right",  fill="y")
        hsb.pack(side="bottom", fill="x")
        tree.pack(side="left",  fill="both", expand=True)
        self._attach_copy_menu(tree)
        return tree

    def _make_tree_wide(self, parent):
        f = tk.Frame(parent, bg="white")
        f.pack(fill="both", expand=True)
        tree = ttk.Treeview(f, show="headings")
        vsb = ttk.Scrollbar(f, orient="vertical",   command=tree.yview)
        hsb = ttk.Scrollbar(f, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right",  fill="y")
        hsb.pack(side="bottom", fill="x")
        tree.pack(side="left",  fill="both", expand=True)

        def _hscroll(event):
            tree.xview_scroll(-1 * (event.delta // 120), "units")
        tree.bind("<Shift-MouseWheel>", _hscroll)
        self._attach_copy_menu(tree)
        return tree

    def _display_in_tree(self, tree, columns, rows, col_widths=None):
        tree.delete(*tree.get_children())
        tree["columns"] = columns
        for i, col in enumerate(columns):
            w = col_widths[i] if col_widths else 120
            tree.heading(col, text=col)
            tree.column(col, width=w, minwidth=60, anchor="w", stretch=False)
        for row in rows:
            tree.insert("", "end", values=[str(row.get(c, "")) for c in columns])

    # ─────────────────────────────────────────────────────────────────────
    # TEMPLATE HINT
    # ─────────────────────────────────────────────────────────────────────
    def _clear_hint(self, event=None):
        if self._template_has_hint:
            self.txt_template.delete("1.0", "end")
            self.txt_template.config(fg="#222")
            self._template_has_hint = False

    def _restore_hint(self, event=None):
        if not self.txt_template.get("1.0", "end").strip():
            self.txt_template.insert("1.0", self.TEMPLATE_HINT)
            self.txt_template.config(fg=self.HINT_COLOR)
            self._template_has_hint = True

    def _get_template(self) -> str:
        if self._template_has_hint:
            return ""
        return self.txt_template.get("1.0", "end").strip()

    def _on_template_edit(self, event=None):
        n = len(self._get_template())
        self.lbl_char.config(text=f"Characters: {n}")
        self._refresh_placeholder_dropdown()

    # ─────────────────────────────────────────────────────────────────────
    # PLACEHOLDER DROPDOWN LOGIC
    # ─────────────────────────────────────────────────────────────────────
    def _refresh_placeholder_dropdown(self):
        if not self.headers:
            return
        tmpl = self._get_template()
        available = [
            f"{{{h}}}" for h in self.headers
            if f"{{{h}}}" not in tmpl
        ]
        self.ph_box.config(values=available if available else ["(all used)"])
        self.placeholder_var.set("— select placeholder —")

    def _insert_placeholder(self, event=None):
        val = self.placeholder_var.get()
        if not val or val.startswith("—") or val == "(all used)":
            return
        self._clear_hint()
        try:
            idx = self.txt_template.index(tk.INSERT)
        except tk.TclError:
            idx = "end"
        self.txt_template.insert(idx, val)
        self.txt_template.focus_set()
        self._on_template_edit()
        self.placeholder_var.set("— select placeholder —")

    # ─────────────────────────────────────────────────────────────────────
    # EVENTS
    # ─────────────────────────────────────────────────────────────────────
    def _on_option_change(self):
        if self.ready_df:
            self._build_preview()

    def _on_country_change(self, *_):
        if self.ready_df:
            self._build_preview()

    # ─────────────────────────────────────────────────────────────────────
    # CSV LOAD
    # ─────────────────────────────────────────────────────────────────────
    def _load_csv(self):
        path = filedialog.askopenfilename(
            title="Select SMS data CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        try:
            self.headers, self.records = _read_csv(path)
        except Exception as e:
            messagebox.showerror("Load Error", str(e))
            return

        if not self.headers:
            messagebox.showwarning("Empty File", "The CSV has no columns.")
            return

        self.lbl_file.config(
            text=f"📄  {os.path.basename(path)}",
            fg=self.GREEN)
        self._display_in_tree(self.tree_raw, self.headers, self.records,
                              col_widths=[110] * len(self.headers))
        self.lbl_raw_count.config(text=f"Total rows: {len(self.records)}")

        self._refresh_placeholder_dropdown()

        self.lbl_status.config(
            text=f"✔ Loaded {len(self.records)} rows · {len(self.headers)} columns  |  "
                 f"Write your template and click 👁 Preview SMS",
            fg=self.GREEN)

        self.ready_df = []
        self.tree_prev.delete(*self.tree_prev.get_children())
        self.lbl_prev_count.config(text="Total rows: 0")

    # ─────────────────────────────────────────────────────────────────────
    # PREVIEW / COMPILE
    # ─────────────────────────────────────────────────────────────────────
    def _build_preview(self):
        if not self.records:
            messagebox.showwarning("No Data", "Upload a CSV first.")
            return
        tmpl = self._get_template()
        if not tmpl:
            messagebox.showwarning("No Template", "Write an SMS template first.")
            return

        cfg        = COUNTRY_CONFIG[self.country_var.get()]
        first_only = self.first_name_var.get()

        name_col = next(
            (h for h in self.headers if "name" in h.lower()), None)

        phone_col = next(
            (h for h in self.headers
             if any(k in h.lower()
                    for k in ("mobile", "phone", "msisdn", "_no", "number"))),
            None)
        if phone_col is None:
            messagebox.showwarning(
                "Phone Column Not Found",
                "Cannot detect a phone-number column.\n"
                "Make sure a column header contains:\n"
                "'mobile', 'phone', 'msisdn', or 'number'.")
            return

        self.ready_df = []
        errors = []
        for i, rec in enumerate(self.records, start=1):
            try:
                sub = {}
                for h in self.headers:
                    val = str(rec.get(h, "")).strip()
                    if h == name_col and first_only:
                        val = val.split()[0] if val else val
                    sub[h] = val

                sms = tmpl
                for k, v in sub.items():
                    sms = sms.replace(f"{{{k}}}", v)

                phone = _clean_phone(
                    rec.get(phone_col, ""),
                    cfg["prefix"], cfg["strip"])

                self.ready_df.append({"Mobile_no": phone, "Blast": sms})
            except Exception as e:
                errors.append(f"Row {i}: {e}")

        if errors:
            messagebox.showwarning(
                "Some Rows Had Errors",
                "\n".join(errors[:10]) +
                ("\n…and more" if len(errors) > 10 else ""))

        self._display_in_tree(
            self.tree_prev,
            ["Mobile_no", "Blast"],
            self.ready_df,
            col_widths=[160, 900])

        self.lbl_prev_count.config(text=f"Total rows: {len(self.ready_df)}")
        self.lbl_status.config(
            text=f"✔ {len(self.ready_df)} messages compiled  |  "
                 f"Scroll right to read full messages  |  Click 💾 Save CSV when ready",
            fg=self.GREEN)

    # ─────────────────────────────────────────────────────────────────────
    # SAVE
    # ─────────────────────────────────────────────────────────────────────
    def _save_csv(self):
        if not self.ready_df:
            messagebox.showwarning("Nothing to Save", "Build a preview first.")
            return
        _ensure_blast_dir()
        ts           = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"blast_sms_{ts}.csv"
        path = filedialog.asksaveasfilename(
            initialdir=BLAST_DIR,
            initialfile=default_name,
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")])
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["Mobile_no", "Blast"])
            writer.writeheader()
            writer.writerows(self.ready_df)
        messagebox.showinfo(
            "Saved ✔",
            f"{len(self.ready_df)} messages saved to:\n{path}")
        self.lbl_status.config(
            text=f"✔ Saved → {os.path.basename(path)}", fg=self.GREEN)

    # ─────────────────────────────────────────────────────────────────────
    # RESET
    # ─────────────────────────────────────────────────────────────────────
    def _reset(self):
        self.headers  = []
        self.records  = []
        self.ready_df = []

        self.lbl_file.config(text="No file loaded", fg=self.HINT_COLOR)
        if not self._template_has_hint:
            self.txt_template.delete("1.0", "end")
            self.txt_template.insert("1.0", self.TEMPLATE_HINT)
            self.txt_template.config(fg=self.HINT_COLOR)
            self._template_has_hint = True

        self.tree_raw.delete(*self.tree_raw.get_children())
        self.tree_prev.delete(*self.tree_prev.get_children())
        self.lbl_raw_count.config(text="Total rows: 0")
        self.lbl_prev_count.config(text="Total rows: 0")
        self.lbl_char.config(text="Characters: 0")
        self.lbl_status.config(text="")
        self.ph_box.config(values=[])
        self.placeholder_var.set("— select placeholder —")
        self.first_name_var.set(False)
        self.country_var.set(COUNTRY_DISPLAY[0])

    def show(self):
        pass