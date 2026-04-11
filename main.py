#!/usr/bin/env python
# coding: utf-8
# main.py
"""
4G WORKBENCH — Entry Point
"""
import os
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import getpass

from config import (
    DESKTOP, BEYONIC_DIR, FLEXIPAY_DIR, CLEANED_PATH, MAX_ROWS,
    THEME_BG, THEME_ACCENT, TEXT_COLOR,
    FONT_BODY, FONT_BOLD, FONT_HEADER, FONT_SMALL,
    MODE_OPTIONS, DATE_SEQUENCE_OPTIONS, DROPDOWN_PLACEHOLDER,
)
from backend import (normalize_raw_file, read_dataframe,
                    transform_beyonic, transform_flexipay,
                    save_chunks, resource_path)
from widgets import PreviewTree
from tab_csv import render_instructions
from tab_json import JsonGeneratorPanel
from settings_page import SettingsPanel
from reconcile_page import ReconcilePanel  # New Import

try:
    from notes_page import NotesPanel
except ImportError:
    class NotesPanel(tk.Frame):
        def __init__(self, parent, **kwargs):
            super().__init__(parent, bg="#ffffff", **kwargs)
            tk.Label(self, text="Notes Page Placeholder",
                     font=("Segoe UI", 20)).pack(pady=50)
        def show(self):     pass
        def autosave(self): pass

_LICENSE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "LICENSE.txt"
)

def _open_license():
    if not os.path.exists(_LICENSE_PATH):
        messagebox.showinfo("Licence",
                            "LICENSE.txt not found in the application folder.")
        return
    try:
        if sys.platform.startswith("win"):
            os.startfile(_LICENSE_PATH)
        elif sys.platform == "darwin":
            subprocess.call(["open", _LICENSE_PATH])
        else:
            subprocess.call(["xdg-open", _LICENSE_PATH])
    except Exception as e:
        messagebox.showwarning("Could not open file", str(e))

 # ── uses app.icns on mac ────────────────────────────────────────────────────────────
