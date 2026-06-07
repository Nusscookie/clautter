"""UI builder for the B-Roll Assistant tab.

Extracted from broll_tab.py so the tab file stays under 200 lines.
"""

from __future__ import annotations
from typing import Any

import customtkinter as ctk


def build(parent: Any) -> None:
    w: dict[str, Any] = {}

    ctk.CTkLabel(
        parent,
        text="B-ROLL ASSISTANT  —  Smart B-roll suggestions from transcript",
        font=ctk.CTkFont(size=11, weight="bold"),
        text_color="#aaaaaa",
        anchor="w",
    ).pack(fill="x", padx=12, pady=(12, 6))

    folder_card = ctk.CTkFrame(parent, fg_color="#2a2a2a", corner_radius=6)
    folder_card.pack(fill="x", padx=10, pady=4)

    ctk.CTkLabel(folder_card, text="LOCAL B-ROLL FOLDER",
                 font=ctk.CTkFont(size=10, weight="bold"),
                 text_color="#888888").pack(anchor="w", padx=10, pady=(8, 4))

    folder_row = ctk.CTkFrame(folder_card, fg_color="transparent")
    folder_row.pack(fill="x", padx=10, pady=(0, 8))
    folder_row.grid_columnconfigure(0, weight=1)

    w["folder"] = ctk.CTkEntry(folder_row, state="readonly",
                                placeholder_text="No folder selected.")
    w["folder"].grid(row=0, column=0, sticky="ew", padx=(0, 6))

    w["browse_btn"] = ctk.CTkButton(folder_row, text="Browse", width=80)
    w["browse_btn"].grid(row=0, column=1)

    w["suggest_local_btn"] = ctk.CTkButton(
        parent, text="Suggest Local B-Roll",
        fg_color="#1b5e20", hover_color="#2e7d32",
        state="disabled",
    )
    w["suggest_local_btn"].pack(fill="x", padx=10, pady=(4, 2))

    w["status"] = ctk.CTkLabel(
        parent, text="Browse a folder of local B-roll clips to start.",
        font=ctk.CTkFont(size=11), text_color="#aaaaaa", anchor="w", wraplength=800)
    w["status"].pack(fill="x", padx=12, pady=(4, 4))

    _divider(parent)

    # ── Online search card ─────────────────────────────────────────
    _build_online_card(parent, w)

    # ── Clip library / suggestions (bottom) ───────────────────────
    _divider(parent)

    ctk.CTkLabel(parent, text="CLIP LIBRARY  /  SUGGESTIONS",
                 font=ctk.CTkFont(size=10, weight="bold"),
                 text_color="#888888").pack(anchor="w", padx=12, pady=(8, 4))

    w["suggestions"] = ctk.CTkTextbox(parent, height=200, state="disabled",
                                       font=ctk.CTkFont(size=12))
    w["suggestions"].pack(fill="x", padx=10, pady=(0, 4))
    _set_textbox(w["suggestions"], "Browse a folder and click Suggest Local B-Roll...")

    w["place_btn"] = ctk.CTkButton(
        parent, text="Auto Place on Timeline",
        fg_color="#2a2a2a", hover_color="#3a3a3a",
        state="disabled",
    )
    w["place_btn"].pack(fill="x", padx=10, pady=(2, 4))

    ctk.CTkLabel(
        parent,
        text="Note: Requires transcript from the Subtitles tab. "
             "Auto Place (coming soon) places suggestions on V2 — "
             "V2 will be renamed to 'B-roll' then.",
        font=ctk.CTkFont(size=10),
        text_color="#555555",
        wraplength=800,
        anchor="w",
    ).pack(fill="x", padx=12, pady=(0, 8))

    _divider(parent)
    _build_advanced_card(parent, w)

    parent._w = w


def _set_textbox(tb: ctk.CTkTextbox, text: str) -> None:
    tb.configure(state="normal")
    tb.delete("0.0", "end")
    tb.insert("0.0", text)
    tb.configure(state="disabled")


def _divider(parent: Any) -> None:
    ctk.CTkFrame(parent, height=1, fg_color="#444444", corner_radius=0).pack(
        fill="x", padx=10, pady=4)


def _build_advanced_card(parent: Any, w: dict[str, Any]) -> None:
    """Collapsible advanced settings — keyword extraction method selector."""
    w["advanced_toggle"] = ctk.CTkButton(
        parent,
        text="▶  ADVANCED SETTINGS",
        font=ctk.CTkFont(size=10, weight="bold"),
        text_color="#888888",
        fg_color="transparent",
        hover_color="#1e1e1e",
        anchor="w",
        height=26,
        corner_radius=0,
    )
    w["advanced_toggle"].pack(fill="x", padx=10, pady=(2, 2))

    adv_frame = ctk.CTkFrame(parent, fg_color="#1e1e1e", corner_radius=4)
    w["advanced_frame"] = adv_frame
    # Not packed here — toggled by button in setup()

    method_row = ctk.CTkFrame(adv_frame, fg_color="transparent")
    method_row.pack(fill="x", padx=10, pady=8)

    ctk.CTkLabel(
        method_row, text="Keyword method:",
        font=ctk.CTkFont(size=11), text_color="#aaaaaa",
        width=130, anchor="w",
    ).pack(side="left")

    w["keyword_method"] = ctk.CTkOptionMenu(
        method_row,
        values=["spaCy (en_core_web_sm)", "YAKE", "KeyBERT", "Frequency (no deps)"],
        width=210,
        fg_color="#2a2a2a",
        button_color="#2a2a2a",
        button_hover_color="#3a3a3a",
    )
    w["keyword_method"].pack(side="left", padx=(6, 0))

    ctk.CTkLabel(
        adv_frame,
        text="KeyBERT and spaCy download a model (~80 MB) on first use.",
        font=ctk.CTkFont(size=10),
        text_color="#555555",
        anchor="w",
    ).pack(fill="x", padx=10, pady=(0, 8))


