"""UI builder for the B-Roll Assistant tab.

Extracted from broll_tab.py so the tab file stays under 200 lines.
Two modes: Manual (existing flow) and Autonomous (agent runs end-to-end).
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

    # ── Mode toggle ────────────────────────────────────────────────
    w["mode_toggle"] = ctk.CTkSegmentedButton(
        parent,
        values=["Manual", "Autonomous"],
        font=ctk.CTkFont(size=12),
        selected_color="#1b5e20",
        selected_hover_color="#2e7d32",
        unselected_color="#2a2a2a",
        unselected_hover_color="#3a3a3a",
    )
    w["mode_toggle"].set("Manual")
    w["mode_toggle"].pack(fill="x", padx=10, pady=(0, 8))

    # ── Manual content container ───────────────────────────────────
    w["manual_container"] = ctk.CTkFrame(parent, fg_color="transparent")
    w["manual_container"].pack(fill="x")

    _build_manual_content(w["manual_container"], w)

    # ── Autonomous content container (hidden initially) ────────────
    w["auto_container"] = ctk.CTkFrame(parent, fg_color="transparent")
    # Not packed yet — shown when mode switches to Autonomous

    _build_autonomous_card(w["auto_container"], w)

    parent._w = w


def _build_manual_content(container: Any, w: dict[str, Any]) -> None:
    """Build all manual-mode widgets inside *container*."""
    folder_card = ctk.CTkFrame(container, fg_color="#2a2a2a", corner_radius=6)
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
        container, text="Suggest Local B-Roll",
        fg_color="#1b5e20", hover_color="#2e7d32",
        state="disabled",
    )
    w["suggest_local_btn"].pack(fill="x", padx=10, pady=(4, 2))

    w["status"] = ctk.CTkLabel(
        container, text="Browse a folder of local B-roll clips to start.",
        font=ctk.CTkFont(size=11), text_color="#aaaaaa", anchor="w", wraplength=800)
    w["status"].pack(fill="x", padx=12, pady=(4, 4))

    _divider(container)

    # ── Online search card ─────────────────────────────────────────
    _build_online_card(container, w)

    # ── Clip library / suggestions (bottom) ───────────────────────
    _divider(container)

    ctk.CTkLabel(container, text="CLIP LIBRARY  /  SUGGESTIONS",
                 font=ctk.CTkFont(size=10, weight="bold"),
                 text_color="#888888").pack(anchor="w", padx=12, pady=(8, 4))

    w["suggestions"] = ctk.CTkTextbox(container, height=200, state="disabled",
                                       font=ctk.CTkFont(size=12))
    w["suggestions"].pack(fill="x", padx=10, pady=(0, 4))
    _set_textbox(w["suggestions"], "Browse a folder and click Suggest Local B-Roll...")

    w["place_btn"] = ctk.CTkButton(
        container, text="Auto Place on Timeline",
        fg_color="#2a2a2a", hover_color="#3a3a3a",
        state="disabled",
    )
    w["place_btn"].pack(fill="x", padx=10, pady=(2, 4))

    ctk.CTkLabel(
        container,
        text="Note: Requires transcript from the Subtitles tab.",
        font=ctk.CTkFont(size=10),
        text_color="#555555",
        wraplength=800,
        anchor="w",
    ).pack(fill="x", padx=12, pady=(0, 8))


def _build_autonomous_card(container: Any, w: dict[str, Any]) -> None:
    """Build all autonomous-mode widgets inside *container*."""
    card = ctk.CTkFrame(container, fg_color="#2a2a2a", corner_radius=6)
    card.pack(fill="x", padx=10, pady=(4, 8))

    ctk.CTkLabel(card, text="AUTONOMOUS B-ROLL AGENT",
                 font=ctk.CTkFont(size=10, weight="bold"),
                 text_color="#888888").pack(anchor="w", padx=10, pady=(8, 4))

    ctk.CTkLabel(
        card,
        text="One click: extract keywords → search/match → rank → place on B-Roll track.",
        font=ctk.CTkFont(size=11),
        text_color="#aaaaaa",
        wraplength=760,
        anchor="w",
    ).pack(fill="x", padx=10, pady=(0, 8))

    _divider(card)

    # Sources row
    src_row = ctk.CTkFrame(card, fg_color="transparent")
    src_row.pack(fill="x", padx=10, pady=(8, 4))
    ctk.CTkLabel(src_row, text="Sources:", font=ctk.CTkFont(size=11),
                 text_color="#aaaaaa", width=80, anchor="w").pack(side="left")
    w["auto_use_local"] = ctk.CTkCheckBox(src_row, text="Local folder",
                                           font=ctk.CTkFont(size=11),
                                           checkbox_width=16, checkbox_height=16)
    w["auto_use_local"].pack(side="left", padx=(0, 16))
    w["auto_use_online"] = ctk.CTkCheckBox(src_row, text="Online search",
                                            font=ctk.CTkFont(size=11),
                                            checkbox_width=16, checkbox_height=16)
    w["auto_use_online"].pack(side="left")

    # Local folder row (shown when local source checked)
    auto_folder_row = ctk.CTkFrame(card, fg_color="transparent")
    auto_folder_row.pack(fill="x", padx=10, pady=(0, 4))
    auto_folder_row.grid_columnconfigure(0, weight=1)
    w["auto_folder"] = ctk.CTkEntry(auto_folder_row, state="readonly",
                                     placeholder_text="No local folder selected.")
    w["auto_folder"].grid(row=0, column=0, sticky="ew", padx=(0, 6))
    w["auto_browse_btn"] = ctk.CTkButton(auto_folder_row, text="Browse", width=80)
    w["auto_browse_btn"].grid(row=0, column=1)

    # Online provider + download folder
    online_row = ctk.CTkFrame(card, fg_color="transparent")
    online_row.pack(fill="x", padx=10, pady=(0, 4))
    online_row.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(online_row, text="Provider:", font=ctk.CTkFont(size=11),
                 text_color="#aaaaaa", width=80, anchor="w").grid(row=0, column=0, sticky="w")
    w["auto_provider"] = ctk.CTkOptionMenu(
        online_row,
        values=["Pixabay", "Pexels", "Both"],
        width=120,
        fg_color="#1e1e1e",
        button_color="#1e1e1e",
        button_hover_color="#3a3a3a",
    )
    w["auto_provider"].grid(row=0, column=1, sticky="w", pady=2)

    dl_row = ctk.CTkFrame(card, fg_color="transparent")
    dl_row.pack(fill="x", padx=10, pady=(0, 4))
    dl_row.grid_columnconfigure(0, weight=1)
    w["auto_dl_folder"] = ctk.CTkEntry(dl_row, state="readonly",
                                        placeholder_text="Download folder…")
    w["auto_dl_folder"].grid(row=0, column=0, sticky="ew", padx=(0, 6))
    w["auto_dl_browse_btn"] = ctk.CTkButton(dl_row, text="Browse", width=80)
    w["auto_dl_browse_btn"].grid(row=0, column=1)

    # LLM mode row
    llm_row = ctk.CTkFrame(card, fg_color="transparent")
    llm_row.pack(fill="x", padx=10, pady=(4, 4))
    ctk.CTkLabel(llm_row, text="LLM mode:", font=ctk.CTkFont(size=11),
                 text_color="#aaaaaa", width=80, anchor="w").pack(side="left")
    w["auto_llm_mode"] = ctk.CTkSegmentedButton(
        llm_row,
        values=["Off"],  # real provider segments are set at setup() from configured keys
        font=ctk.CTkFont(size=11),
        selected_color="#1b5e20",
        selected_hover_color="#2e7d32",
        unselected_color="#2a2a2a",
        unselected_hover_color="#3a3a3a",
        width=180,
    )
    w["auto_llm_mode"].set("Off")
    w["auto_llm_mode"].pack(side="left", padx=(6, 0))
    ctk.CTkLabel(
        llm_row,
        text="Pick a provider to let the LLM choose clips + positions. Only providers with an API key are shown.",
        font=ctk.CTkFont(size=10), text_color="#555555",
    ).pack(side="left", padx=(10, 0))

    # Max total clips slider
    max_clips_row = ctk.CTkFrame(card, fg_color="transparent")
    max_clips_row.pack(fill="x", padx=10, pady=(0, 4))
    max_clips_row.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(max_clips_row, text="Max total clips:", font=ctk.CTkFont(size=11),
                 text_color="#aaaaaa", width=110, anchor="w").grid(row=0, column=0, sticky="w")

    w["auto_max_clips_value"] = ctk.CTkLabel(
        max_clips_row, text="10",
        font=ctk.CTkFont(size=11), text_color="#D97757", width=28, anchor="e")
    w["auto_max_clips_value"].grid(row=0, column=2, padx=(6, 0))

    w["auto_max_clips"] = ctk.CTkSlider(
        max_clips_row, from_=1, to=30, number_of_steps=29,
        progress_color="#D97757",
    )
    w["auto_max_clips"].set(10)
    w["auto_max_clips"].grid(row=0, column=1, sticky="ew", padx=(6, 0))

    ctk.CTkLabel(
        card,
        text="Caps online downloads. Local folder clips always included.",
        font=ctk.CTkFont(size=10), text_color="#555555", anchor="w",
    ).pack(fill="x", padx=10, pady=(0, 4))

    # Clips per segment
    cps_row = ctk.CTkFrame(card, fg_color="transparent")
    cps_row.pack(fill="x", padx=10, pady=(0, 8))
    ctk.CTkLabel(cps_row, text="Clips/segment:", font=ctk.CTkFont(size=11),
                 text_color="#aaaaaa", width=110, anchor="w").pack(side="left")
    w["auto_clips_per_seg"] = ctk.CTkOptionMenu(
        cps_row,
        values=["1", "2", "3"],
        width=70,
        fg_color="#1e1e1e",
        button_color="#1e1e1e",
        button_hover_color="#3a3a3a",
    )
    w["auto_clips_per_seg"].set("1")
    w["auto_clips_per_seg"].pack(side="left")
    ctk.CTkLabel(cps_row, text="clips placed per transcript segment",
                 font=ctk.CTkFont(size=10), text_color="#555555").pack(side="left", padx=(8, 0))

    _divider(card)

    # Fill frame + Natural placement checkboxes
    placement_row = ctk.CTkFrame(card, fg_color="transparent")
    placement_row.pack(fill="x", padx=10, pady=(4, 2))

    w["auto_fill_frame"] = ctk.CTkCheckBox(
        placement_row,
        text="Fill Frame (no black bars)",
        font=ctk.CTkFont(size=11),
        checkbox_width=16, checkbox_height=16,
    )
    w["auto_fill_frame"].pack(side="left", padx=(0, 16))

    w["auto_natural_placement"] = ctk.CTkCheckBox(
        placement_row,
        text="Natural Placement (skip intro, space clips)",
        font=ctk.CTkFont(size=11),
        checkbox_width=16, checkbox_height=16,
    )
    w["auto_natural_placement"].pack(side="left")

    ctk.CTkLabel(
        card,
        text="Fill Frame: zoom-crops clips to fill frame.  "
             "Natural Placement: skips first 8s, enforces 5s gaps between clips, caps each clip at 5s.",
        font=ctk.CTkFont(size=10), text_color="#555555", anchor="w", wraplength=760,
    ).pack(fill="x", padx=10, pady=(0, 6))

    # Run button
    w["auto_run_btn"] = ctk.CTkButton(
        card,
        text="▶  Run Autonomous B-Roll",
        fg_color="#1b5e20", hover_color="#2e7d32",
        font=ctk.CTkFont(size=13, weight="bold"),
        height=38,
        state="disabled",
    )
    w["auto_run_btn"].pack(fill="x", padx=10, pady=(8, 4))

    # Progress bar (hidden until run starts)
    w["auto_progress_frame"] = ctk.CTkFrame(card, fg_color="transparent")
    w["auto_progress_frame"].pack(fill="x", padx=10, pady=(0, 2))
    w["auto_progress"] = ctk.CTkProgressBar(w["auto_progress_frame"], height=6,
                                              progress_color="#D97757")
    w["auto_progress"].set(0)

    w["auto_status"] = ctk.CTkLabel(
        card, text="Configure sources above, then click Run.",
        font=ctk.CTkFont(size=11), text_color="#aaaaaa", anchor="w", wraplength=760)
    w["auto_status"].pack(fill="x", padx=10, pady=(0, 10))


def _set_textbox(tb: ctk.CTkTextbox, text: str) -> None:
    tb.configure(state="normal")
    tb.delete("0.0", "end")
    tb.insert("0.0", text)
    tb.configure(state="disabled")


def _divider(parent: Any) -> None:
    ctk.CTkFrame(parent, height=1, fg_color="#444444", corner_radius=0).pack(
        fill="x", padx=10, pady=4)


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

    ctk.CTkLabel(
        card,
        text="Pixabay / Pexels API keys → Settings  ( ⚙ top-right )",
        font=ctk.CTkFont(size=11), text_color="#888888", anchor="w",
    ).pack(fill="x", padx=10, pady=(0, 8))

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
                                     text_color="#D97757", width=24, anchor="e")
    w["top_n_value"].grid(row=0, column=2, padx=(6, 0))

    w["top_n_slider"] = ctk.CTkSlider(
        topn_row, from_=5, to=15, number_of_steps=10,
        progress_color="#D97757",
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