class TransformerApp(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("4G Workbench")
        self.geometry("1180x940")
        self.configure(bg=THEME_BG)
        self.minsize(1000, 700)

        self.input_path     = None
        self.df_preview     = None
        self.df_transformed = None
        self.user_greeting  = getpass.getuser().replace(".", " ").title()

        self.mode_var          = tk.StringVar(value=DROPDOWN_PLACEHOLDER)
        self.date_sequence_var = tk.StringVar(value=DROPDOWN_PLACEHOLDER)

        try:
            self.iconbitmap(resource_path("app.ico"))
        except Exception:
            pass

        self._apply_styles()
        self._build_ui()
        self._mode_changed()
        self.protocol("WM_DELETE_WINDOW", self._on_app_close)

    def _on_app_close(self):
        try:
            self.notes_panel.autosave()
        except Exception:
            pass
        self.destroy()

    # ── styles ────────────────────────────────────────────────────────────
    def _apply_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TButton",
                        background=THEME_ACCENT, foreground=TEXT_COLOR,
                        font=FONT_BOLD)
        style.map("TButton", background=[("active", "#b58955")])
        style.configure("TLabel",
                        background=THEME_BG, foreground=TEXT_COLOR,
                        font=FONT_BODY)
        style.configure("Title.TLabel",
                        background=THEME_BG, foreground=TEXT_COLOR,
                        font=FONT_HEADER)
        style.configure("TNotebook",
                        background=THEME_BG, borderwidth=0)
        style.configure("TNotebook.Tab",
                        background="#FAF3E6", foreground=TEXT_COLOR,
                        font=FONT_BODY, padding=[10, 4])
        style.map("TNotebook.Tab",
                  background=[("selected", THEME_ACCENT)])

    # ── UI construction ───────────────────────────────────────────────────
    def _build_ui(self):
        # ── Header row ────────────────────────────────────────────────────
        header_row = tk.Frame(self, bg=THEME_BG)
        header_row.pack(fill="x", padx=15, pady=(10, 5))

        title_f = tk.Frame(header_row, bg=THEME_BG)
        title_f.pack(side="left")
        tk.Label(title_f,
                 text="4G TECH WORKBENCH",
                 font=("Segoe UI", 12, "bold"),
                 bg=THEME_BG, fg=TEXT_COLOR).pack(anchor="w")
        tk.Label(title_f,
                 text="Thoughtfully designed and developed by the Tech Team",
                 font=("Segoe UI", 9),
                 bg=THEME_BG, fg="#8A7A6A").pack(anchor="w")

        top_right = tk.Frame(header_row, bg=THEME_BG)
        top_right.pack(side="right")

        greeting_row = tk.Frame(top_right, bg=THEME_BG)
        greeting_row.pack(anchor="e")
        tk.Label(greeting_row,
                 text=f"Greetings, {self.user_greeting} ",
                 font=FONT_SMALL, bg=THEME_BG, fg="#7A614A").pack(side="left")
        tk.Label(greeting_row,
                 text="Twende Vita!",
                 font=("Segoe UI", 10, "bold"),
                 bg=THEME_BG, fg=THEME_ACCENT).pack(side="left")

        icons_f = tk.Frame(top_right, bg=THEME_BG)
        icons_f.pack(anchor="e", pady=(5, 0))

        # Reconcile icon (NEW)
        recon_btn_f = tk.Frame(icons_f, bg=THEME_BG)
        recon_btn_f.pack(side="left", padx=15)
        tk.Button(recon_btn_f, text="⚖",
                  font=("Segoe UI Symbol", 16),
                  bg=THEME_BG, fg=TEXT_COLOR,
                  activebackground=THEME_ACCENT,
                  relief="flat", bd=0, cursor="hand2",
                  command=self._toggle_reconcile).pack()
        tk.Label(recon_btn_f, text="Reconcile",
                 font=FONT_SMALL, bg=THEME_BG, fg=TEXT_COLOR).pack()

        # Notes icon
        notes_btn_f = tk.Frame(icons_f, bg=THEME_BG)
        notes_btn_f.pack(side="left", padx=15)
        tk.Button(notes_btn_f, text="📝",
                  font=("Segoe UI Symbol", 16),
                  bg=THEME_BG, fg=TEXT_COLOR,
                  activebackground=THEME_ACCENT,
                  relief="flat", bd=0, cursor="hand2",
                  command=self._toggle_notes).pack()
        tk.Label(notes_btn_f, text="Notes",
                 font=FONT_SMALL, bg=THEME_BG, fg=TEXT_COLOR).pack()

        # Settings icon
        set_btn_f = tk.Frame(icons_f, bg=THEME_BG)
        set_btn_f.pack(side="left", padx=5)
        tk.Button(set_btn_f, text="⚙",
                  font=("Segoe UI Symbol", 18, "bold"),
                  bg=THEME_BG, fg=TEXT_COLOR,
                  activebackground=THEME_ACCENT,
                  relief="flat", bd=0, cursor="hand2",
                  command=self._toggle_settings).pack()
        tk.Label(set_btn_f, text="Settings",
                 font=FONT_SMALL, bg=THEME_BG, fg=TEXT_COLOR).pack()

        # ── Instruction panel ─────────────────────────────────────────────
        self.instruction_outer = tk.Frame(self, bg=THEME_BG, padx=10, pady=5)
        self.instruction_outer.pack(fill="x", padx=15)

        self.user_action_frame = tk.Frame(self.instruction_outer, bg=THEME_BG)
        self.user_action_frame.pack(side="left", fill="both", expand=True)

        self._sep1 = ttk.Separator(self.instruction_outer, orient="vertical")
        self._sep1.pack(side="left", fill="y", padx=20)

        self.system_logic_frame = tk.Frame(self.instruction_outer, bg=THEME_BG)
        self.system_logic_frame.pack(side="left", fill="both", expand=True)

        self._sep2 = ttk.Separator(self.instruction_outer, orient="vertical")
        self.ref_guide_frame = tk.Frame(self.instruction_outer, bg=THEME_BG)

        ttk.Separator(self, orient="horizontal").pack(
            fill="x", padx=15, pady=(10, 5)
        )

        # ── Controls ──────────────────────────────────────────────────────
        self.main_ctrl_frame = tk.Frame(self, bg=THEME_BG, padx=15)
        self.main_ctrl_frame.pack(fill="x", pady=(5, 2))
        self._build_controls_left()

        # ── Notebook ──────────────────────────────────────────────────────
        self._build_notebook()

        # ── Overlays (hidden initially) ───────────────────────────────────
        self.settings_panel  = SettingsPanel(self)
        self.notes_panel     = NotesPanel(self)
        self.reconcile_panel = ReconcilePanel(self) # New Panel

        # ── Footer ────────────────────────────────────────────────────────
        self._build_footer()

    def _build_controls_left(self):
        # ── ROW 1: dropdowns ──────────────────────────────────────────────
        dropdown_row = tk.Frame(self.main_ctrl_frame, bg=THEME_BG)
        dropdown_row.pack(fill="x", pady=(0, 4))

        mode_f = tk.Frame(dropdown_row, bg=THEME_BG)
        mode_f.pack(side="left", padx=(0, 20))
        tk.Label(mode_f, text="Mode:", font=FONT_BOLD,
                 bg=THEME_BG, fg=TEXT_COLOR).pack(side="left", padx=(0, 5))
        self.mode_box = ttk.Combobox(
            mode_f, textvariable=self.mode_var,
            values=MODE_OPTIONS, state="readonly",
            width=14, font=FONT_BODY,
        )
        self.mode_box.bind("<<ComboboxSelected>>", self._mode_changed)
        self.mode_box.pack(side="left")

        date_f = tk.Frame(dropdown_row, bg=THEME_BG)
        self._date_order_frame = date_f
        date_f.pack(side="left")
        tk.Label(date_f, text="Original CSV Date Order:", font=FONT_BOLD,
                 bg=THEME_BG, fg=TEXT_COLOR).pack(side="left", padx=(0, 5))
        self.date_box = ttk.Combobox(
            date_f, textvariable=self.date_sequence_var,
            values=DATE_SEQUENCE_OPTIONS, state="readonly",
            width=12, font=FONT_BODY,
        )
        self.date_box.bind("<<ComboboxSelected>>", self._date_sequence_changed)
        self.date_box.pack(side="left")

        # ── ROW 2: transformation buttons ─────────────────────────────────
        self.btn_ctrl_frame = tk.Frame(self, bg=THEME_BG, padx=15)
        self.btn_ctrl_frame.pack(fill="x", pady=(0, 5))

        btn_row = tk.Frame(self.btn_ctrl_frame, bg=THEME_BG)
        btn_row.pack(side="left")

        self.btn_load = ttk.Button(btn_row, text="1. 📂 Load File",
                                   command=self.load_file, state="disabled")
        self.btn_load.pack(side="left", padx=3)
        tk.Label(btn_row, text=" → ", font=("Segoe UI", 12),
                 bg=THEME_BG, fg=THEME_ACCENT).pack(side="left")
        self.btn_prev_orig = ttk.Button(btn_row, text="2. 📥 Original",
                                        command=self.preview_original,
                                        state="disabled")
        self.btn_prev_orig.pack(side="left", padx=3)
        tk.Label(btn_row, text=" → ", font=("Segoe UI", 12),
                 bg=THEME_BG, fg=THEME_ACCENT).pack(side="left")
        self.btn_prev_trans = ttk.Button(btn_row, text="3. ✨ Transformed",
                                         command=self.preview_transformed,
                                         state="disabled")
        self.btn_prev_trans.pack(side="left", padx=3)
        tk.Label(btn_row, text=" → ", font=("Segoe UI", 12),
                 bg=THEME_BG, fg=THEME_ACCENT).pack(side="left")
        self.btn_exec = ttk.Button(btn_row, text="4. ⚙️ Process",
                                   command=self.transform_action,
                                   state="disabled")
        self.btn_exec.pack(side="left", padx=3)

    def _build_notebook(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=15, pady=5)
        self.tab_orig       = ttk.Frame(self.notebook)
        self.tab_trans      = ttk.Frame(self.notebook)
        self.tab_json_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_orig,       text="  Original Data  ")
        self.notebook.add(self.tab_trans,      text="  Transformed Data  ")
        self.notebook.add(self.tab_json_frame, text="  🔧 JSON Tool  ")
        self.tree_orig  = PreviewTree(self.tab_orig)
        self.tree_orig.pack(fill="both", expand=True)
        self.tree_trans = PreviewTree(self.tab_trans)
        self.tree_trans.pack(fill="both", expand=True)
        self.json_panel = JsonGeneratorPanel(self.tab_json_frame)
        self.json_panel.pack(fill="both", expand=True)

    def _build_footer(self):
        footer = tk.Frame(self, bg="#c9a66b", height=35)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)
        tk.Label(footer, text="© 2026 4G Capital | Internal Systems",
                 font=("Segoe UI", 8), bg="#c9a66b", fg="#3a2f24").pack(side="left", padx=15, pady=5)
        tk.Label(footer, text="v1.0.3", font=("Segoe UI", 8),
                 bg="#c9a66b", fg="#5a4530").pack(side="right", padx=15, pady=5)
        lic = tk.Label(footer, text="📄 View Software Licence", font=("Segoe UI", 8, "underline"),
                       bg="#c9a66b", fg="#3a2f24", cursor="hand2")
        lic.pack(side="right", padx=15, pady=5)
        lic.bind("<Button-1>", lambda _: _open_license())

    # ── overlay show/hide ─────────────────────────────────────────────────
    def _show_overlay(self, panel):
        self.instruction_outer.pack_forget()
        self.main_ctrl_frame.pack_forget()
        self.btn_ctrl_frame.pack_forget()
        self.notebook.pack_forget()
        panel.pack(fill="both", expand=True, padx=15, pady=5)

    def _hide_overlay(self, panel):
        panel.pack_forget()
        self.instruction_outer.pack(fill="x", padx=15)
        self.main_ctrl_frame.pack(fill="x", pady=(5, 2))
        if self.mode_var.get() != "JSON Generator":
            self.btn_ctrl_frame.pack(fill="x", pady=(0, 5))
        self.notebook.pack(fill="both", expand=True, padx=15, pady=5)

    def _toggle_reconcile(self):
        for p in [self.settings_panel, self.notes_panel]:
            if p.winfo_ismapped(): self._hide_overlay(p)
        if self.reconcile_panel.winfo_ismapped():
            self._hide_overlay(self.reconcile_panel)
        else:
            self._show_overlay(self.reconcile_panel)

    def _toggle_notes(self):
        for p in [self.settings_panel, self.reconcile_panel]:
            if p.winfo_ismapped(): self._hide_overlay(p)
        if self.notes_panel.winfo_ismapped():
            self._hide_overlay(self.notes_panel)
        else:
            self._show_overlay(self.notes_panel)
            self.notes_panel.show()

    def _toggle_settings(self):
        for p in [self.notes_panel, self.reconcile_panel]:
            if p.winfo_ismapped(): self._hide_overlay(p)
        if self.settings_panel.winfo_ismapped():
            self._hide_overlay(self.settings_panel)
        else:
            self._show_overlay(self.settings_panel)
            self.settings_panel.show()

    def _mode_changed(self, event=None):
        mode = self.mode_var.get()
        self._clear_preview(keep_df=True)
        if mode == "JSON Generator":
            if not self._sep2.winfo_ismapped(): self._sep2.pack(side="left", fill="y", padx=20)
            if not self.ref_guide_frame.winfo_ismapped(): self.ref_guide_frame.pack(side="left", fill="both", expand=True)
        else:
            if self._sep2.winfo_ismapped(): self._sep2.pack_forget()
            if self.ref_guide_frame.winfo_ismapped(): self.ref_guide_frame.pack_forget()

        render_instructions(self.user_action_frame, self.system_logic_frame, mode,
                            self.ref_guide_frame if mode == "JSON Generator" else None)
        self._update_tab_states(mode)
        self._update_controls()

    def _update_tab_states(self, mode):
        if mode == "JSON Generator":
            if self._date_order_frame.winfo_ismapped(): self._date_order_frame.pack_forget()
            if self.btn_ctrl_frame.winfo_ismapped(): self.btn_ctrl_frame.pack_forget()
            self.notebook.tab(0, state="hidden"); self.notebook.tab(1, state="hidden")
            self.notebook.tab(2, state="normal"); self.notebook.select(self.tab_json_frame)
        else:
            if not self._date_order_frame.winfo_ismapped(): self._date_order_frame.pack(side="left")
            if not self.btn_ctrl_frame.winfo_ismapped(): self.btn_ctrl_frame.pack(fill="x", pady=(0, 5), before=self.notebook)
            self.notebook.tab(0, state="normal"); self.notebook.tab(1, state="normal")
            self.notebook.tab(2, state="disabled"); self.notebook.select(self.tab_orig)

    def _date_sequence_changed(self, event=None):
        self._clear_preview(keep_df=True); self._update_controls()

    def _update_controls(self):
        mode = self.mode_var.get(); is_json = mode == "JSON Generator"
        self.date_box.config(state="disabled" if is_json else "readonly")
        if is_json:
            for btn in (self.btn_load, self.btn_prev_orig, self.btn_prev_trans, self.btn_exec): btn.config(state="disabled")
            return
        mode_ok = mode in ("Beyonic", "FlexiPay"); date_ok = self.date_sequence_var.get() in DATE_SEQUENCE_OPTIONS
        file_ok = self.df_preview is not None; can_run = mode_ok and date_ok and file_ok
        self.btn_load.config(state="normal" if mode_ok else "disabled")
        self.btn_prev_orig.config(state="normal" if file_ok else "disabled")
        self.btn_prev_trans.config(state="normal" if can_run else "disabled")
        self.btn_exec.config(state="normal" if can_run else "disabled")

    def _clear_preview(self, keep_df=False):
        self.tree_trans.clear(); self.df_transformed = None
        if not keep_df: self.tree_orig.clear(); self.df_preview = None
        self._update_controls()

    def load_file(self):
        path = filedialog.askopenfilename(title="Select CSV", filetypes=[("CSV", "*.csv;*.txt"), ("All", "*.*")])
        if not path: return
        self.input_path = path; self._clear_preview(keep_df=False)
        try:
            normalize_raw_file(path, CLEANED_PATH, self.mode_var.get(), None)
            self.df_preview = read_dataframe(CLEANED_PATH, None)
            self.preview_original(); self._update_controls()
        except Exception as e: messagebox.showerror("Load Error", str(e))

    def preview_original(self):
        if self.df_preview is not None: self.tree_orig.display(self.df_preview, MAX_ROWS); self.notebook.select(self.tab_orig)

    def preview_transformed(self):
        try:
            mode = self.mode_var.get(); seq = self.date_sequence_var.get()
            df_out = transform_beyonic(self.df_preview.copy(), seq, None) if mode == "Beyonic" else transform_flexipay(self.df_preview.copy(), seq, None)
            self.df_transformed = df_out; self.tree_trans.display(df_out, MAX_ROWS); self.notebook.select(self.tab_trans)
        except Exception as e: messagebox.showerror("Preview Error", str(e))

    def transform_action(self):
        mode = self.mode_var.get(); seq = self.date_sequence_var.get()
        try:
            df_out = transform_beyonic(self.df_preview.copy(), seq, None) if mode == "Beyonic" else transform_flexipay(self.df_preview.copy(), seq, None)
            self.df_transformed = df_out; out_dir = BEYONIC_DIR if mode == "Beyonic" else FLEXIPAY_DIR
            saved = save_chunks(df_out, out_dir, mode, None)
            self.tree_trans.display(df_out, MAX_ROWS); self.notebook.select(self.tab_trans)
            messagebox.showinfo("Success", f"Saved {len(saved)} file(s) to:\n{out_dir}")
        except Exception as e: messagebox.showerror("Error", str(e))

if __name__ == "__main__":
    app = TransformerApp()
    app.mainloop()