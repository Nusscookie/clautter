Build a professional DaVinci Resolve Studio plugin called "Clutter".

Goal:
Create a production-ready DaVinci Resolve plugin that helps creators edit talking-head videos faster through silence cutting, subtitle generation, intelligent zooms, and automatic B-roll suggestions.

Tech Requirements:

* Language: Python
* DaVinci Resolve Scripting API
* Modern UI using Resolve's UI Manager
* Modular architecture
* Each major feature in its own tab
* Settings saved locally in JSON
* Undo support whenever possible
* Progress bars for long-running operations
* Error handling for missing API keys, missing tracks, missing media, etc.

====================================================
TAB 1: SMART CUTS
=================

Purpose:
Automatically remove silences from selected clips in the timeline.

Features:

* Analyze audio waveform.
* Detect silent sections.
* Cut and ripple delete silence.
* Operate on selected timeline clips only.
* Non-destructive preview mode.

Controls:

* Silence Threshold (default: -35 dB)
* Minimum Silence Duration (default: 0.35 sec)
* Leave Breathing Room (default: 0.12 sec before and after cuts)
* Analyze Button
* Apply Cuts Button
* Preview Cuts Button

Output:

* Display total silences found.
* Display estimated time saved.
* Highlight cut locations.

====================================================
TAB 2: PACE CONTROL
===================

Purpose:
Control editing intensity.

Provide a single slider:

Value 1:
Very slow pacing
Only remove long pauses.

Value 5:
Standard YouTube pacing.

Value 10:
Fast TikTok/Reels pacing.

The slider automatically adjusts:

* silence threshold
* minimum pause duration
* aggressiveness of cuts

Display:

* Estimated average words per minute after edit.
* Estimated retention score.

====================================================
TAB 3: SUBTITLES
================

Purpose:
Generate subtitles automatically.

Provider:
ElevenLabs Speech-to-Text API

Settings:

* API Key field
* Save API Key locally
* Language selector
* Subtitle style presets

Presets:

* Standard
* YouTube
* TikTok
* Alex Hormozi Style

Functions:

* Generate transcript
* Create subtitle track
* Burn-in subtitles (optional)
* Export SRT
* Export TXT transcript

Transcript panel:

* Editable transcript viewer
* Clicking transcript jumps to timeline position

====================================================
TAB 4: AUTO ZOOMS
=================

Purpose:
Create engaging zoom cuts automatically.

Features:
Analyze:

* speech emphasis
* transcript keywords
* volume peaks
* pauses
* emotional intensity

Detect moments where zooms improve viewer retention.

Controls:

* Enable Auto Zoom
* Fade Zooms
* Hard Cut Zooms
* Zoom Amount slider (105%–130%)
* Max Zooms Per Minute

Modes:

1. Conservative
2. Standard
3. High Energy

Output:

* Suggested zoom markers
* Apply Zooms button

Implementation:
Create keyframes on clip scale and position.

====================================================
TAB 5: B-ROLL ASSISTANT
=======================

Purpose:
Suggest and optionally place B-roll automatically.

Input:
User selects a folder containing B-roll clips.

Process:

1. Scan all clips.
2. Generate metadata.
3. Extract file names.
4. Optionally create embeddings.

Transcript Analysis:
Analyze generated transcript.

Example:
Speaker says:
"Last week I tested three cameras."

Suggestions:
camera footage
camera closeups
testing shots

Features:

* Suggest B-roll
* Auto-place on V2
* Confidence score
* Preview before applying

Controls:

* Scan Folder
* Analyze Transcript
* Suggest B-roll
* Auto Place B-roll

Timeline Rules:

* Never overwrite existing clips.
* Place on V2 by default.
* Respect clip boundaries.

====================================================
TAB 6: MOTION GRAPHICS (OPTIONAL BETA)
======================================

Purpose:
Generate simple motion graphic recommendations.

Version 1:
Suggestions only.

Examples:

* Lower thirds
* Statistic callouts
* Quote cards
* Number counters
* Process diagrams

Future:
Integrate with AI providers:

* Minimax
* Gemini
* OpenAI

Settings:

* API Key
* Graphic Style

Output:

* Suggested graphics list
* Timeline marker recommendations

Do NOT implement full AI-generated graphics in V1.

====================================================
GLOBAL FEATURES
===============

Dashboard:

* Time saved estimate
* Total edits created
* Retention improvement estimate

Background processing:

* Multi-threading where possible

Architecture:
Create modules:

ui/
smartcuts/
pace/
subtitles/
zooms/
broll/
graphics/
settings/
utils/

Code Requirements:

* Clean architecture
* Strong comments
* Type hints
* Logging
* Config file
* Easy future expansion

Create:

1. Full folder structure
2. All source code
3. Installation guide
4. Build instructions
5. Example config file
6. README.md

Start with a working MVP:
Smart Cuts + Subtitles + Auto Zooms.

Then scaffold remaining tabs for future implementation.
