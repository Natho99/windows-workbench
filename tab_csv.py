"""
Instruction panel renderer.
Optimized to minimize vertical height for all modes, specifically JSON Generator.
"""
import tkinter as tk
from tkinter import ttk

from config import (
    THEME_BG, TEXT_COLOR, TEXT_ERROR,
    FONT_BODY, FONT_BOLD, FONT_TITLE,
)

def render_instructions(
    left_frame: tk.Frame,
    right_frame: tk.Frame,
    mode: str,
    ref_frame: tk.Frame | None = None,
):
    """
    Clear frames and render instructions.
    JSON Mode uses a condensed 3-column layout to minimize height.
    """
    for f in filter(None, [left_frame, right_frame, ref_frame]):
        for w in f.winfo_children():
            w.destroy()

    # ── No mode selected ─────────────────────────────────────────────────────
    if mode not in ("Beyonic", "FlexiPay", "JSON Generator"):
        tk.Label(
            left_frame,
            text="Select a Mode above to view instructions.",
            font=FONT_BODY, bg=THEME_BG, fg=TEXT_COLOR,
        ).pack(anchor="w")
        return

    # ══════════════════════════════════════════════════════════════════════════
    # JSON GENERATOR MODE — Condensed 3-column layout
    # ══════════════════════════════════════════════════════════════════════════
    if mode == "JSON Generator":

        # ── Column 1: Tool Capabilities ──────────────────────────────────────
        tk.Label(left_frame, text="JSON GENERATOR", font=FONT_TITLE, 
                 bg=THEME_BG, fg=TEXT_COLOR, anchor="w").pack(fill="x")
        tk.Label(left_frame, text=(
            "• Supports: Beyonic, Airtel, Bank, Flexipay.\n"
            "• Prevents manual JSON syntax errors.\n"
            "• Auto-formats IDs (e.g., Bank 'S' prefix).\n"
            "🔒 Privacy: Masks customer numbers & Txn IDs before hitting AI (Groq)."
        ), font=FONT_BODY, bg=THEME_BG, fg=TEXT_COLOR, justify="left", anchor="w").pack(fill="x")

        # ── Column 2: Workflow ─────────────────────────────────────────────
        tk.Label(right_frame, text="QUICK STEPS", font=FONT_TITLE, 
                 bg=THEME_BG, fg=TEXT_COLOR, anchor="w").pack(fill="x")
        tk.Label(right_frame, text=(
            "1. Paste raw text into Reference Panel.\n"
            "2. Click 🤖 Autofill with AI (Groq).\n"
            "4. ⚙️ Generate ➔ 📋 Copy ➔ Paste to Shujaa."
        ), font=FONT_BODY, bg=THEME_BG, fg=TEXT_COLOR, justify="left", anchor="w").pack(fill="x")

        # ── Column 3: Persistence & AI ──────────────────────────────────────
        if ref_frame is not None:
            tk.Label(ref_frame, text="SETTINGS & DB", font=FONT_TITLE, 
                     bg=THEME_BG, fg=TEXT_COLOR, anchor="w").pack(fill="x")
            tk.Label(ref_frame, text=(
                "• ⚙ Settings: Update API keys & Txn Samples.\n"
                "• DB Persistence: Notes & Keys are never lost.\n"
                "• Sample IDs: Customize examples in settings."
            ), font=FONT_BODY, bg=THEME_BG, fg=TEXT_COLOR, justify="left", anchor="w").pack(fill="x")

        # Warning Bar for JSON Mode
        ttk.Separator(left_frame, orient="horizontal").pack(fill="x", pady=(4, 2))
        tk.Label(left_frame, text="Note: Always cross-check AI output with original data in Reference Holder.",
                 font=FONT_BOLD, bg=THEME_BG, fg=TEXT_ERROR).pack(anchor="w")
        return

    # ══════════════════════════════════════════════════════════════════════════
    # CSV MODES — Beyonic / FlexiPay (Condensed)
    # ══════════════════════════════════════════════════════════════════════════

    # Standard Bottom Warning for CSV modes
    bottom_warn = tk.Frame(left_frame, bg=THEME_BG)
    bottom_warn.pack(side="bottom", fill="x")
    ttk.Separator(bottom_warn, orient="horizontal").pack(fill="x", pady=(5, 2))
    tk.Label(bottom_warn, text="IMPORTANT: Verify transformed CSV data against original statement.",
             font=FONT_BOLD, bg=THEME_BG, fg=TEXT_ERROR).pack(fill="x")

    if mode == "FlexiPay":
        tk.Label(left_frame, text="USER ACTIONS", font=FONT_TITLE, 
                 bg=THEME_BG, fg=TEXT_COLOR, anchor="w").pack(fill="x")
        tk.Label(left_frame, font=FONT_BODY, bg=THEME_BG, fg=TEXT_COLOR, justify="left", anchor="w",
            text=(
                "• Clean File: Remove top labels and footers.\n"
                "• Clean Header: Keep only the column names row.\n"
                "• File Format: Save as .CSV before upload."
            )).pack(fill="x")

        tk.Label(right_frame, text="SYSTEM LOGIC", font=FONT_TITLE, 
                 bg=THEME_BG, fg=TEXT_COLOR, anchor="w").pack(fill="x")
        tk.Label(right_frame, font=FONT_BODY, bg=THEME_BG, fg=TEXT_COLOR, justify="left", anchor="w",
            text=(
                "• Filters for 'successful' cashins/merchants.\n"
                "• Standardizes dates (DD-MM-YYYY HH:MM:SS).\n"
                "• Export: Saved to Desktop/FLEXIPAY_TRANSFORMED."
            )).pack(fill="x")

    elif mode == "Beyonic":
        tk.Label(left_frame, text="USER ACTIONS", font=FONT_TITLE, 
                 bg=THEME_BG, fg=TEXT_COLOR, anchor="w").pack(fill="x")
        tk.Label(left_frame, font=FONT_BODY, bg=THEME_BG, fg=TEXT_COLOR, justify="left", anchor="w",
            text=(
                "• Direct Upload: Use the raw CSV download.\n"
                "• No editing required before processing.\n"
                "• Verify no exponential values are present."
            )).pack(fill="x")

        tk.Label(right_frame, text="SYSTEM LOGIC", font=FONT_TITLE, 
                 bg=THEME_BG, fg=TEXT_COLOR, anchor="w").pack(fill="x")
        tk.Label(right_frame, font=FONT_BODY, bg=THEME_BG, fg=TEXT_COLOR, justify="left", anchor="w",
            text=(
                "• Maps 7 columns and handles 'Id' vs 'TxnId'.\n"
                "• Standardizes dates (DD-MM-YYYY HH:MM:SS).\n"
                "• Export: Saved to Desktop/BEYONIC_TRANSFORMED."
            )).pack(fill="x")