def _build_online_card(parent: Any, w: dict[str, Any]) -> None:
    """Construct the 'Search Online' card: provider + API keys + dl folder
    + top-N slider + primary search button + status label."""
    card = ctk.CTkFrame(parent, fg_color="#2a2a2a", corner_radius=6)
    card.pack(fill="x", padx=10, pady=(8, 4))

    ctk.CTkLabel(card, text="ONLINE B-ROLL SEARCH",
                 font=ctk.CTkFont(size=10, weight="bold"),
                 text_color="#888888").pack(anchor="w", padx=10, pady=(8, 4))

    # Provider + keys row
    prov_row = ctk.CTkFrame(card, fg_color="transparent")
    prov_row.pack(fill="x", padx=10, pady=(0, 4))
    prov_row.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(prov_row, text="Provider:",
                 font=ctk.CTkFont(size=11),
                 text_color="#aaaaaa").grid(row=0, column=0, padx=(0, 6), sticky="w")

    w["provider"] = ctk.CTkOptionMenu(
        prov_row,
        values=["Pixabay", "Pexels", "Both"],
        width=120,
        fg_color="#1e1e1e",
        button_color="#1e1e1e",
        button_hover_color="#3a3a3a",
    )
    w["provider"].grid(row=0, column=1, sticky="w")

    # Pixabay key
    px_row = ctk.CTkFrame(card, fg_color="transparent")
    px_row.pack(fill="x", padx=10, pady=(4, 2))
    px_row.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(px_row, text="Pixabay key:",
                 font=ctk.CTkFont(size=11),
                 text_color="#aaaaaa", width=110, anchor="w").grid(row=0, column=0, sticky="w")
    w["pixabay_key"] = ctk.CTkEntry(px_row, show="*", placeholder_text="Paste Pixabay API key")
    w["pixabay_key"].grid(row=0, column=1, sticky="ew")
    w["px_row"] = px_row

    # Pexels key
    pex_row = ctk.CTkFrame(card, fg_color="transparent")
    pex_row.pack(fill="x", padx=10, pady=(2, 4))
    pex_row.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(pex_row, text="Pexels key:",
                 font=ctk.CTkFont(size=11),
                 text_color="#aaaaaa", width=110, anchor="w").grid(row=0, column=0, sticky="w")
    w["pexels_key"] = ctk.CTkEntry(pex_row, show="*", placeholder_text="Paste Pexels API key")
    w["pexels_key"].grid(row=0, column=1, sticky="ew")
    w["pex_row"] = pex_row

    w["save_keys_btn"] = ctk.CTkButton(
        card, text="Save Keys",
        fg_color="#1f6aa5", hover_color="#144870",
        text_color="#ffffff", width=110,
    )
    w["save_keys_btn"].pack(anchor="w", padx=10, pady=(0, 6))

    w["provider_status"] = ctk.CTkLabel(
        card, text="",
        font=ctk.CTkFont(size=10),
        text_color="#aaaaaa", anchor="w", wraplength=800,
    )
    w["provider_status"].pack(fill="x", padx=10, pady=(0, 4))

    # Download target folder
    dl_row = ctk.CTkFrame(card, fg_color="transparent")
    dl_row.pack(fill="x", padx=10, pady=(4, 2))
    dl_row.grid_columnconfigure(0, weight=1)
    ctk.CTkLabel(dl_row, text="Download folder:",
                 font=ctk.CTkFont(size=11),
                 text_color="#aaaaaa").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))

    w["dl_folder"] = ctk.CTkEntry(dl_row, state="readonly",
                                   placeholder_text="No download folder selected.")
    w["dl_folder"].grid(row=1, column=0, sticky="ew", padx=(0, 6))

    w["dl_folder_btn"] = ctk.CTkButton(dl_row, text="Browse", width=80)
    w["dl_folder_btn"].grid(row=1, column=1)

    # Top-N slider
    topn_row = ctk.CTkFrame(card, fg_color="transparent")
    topn_row.pack(fill="x", padx=10, pady=(6, 2))
    topn_row.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(topn_row, text="Top-N keywords:",
                 font=ctk.CTkFont(size=11),
                 text_color="#aaaaaa", width=140, anchor="w").grid(row=0, column=0, sticky="w")

    w["top_n_value"] = ctk.CTkLabel(topn_row, text="10",
                                     font=ctk.CTkFont(size=11),
                                     text_color="#4fc3f7", width=24, anchor="e")
    w["top_n_value"].grid(row=0, column=2, padx=(6, 0))

    w["top_n_slider"] = ctk.CTkSlider(
        topn_row, from_=5, to=15, number_of_steps=10,
        progress_color="#4fc3f7",
    )
    w["top_n_slider"].grid(row=0, column=1, sticky="ew", padx=(6, 0))

    # Primary search button
    w["search_online_btn"] = ctk.CTkButton(
        card, text="Search Online for B-Roll",
        fg_color="#1b5e20", hover_color="#2e7d32",
        state="disabled",
    )
    w["search_online_btn"].pack(fill="x", padx=10, pady=(8, 4))

    w["search_status"] = ctk.CTkLabel(
        card, text="",
        font=ctk.CTkFont(size=11),
        text_color="#aaaaaa", anchor="w", wraplength=800,
    )
    w["search_status"].pack(fill="x", padx=10, pady=(0, 8))
