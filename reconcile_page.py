# reconcile_page.py
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import pandas as pd
import os
from datetime import datetime
from reconcile import perform_reconciliation

class ReconcilePanel(tk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg="#FAF3E6", **kwargs)
        self.mpesa_df = None
        self.shujaa_df = None
        self.diff_shujaa = pd.DataFrame()
        self.diff_mpesa = pd.DataFrame()
        self._build_ui()

    def _build_ui(self):
        # Header - Descriptive name
        header_frame = tk.Frame(self, bg="#FAF3E6")
        header_frame.pack(fill="x", pady=5)
        
        tk.Label(header_frame, text="Reconciliation Engine", 
                 font=("Segoe UI", 12, "bold"), bg="#FAF3E6", fg="#3a2f24").pack()

        # --- Top Control Bar ---
        ctrl_bar = tk.Frame(self, bg="#FAF3E6")
        ctrl_bar.pack(fill="x", padx=10, pady=5)

        # M-Pesa Setup
        self.mpesa_box = tk.LabelFrame(ctrl_bar, text=" M-Pesa,Airtel,Beyonic etc Setup ", bg="#FAF3E6", 
                                       fg="#2e7d32", font=("Segoe UI", 9, "bold"), 
                                       highlightbackground="#2e7d32", highlightthickness=1)
        self.mpesa_box.pack(side="left", fill="both", expand=True, padx=5)
        
        tk.Button(self.mpesa_box, text="📂 Upload M-Pesa", command=self.load_mpesa).pack(pady=5)
        self.lbl_mpesa = tk.Label(self.mpesa_box, text="No file selected", bg="#FAF3E6", font=("Segoe UI", 8))
        self.lbl_mpesa.pack()
        
        m_ref_f = tk.Frame(self.mpesa_box, bg="#FAF3E6")
        m_ref_f.pack(pady=5)
        tk.Label(m_ref_f, text="Ref Col (Column with Transaction code):", bg="#FAF3E6", font=("Segoe UI", 8)).pack(side="left")
        self.mpesa_col_var = tk.StringVar()
        self.mpesa_dropdown = ttk.Combobox(m_ref_f, textvariable=self.mpesa_col_var, state="readonly", width=18)
        self.mpesa_dropdown.pack(side="left", padx=5)

        # Shujaa Setup
        self.shujaa_box = tk.LabelFrame(ctrl_bar, text=" Shujaa Setup ", bg="#FAF3E6", 
                                        fg="#ef6c00", font=("Segoe UI", 9, "bold"),
                                        highlightbackground="#ef6c00", highlightthickness=1)
        self.shujaa_box.pack(side="left", fill="both", expand=True, padx=5)

        tk.Button(self.shujaa_box, text="📂 Upload Shujaa", command=self.load_shujaa).pack(pady=5)
        self.lbl_shujaa = tk.Label(self.shujaa_box, text="No file selected", bg="#FAF3E6", font=("Segoe UI", 8))
        self.lbl_shujaa.pack()

        s_ref_f = tk.Frame(self.shujaa_box, bg="#FAF3E6")
        s_ref_f.pack(pady=5)
        tk.Label(s_ref_f, text="Ref Col (Column with Transaction code):", bg="#FAF3E6", font=("Segoe UI", 8)).pack(side="left")
        self.shujaa_col_var = tk.StringVar()
        self.shujaa_dropdown = ttk.Combobox(s_ref_f, textvariable=self.shujaa_col_var, state="readonly", width=18)
        self.shujaa_dropdown.pack(side="left", padx=5)

        # Action Execution Bar
        exec_bar = tk.Frame(self, bg="#FAF3E6")
        exec_bar.pack(fill="x", pady=10)
        
        btn_container = tk.Frame(exec_bar, bg="#FAF3E6")
        btn_container.pack(expand=True)

        tk.Button(btn_container, text="🚀 Run Reconciliation", bg="#c9a66b", fg="white", 
                  font=("Segoe UI", 10, "bold"), padx=20, command=self.run_recon).pack(side="left", padx=10)
        
        tk.Button(btn_container, text="🔄 Reset Process", bg="#d4b896", fg="#3a2f24", 
                  font=("Segoe UI", 10, "bold"), padx=20, command=self.reset_process).pack(side="left", padx=10)

        # --- Two-Column Results Area ---
        results_container = tk.Frame(self, bg="#FAF3E6")
        results_container.pack(fill="both", expand=True, padx=10, pady=5)
        results_container.grid_columnconfigure(0, weight=1, uniform="group1")
        results_container.grid_columnconfigure(1, weight=1, uniform="group1")
        results_container.grid_rowconfigure(0, weight=1)

        # Left Column Frame
        self.left_col = tk.Frame(results_container, bg="#FAF3E6", bd=1, relief="ridge")
        self.left_col.grid(row=0, column=0, sticky="nsew", padx=5)
        
        l_hdr = tk.Frame(self.left_col, bg="#e8f5e9")
        l_hdr.pack(fill="x")
        self.lbl_title_mpesa = tk.Label(l_hdr, text="M-Pesa Data", font=("Segoe UI", 9, "bold"), bg="#e8f5e9", fg="#2e7d32")
        self.lbl_title_mpesa.pack(side="left", padx=5)
        self.lbl_count_mpesa = tk.Label(l_hdr, text="Rows: 0", font=("Segoe UI", 8, "bold"), bg="#e8f5e9")
        self.lbl_count_mpesa.pack(side="right", padx=5)
        
        self.btn_dl_mpesa = tk.Button(self.left_col, text="📥 Download M-Pesa Gaps", state="disabled", font=("Segoe UI", 8),
                                      command=self.download_mpesa_gaps)
        self.btn_dl_mpesa.pack(fill="x")
        self.tree_mpesa = self._create_tree(self.left_col)

        # Right Column Frame
        self.right_col = tk.Frame(results_container, bg="#FAF3E6", bd=1, relief="ridge")
        self.right_col.grid(row=0, column=1, sticky="nsew", padx=5)
        
        r_hdr = tk.Frame(self.right_col, bg="#fff3e0")
        r_hdr.pack(fill="x")
        self.lbl_title_shujaa = tk.Label(r_hdr, text="Shujaa Data", font=("Segoe UI", 9, "bold"), bg="#fff3e0", fg="#ef6c00")
        self.lbl_title_shujaa.pack(side="left", padx=5)
        self.lbl_count_shujaa = tk.Label(r_hdr, text="Rows: 0", font=("Segoe UI", 8, "bold"), bg="#fff3e0")
        self.lbl_count_shujaa.pack(side="right", padx=5)
        
        self.btn_dl_shujaa = tk.Button(self.right_col, text="📥 Download Shujaa Gaps", state="disabled", font=("Segoe UI", 8),
                                       command=self.download_shujaa_gaps)
        self.btn_dl_shujaa.pack(fill="x")
        self.tree_shujaa = self._create_tree(self.right_col)

    def _create_tree(self, parent):
        container = tk.Frame(parent, bg="white")
        container.pack(fill="both", expand=True)
        tree = ttk.Treeview(container, show="headings")
        vsb = ttk.Scrollbar(container, orient="vertical", command=tree.yview)
        hsb = ttk.Scrollbar(container, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        tree.pack(side="left", fill="both", expand=True)
        return tree

    def load_mpesa(self):
        path = filedialog.askopenfilename(filetypes=[("CSV", "*.csv")])
        if path:
            self.mpesa_df = pd.read_csv(path)
            cols = list(self.mpesa_df.columns)
            self.mpesa_dropdown['values'] = cols
            self.mpesa_col_var.set("Receipt No." if "Receipt No." in cols else cols[0])
            self.lbl_mpesa.config(text=os.path.basename(path), fg="#2e7d32")
            self._display_df(self.tree_mpesa, self.mpesa_df)
            self.lbl_count_mpesa.config(text=f"Total: {len(self.mpesa_df)}")
            self.lbl_title_mpesa.config(text="M-Pesa Statement (Loaded)")

    def load_shujaa(self):
        path = filedialog.askopenfilename(filetypes=[("CSV", "*.csv")])
        if path:
            self.shujaa_df = pd.read_csv(path)
            cols = list(self.shujaa_df.columns)
            self.shujaa_dropdown['values'] = cols
            self.shujaa_col_var.set("Receipt No." if "Receipt No." in cols else cols[0])
            self.lbl_shujaa.config(text=os.path.basename(path), fg="#ef6c00")
            self._display_df(self.tree_shujaa, self.shujaa_df)
            self.lbl_count_shujaa.config(text=f"Total: {len(self.shujaa_df)}")
            self.lbl_title_shujaa.config(text="Shujaa Statement (Loaded)")

    def run_recon(self):
        if self.mpesa_df is None or self.shujaa_df is None:
            messagebox.showwarning("Warning", "Upload both statements first.")
            return
        m_col, s_col = self.mpesa_col_var.get(), self.shujaa_col_var.get()
        try:
            self.diff_shujaa, self.diff_mpesa = perform_reconciliation(self.mpesa_df, self.shujaa_df, m_col, s_col)
            
            # Row count and Percentage for M-Pesa gaps
            m_gaps = len(self.diff_mpesa)
            m_total = len(self.mpesa_df)
            m_perc = (m_gaps / m_total * 100) if m_total > 0 else 0
            
            self._display_df(self.tree_mpesa, self.diff_mpesa)
            self.lbl_title_mpesa.config(text="In M-Pesa, NOT in Shujaa")
            self.lbl_count_mpesa.config(text=f"{m_gaps}/{m_total} ({m_perc:.2f}%)")
            self.btn_dl_mpesa.config(state="normal" if not self.diff_mpesa.empty else "disabled")
            
            # Row count and Percentage for Shujaa gaps
            s_gaps = len(self.diff_shujaa)
            s_total = len(self.shujaa_df)
            s_perc = (s_gaps / s_total * 100) if s_total > 0 else 0

            self._display_df(self.tree_shujaa, self.diff_shujaa)
            self.lbl_title_shujaa.config(text="In Shujaa, NOT in M-Pesa")
            self.lbl_count_shujaa.config(text=f"{s_gaps}/{s_total} ({s_perc:.2f}%)")
            self.btn_dl_shujaa.config(state="normal" if not self.diff_shujaa.empty else "disabled")
            
            messagebox.showinfo("Success", "Reconciliation complete.")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def reset_process(self):
        self.mpesa_df = None
        self.shujaa_df = None
        self.diff_shujaa = pd.DataFrame()
        self.diff_mpesa = pd.DataFrame()
        self.lbl_mpesa.config(text="No file selected", fg="black")
        self.lbl_shujaa.config(text="No file selected", fg="black")
        self.mpesa_dropdown['values'] = []
        self.shujaa_dropdown['values'] = []
        self.mpesa_col_var.set("")
        self.shujaa_col_var.set("")
        self.tree_mpesa.delete(*self.tree_mpesa.get_children())
        self.tree_shujaa.delete(*self.tree_shujaa.get_children())
        self.lbl_count_mpesa.config(text="Rows: 0")
        self.lbl_count_shujaa.config(text="Rows: 0")
        self.lbl_title_mpesa.config(text="M-Pesa Data")
        self.lbl_title_shujaa.config(text="Shujaa Data")
        self.btn_dl_mpesa.config(state="disabled")
        self.btn_dl_shujaa.config(state="disabled")

    def _display_df(self, tree, df):
        tree.delete(*tree.get_children())
        cols = list(df.columns)
        tree["columns"] = cols
        for col in cols:
            tree.heading(col, text=col)
            tree.column(col, width=120, anchor="w")
        for _, row in df.iterrows():
            tree.insert("", "end", values=[str(x) for x in list(row)])

    def download_mpesa_gaps(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"payments_not_in_shujaa-but-in-mpesa_{timestamp}"
        self.save_csv(self.diff_mpesa, filename)

    def download_shujaa_gaps(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"payments_not_in_mpesa-but-in-shujaa_{timestamp}"
        self.save_csv(self.diff_shujaa, filename)

    def save_csv(self, df, default_name):
        path = filedialog.asksaveasfilename(defaultextension=".csv", 
                                            initialfile=default_name,
                                            filetypes=[("CSV", "*.csv")])
        if path:
            df.to_csv(path, index=False)
            messagebox.showinfo("Exported", f"Saved to {os.path.basename(path)}")