"""UI builder for the Music & SFX tab.

Extracted from music_tab.py so the tab file stays under 200 lines.
Follows the same pattern as _zooms_build.py / _broll_build.py.
"""

from __future__ import annotations

from src.constants import COLORS
from typing import Any

import customtkinter as ctk


def build(parent: Any) -> None:
    w: dict[str, Any] = {}

    ctk.CTkLabel(
        parent,
        text="MUSIC & SFX  —  Add mood-matched music and auto-placed sound effects",
        font=ctk.CTkFont(size=11, weight="bold"),
        text_color=COLORS.TEXT_MUTED,
        anchor="w",
    ).pack(fill="x", padx=12, pady=(12, 6))

    # ══════════════════════════════════════════════════════════════
    #  BACKGROUND MUSIC CARD
    # ══════════════════════════════════════════════════════════════
    music_card = ctk.CTkFrame(parent, fg_color=COLORS.BG_CARD, corner_radius=6)
    music_card.pack(fill="x", padx=10, pady=(0, 6))

    ctk.CTkLabel(music_card, text="BACKGROUND MUSIC",
                 font=ctk.CTkFont(size=10, weight="bold"),
                 text_color=COLORS.TEXT_DIM).pack(anchor="w", padx=10, pady=(8, 4))

    # Music mode toggle
    mode_row = ctk.CTkFrame(music_card, fg_color="transparent")
    mode_row.pack(fill="x", padx=10, pady=2)
    mode_row.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(mode_row, text="Music Mode").grid(row=0, column=0, sticky="w", padx=(0, 12))
    w["music_mode"] = ctk.CTkSegmentedButton(mode_row, values=["Single Track", "Segments"])
    w["music_mode"].set("Single Track")
    w["music_mode"].grid(row=0, column=1, sticky="w")

    # Mood engine toggle
    mood_row = ctk.CTkFrame(music_card, fg_color="transparent")
    mood_row.pack(fill="x", padx=10, pady=2)
    mood_row.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(mood_row, text="Mood Engine").grid(row=0, column=0, sticky="w", padx=(0, 12))
    w["mood_mode"] = ctk.CTkSegmentedButton(mood_row, values=["Keywords", "LLM"])
    w["mood_mode"].set("Keywords")
    w["mood_mode"].grid(row=0, column=1, sticky="w")

    # LLM provider picker (hidden until Mood Engine = "LLM"). Values set in setup().
    w["mood_llm_row"] = ctk.CTkFrame(music_card, fg_color="transparent")
    llm_row = w["mood_llm_row"]
    llm_row.grid_columnconfigure(2, weight=1)
    ctk.CTkLabel(llm_row, text="LLM Provider").grid(row=0, column=0, sticky="w", padx=(0, 12))
    w["mood_llm_provider"] = ctk.CTkOptionMenu(
        llm_row, values=["—"], width=160,
        fg_color=COLORS.BG_MID, button_color=COLORS.BG_MID, button_hover_color=COLORS.BG_HOVER,
    )
    w["mood_llm_provider"].grid(row=0, column=1, sticky="w")
    w["mood_llm_hint"] = ctk.CTkLabel(
        llm_row, text="", font=ctk.CTkFont(size=10), text_color=COLORS.TEXT_DIM, anchor="w",
    )
    w["mood_llm_hint"].grid(row=0, column=2, sticky="w", padx=(10, 0))

    # Sections slider (hidden until "Segments" mode selected)
    w["n_sections_frame"] = ctk.CTkFrame(music_card, fg_color="transparent")
    sec_row = w["n_sections_frame"]
    sec_row.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(sec_row, text="Sections").grid(row=0, column=0, sticky="w", padx=(0, 12))
    w["n_sections_slider"] = ctk.CTkSlider(sec_row, from_=1, to=5, number_of_steps=4)
    w["n_sections_slider"].set(3)
    w["n_sections_slider"].grid(row=0, column=1, sticky="ew", padx=(0, 8))
    w["n_sections_lbl"] = ctk.CTkLabel(sec_row, text="3", text_color=COLORS.BRAND_PRIMARY, width=28)
    w["n_sections_lbl"].grid(row=0, column=2)

    # Music source toggle
    source_row = ctk.CTkFrame(music_card, fg_color="transparent")
    source_row.pack(fill="x", padx=10, pady=2)
    source_row.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(source_row, text="Music Source").grid(row=0, column=0, sticky="w", padx=(0, 12))
    w["music_source"] = ctk.CTkSegmentedButton(source_row, values=["Jamendo", "Local", "Both"])
    w["music_source"].set("Jamendo")
    w["music_source"].grid(row=0, column=1, sticky="w")

    # Local music folder row (shown only when source = Local or Both)
    w["local_music_row"] = local_music_row = ctk.CTkFrame(music_card, fg_color="transparent")
    local_music_row.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(local_music_row, text="Local Music Folder").grid(row=0, column=0, sticky="w", padx=(0, 12))
    w["local_music_entry"] = ctk.CTkEntry(local_music_row, state="readonly",
                                           placeholder_text="Folder with .mp3 / .wav tracks")
    w["local_music_entry"].grid(row=0, column=1, sticky="ew", padx=(0, 6))
    w["local_music_btn"] = ctk.CTkButton(local_music_row, text="Browse", width=70,
                                          fg_color=COLORS.BG_MID, hover_color=COLORS.BG_CARD)
    w["local_music_btn"].grid(row=0, column=2)

    # Download folder row
    w["dl_row"] = dl_row = ctk.CTkFrame(music_card, fg_color="transparent")
    dl_row.pack(fill="x", padx=10, pady=2)
    dl_row.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(dl_row, text="Download To").grid(row=0, column=0, sticky="w", padx=(0, 12))
    w["dl_folder_entry"] = ctk.CTkEntry(dl_row, state="readonly")
    w["dl_folder_entry"].grid(row=0, column=1, sticky="ew", padx=(0, 6))
    w["dl_folder_btn"] = ctk.CTkButton(dl_row, text="Browse", width=70,
                                        fg_color=COLORS.BG_MID, hover_color=COLORS.BG_CARD)
    w["dl_folder_btn"].grid(row=0, column=2)

    # Volume slider
    vol_row = ctk.CTkFrame(music_card, fg_color="transparent")
    vol_row.pack(fill="x", padx=10, pady=(2, 0))
    vol_row.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(vol_row, text="Music Level").grid(row=0, column=0, sticky="w", padx=(0, 12))
    w["music_vol_slider"] = ctk.CTkSlider(vol_row, from_=10, to=100, number_of_steps=90)
    w["music_vol_slider"].set(35)
    w["music_vol_slider"].grid(row=0, column=1, sticky="ew", padx=(0, 8))
    w["music_vol_lbl"] = ctk.CTkLabel(vol_row, text="35%", text_color=COLORS.BRAND_PRIMARY, width=44)
    w["music_vol_lbl"].grid(row=0, column=2)
    ctk.CTkLabel(music_card, text="% of main track level — music is matched to dialogue then offset",
                 font=ctk.CTkFont(size=10), text_color=COLORS.TEXT_MUTED, anchor="w").pack(
        fill="x", padx=10, pady=(0, 2))

    # Run Music button
    w["run_music_btn"] = ctk.CTkButton(
        music_card,
        text="▶  Add Background Music",
        fg_color=COLORS.BTN_PRIMARY_BG,
        hover_color=COLORS.BTN_PRIMARY_HOVER,
        height=32,
    )
    w["run_music_btn"].pack(fill="x", padx=10, pady=(8, 4))

    # Music progress bar (hidden until running)
    w["music_progress_frame"] = ctk.CTkFrame(music_card, height=6, fg_color="transparent")
    w["music_progress_frame"].pack(fill="x", padx=10, pady=0)
    w["music_progress"] = ctk.CTkProgressBar(music_card, height=6)
    w["music_progress"].set(0)

    w["status"] = ctk.CTkLabel(
        music_card,
        text="Requires transcript. Jamendo Client ID (⚙ Settings) needed unless using Local source.",
        font=ctk.CTkFont(size=11),
        text_color=COLORS.TEXT_MUTED,
        anchor="w",
        wraplength=820,
    )
    w["status"].pack(fill="x", padx=10, pady=(2, 10))

    # ══════════════════════════════════════════════════════════════
    #  SOUND EFFECTS CARD
    # ══════════════════════════════════════════════════════════════
    sfx_card = ctk.CTkFrame(parent, fg_color=COLORS.BG_CARD, corner_radius=6)
    sfx_card.pack(fill="x", padx=10, pady=(0, 6))

    ctk.CTkLabel(sfx_card, text="SOUND EFFECTS",
                 font=ctk.CTkFont(size=10, weight="bold"),
                 text_color=COLORS.TEXT_DIM).pack(anchor="w", padx=10, pady=(8, 4))

    ctk.CTkLabel(
        sfx_card,
        text="Places SFX clips at cut/zoom/B-roll events on a dedicated 'SFX' audio track.",
        font=ctk.CTkFont(size=10),
        text_color=COLORS.TEXT_DIM,
        anchor="w",
    ).pack(fill="x", padx=10, pady=(0, 6))

    # SFX source toggle
    sfx_source_row = ctk.CTkFrame(sfx_card, fg_color="transparent")
    sfx_source_row.pack(fill="x", padx=10, pady=2)
    sfx_source_row.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(sfx_source_row, text="SFX Source").grid(row=0, column=0, sticky="w", padx=(0, 12))
    w["sfx_source"] = ctk.CTkSegmentedButton(sfx_source_row, values=["Freesound", "Local", "Both"])
    w["sfx_source"].set("Freesound")
    w["sfx_source"].grid(row=0, column=1, sticky="w")

    # SFX term mode toggle
    sfx_mode_row = ctk.CTkFrame(sfx_card, fg_color="transparent")
    sfx_mode_row.pack(fill="x", padx=10, pady=2)
    sfx_mode_row.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(sfx_mode_row, text="Term Selection").grid(row=0, column=0, sticky="w", padx=(0, 12))
    w["sfx_mood_mode"] = ctk.CTkSegmentedButton(sfx_mode_row, values=["Hardcoded", "LLM"])
    w["sfx_mood_mode"].set("Hardcoded")
    w["sfx_mood_mode"].grid(row=0, column=1, sticky="w")

    # SFX LLM provider row (hidden until Term Selection = "LLM")
    w["sfx_llm_row"] = ctk.CTkFrame(sfx_card, fg_color="transparent")
    sfx_llm_row = w["sfx_llm_row"]
    sfx_llm_row.grid_columnconfigure(2, weight=1)
    ctk.CTkLabel(sfx_llm_row, text="LLM Provider").grid(row=0, column=0, sticky="w", padx=(0, 12))
    w["sfx_llm_provider"] = ctk.CTkOptionMenu(
        sfx_llm_row, values=["—"], width=160,
        fg_color=COLORS.BG_MID, button_color=COLORS.BG_MID, button_hover_color=COLORS.BG_HOVER,
    )
    w["sfx_llm_provider"].grid(row=0, column=1, sticky="w")
    w["sfx_llm_hint"] = ctk.CTkLabel(
        sfx_llm_row, text="", font=ctk.CTkFont(size=10), text_color=COLORS.TEXT_DIM, anchor="w",
    )
    w["sfx_llm_hint"].grid(row=0, column=2, sticky="w", padx=(10, 0))

    # Trigger checkboxes
    trigger_row = ctk.CTkFrame(sfx_card, fg_color="transparent")
    trigger_row.pack(fill="x", padx=10, pady=2)
    w["use_cuts_var"]  = ctk.IntVar(value=1)
    w["use_zooms_var"] = ctk.IntVar(value=1)
    w["use_broll_var"] = ctk.IntVar(value=1)
    ctk.CTkCheckBox(trigger_row, text="SmartCuts Cuts",    variable=w["use_cuts_var"]).pack(
        side="left", padx=(0, 14))
    ctk.CTkCheckBox(trigger_row, text="AutoZoom Events",   variable=w["use_zooms_var"]).pack(
        side="left", padx=(0, 14))
    ctk.CTkCheckBox(trigger_row, text="B-Roll Entries",    variable=w["use_broll_var"]).pack(
        side="left")

    # Optional local SFX folder (shown only when source includes Local)
    w["sfx_folder_row"] = sfx_folder_row = ctk.CTkFrame(sfx_card, fg_color="transparent")
    sfx_folder_row.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(sfx_folder_row, text="Local SFX Folder").grid(
        row=0, column=0, sticky="w", padx=(0, 12))
    w["sfx_folder_entry"] = ctk.CTkEntry(sfx_folder_row, state="readonly",
                                          placeholder_text="Folder with .mp3 / .wav SFX clips")
    w["sfx_folder_entry"].grid(row=0, column=1, sticky="ew", padx=(0, 6))
    w["sfx_folder_btn"] = ctk.CTkButton(sfx_folder_row, text="Browse", width=70,
                                         fg_color=COLORS.BG_MID, hover_color=COLORS.BG_CARD)
    w["sfx_folder_btn"].grid(row=0, column=2)

    # Run SFX button
    w["run_sfx_btn"] = ctk.CTkButton(
        sfx_card,
        text="▶  Auto-Place Sound Effects",
        fg_color=COLORS.BTN_PRIMARY_BG,
        hover_color=COLORS.BTN_PRIMARY_HOVER,
        height=32,
    )
    w["run_sfx_btn"].pack(fill="x", padx=10, pady=(8, 4))

    # SFX progress bar (hidden until running)
    w["sfx_progress_frame"] = ctk.CTkFrame(sfx_card, height=6, fg_color="transparent")
    w["sfx_progress_frame"].pack(fill="x", padx=10, pady=0)
    w["sfx_progress"] = ctk.CTkProgressBar(sfx_card, height=6)
    w["sfx_progress"].set(0)

    w["sfx_status"] = ctk.CTkLabel(
        sfx_card,
        text="Requires Freesound API key (⚙ Settings). Run SmartCuts, Auto Zooms, or B-Roll first.",
        font=ctk.CTkFont(size=11),
        text_color=COLORS.TEXT_MUTED,
        anchor="w",
        wraplength=820,
    )
    w["sfx_status"].pack(fill="x", padx=10, pady=(2, 10))

    parent._w = w
