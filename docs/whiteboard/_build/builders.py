"""Per-feature scene builders for the Clutter whiteboard.

Each function receives a gen.Builder and lays out a high-level flow on the
vertical spine, branch nodes to the right, and a legend panel of the real
thresholds/constants. Box labels carry `file:line` back-references so a reader
can jump from the diagram into the code.

Constants here are mirrored from the source (cited inline). If the code
changes, update both — the legend is the contract.
"""

from __future__ import annotations

from typing import Callable

from gen import Builder


# ── Smart Cuts ────────────────────────────────────────────────────────────────
def smartcuts(b: Builder) -> None:
    b.title("Smart Cuts — silence removal + retake detection")
    s = b.step("terminal", "Timeline clips\n(video track 1)", prev=None)
    s = b.step("process",
               "Per-clip: extract source range\ncutter_segments.py:73", prev=s)
    dec = b.step("decision", "silence_method\n== 'vad' ?\ncutter_segments.py:93", prev=s)
    vad = b.branch("io", "Silero VAD\nspeech_ts → invert to gaps\nanalyzer.py:120",
                   from_id=dec, label="vad", dx=380)
    rms = b.branch("process", "pydub RMS detect_silence\nnormalize → threshold\nanalyzer.py:32",
                   from_id=dec, label="rms / VAD fails", dx=-360)
    inv = b.step("process",
                 "Apply padding · invert silence\n→ keep-segments\ncutter_segments.py:17", prev=dec)
    b.arrow(vad, inv)
    b.arrow(rms, inv)
    rt = b.step("decision", "detect_retakes ?\ncutter.py:46", prev=inv)
    rdet = b.branch("io",
                    "Whisper 'base' transcribe\nslide 4-word window\nretake_detector.py:41",
                    from_id=rt, label="yes", dx=380)
    bld = b.step("process",
                 "Build new timeline\n(silence dropped)\ncutter.py:120", prev=rt,
                 label="no")
    b.arrow(rdet, bld, "tag retakes")
    trk = b.branch("process", "Retake track (V2)\nblack gap on V1\ncutter_retakes.py:121",
                   from_id=bld, label="if retakes", dx=380)
    end = b.step("terminal", "CutResult\nsegments · time_saved\ncutter.py:174", prev=bld)
    b.arrow(trk, end)
    b.legend("Thresholds (defaults)", [
        "threshold_db   = -35 dBFS    (RMS floor)",
        "min_silence    = 350 ms",
        "padding        = 120 ms      (cut-edge breath)",
        "vad_threshold  = 0.5         (Silero speech prob)",
        "seek_step      = 10 ms       (RMS resolution)",
        "min_segment    = 10 ms       (drop micro-clips)",
        "",
        "Retake detection:",
        "WIN_WORDS      = 4 words     (slide window)",
        "SIMILARITY     = 0.70        (SequenceMatcher)",
        "PROXIMITY      = 120 s       (search window)",
        "FULL_RETAKE    = 0.90        (coverage → full)",
        "whisper model  = 'base'",
        "VAD → RMS automatic fallback on failure.",
    ])


# ── Auto Zooms ────────────────────────────────────────────────────────────────
def zooms(b: Builder) -> None:
    b.title("Auto Zooms — cut-point driven punch-ins")
    s = b.step("terminal", "Timeline clips\n+ cut points", prev=None)
    d1 = b.step("decision", "take length\n≥ min_take ?\nanalyzer.py:104", prev=s)
    skip = b.branch("exit", "skip clip\n(too short)", from_id=d1, label="no", dx=380)
    pt = b.step("process", "1 zoom point at take start\nanalyzer.py:97", prev=d1,
                label="yes")
    sp = b.step("decision", "spacing ok ?\nmax_per_minute\nanalyzer.py:42", prev=pt)
    drop = b.branch("exit", "drop point\n(too close)", from_id=sp, label="no", dx=380)
    seg = b.step("process", "Segment clips at\nzoom boundaries\napplier_props.py:16",
                 prev=sp, label="yes")
    fade = b.step("decision", "fade (animate) ?\napplier.py:333", prev=seg)
    fus = b.branch("io",
                   "Fusion Transform keyframes\nSize ramp over EASE\napplier.py:132",
                   from_id=fade, label="yes", dx=380)
    stat = b.branch("process", "Static ZoomX/Y\n+ DynamicZoomEase\napplier.py:211",
                    from_id=fade, label="no", dx=-360)
    safe = b.step("process", "safe-zoom cap\ncover pan/tilt ≤ ZOOM_MAX\napplier.py:39",
                  prev=fade)
    b.arrow(fus, safe)
    b.arrow(stat, safe)
    end = b.step("terminal", "ZoomResult\nzooms_applied", prev=safe)
    b.legend("Thresholds (defaults)", [
        "min_take       = 2.0 s    (skip shorter)",
        "max_per_minute = 4        (cadence cap)",
        "zoom_amount    = 1.15     (115% punch)",
        "zoom_duration  = 2500 ms",
        "EASE_SECONDS   = 0.4 s    (ramp in/out)",
        "ZOOM_MAX       = 1.6      (hard cap)",
        "DynamicZoomEase= 3        (in/out)",
        "",
        "spacing = (60 / max_per_minute) * fps",
        "Static path falls back to Fusion-static",
        "if SetProperty no-ops (Resolve free).",
    ])


# ── Autonomous B-Roll ─────────────────────────────────────────────────────────
def broll(b: Builder) -> None:
    b.title("Autonomous B-Roll — keyword → fetch → rank → place")
    g = b.step("decision", "transcript exists ?\nautonomous.py:295", prev=None)
    gx = b.branch("exit", "warn + return\n(no transcript)", from_id=g, label="no", dx=380)
    kw = b.step("decision", "LLM director\n+ providers ?\nautonomous.py:308", prev=g,
                label="yes")
    llmkw = b.branch("io", "LLM search terms\nllm_director.generate_search_terms",
                     from_id=kw, label="yes", dx=380)
    heur = b.step("process",
                  "extract_top_keywords\nspaCy / yake / keybert / freq\nkeywords.py",
                  prev=kw, label="no / LLM fails")
    b.arrow(llmkw, heur, "fallback")
    seg = b.step("process", "Build transcript segments\nmatcher._build_segments", prev=heur)
    col = b.step("process",
                 "Collect candidates\nlocal scan + online search\nautonomous.py:339", prev=seg)
    on = b.branch("io", "Pexels / Pixabay\nper_page 3, dl top-1\nautonomous.py:87",
                  from_id=col, label="online", dx=380)
    mode = b.step("decision", "llm_director_mode ?\nautonomous.py:362", prev=col)
    # LLM director path (left)
    ld = b.branch("io", "LLM plans every placement\nllm_director.direct\nautonomous.py:364",
                  from_id=mode, label="yes", dx=-380, w=300)
    # Semantic path (down)
    rank = b.step("process",
                  "Semantic rank (S-BERT)\n→ word-overlap fallback\nautonomous.py:483",
                  prev=mode, label="no")
    gate = b.step("decision",
                  "pacing gate\nintro_skip · min_gap · MIN_FACE\nautonomous.py:234",
                  prev=rank)
    gx2 = b.branch("exit", "skip segment\n(too early / too close)",
                   from_id=gate, label="reject", dx=380)
    place = b.step("process",
                   "scene-align in-point\n→ place on B-Roll track\nautonomous.py:544",
                   prev=gate, label="pass")
    b.arrow(ld, place, "decisions")
    end = b.step("terminal", "AutonomousResult\nplaced · skipped", prev=place)
    b.legend("Thresholds (defaults)", [
        "top_n keywords = 10",
        "max_clips      = 10      (online cap)",
        "per_page       = 3       (dl top-1 each)",
        "MIN_FACE       = 1.0 s   (merge if closer)",
        "intro_skip     = 8.0 s   (no B-roll in intro)",
        "min_gap        = 5.0 s   (face-time between)",
        "max_broll      = 5.0 s   (clip duration cap)",
        "",
        "Optional re-rank: OpenCLIP ViT-B-32",
        "  (top 10 candidates, if torch present)",
        "Cloud LLM re-rank when cloud_rerank=on.",
        "Scene align via scenedetect ContentDetector.",
        "Two modes: LLM-director vs semantic-rank.",
    ])


# ── Subtitles ─────────────────────────────────────────────────────────────────
def subtitles(b: Builder) -> None:
    b.title("Subtitles — STT → format → remap → Fusion titles")
    s = b.step("process", "Extract timeline audio\n(cut audio if available)\n_subtitles_generate.py:52",
               prev=None)
    prov = b.step("decision", "provider ?\n_subtitles_generate.py:68", prev=s)
    el = b.branch("io", "ElevenLabs scribe_v1\nPOST /speech-to-text\nelevenlabs.py:114",
                  from_id=prov, label="ElevenLabs", dx=380)
    wh = b.branch("io", "faster-whisper (int8)\nauto CPU/CUDA\nwhisper_client.py",
                  from_id=prov, label="Local Whisper", dx=-380, w=300)
    fmt = b.step("process",
                 "Format SRT blocks\npreset wpl × lpb\nformatter.py:75", prev=prov)
    b.arrow(el, fmt)
    b.arrow(wh, fmt)
    edit = b.step("process",
                  "User edits transcript\n(token-count match → keep timing)\n_subtitles_workers.py:44",
                  prev=fmt)
    rm = b.step("decision", "words already\nremapped ?\n_subtitles_workers.py:94", prev=edit)
    remap = b.branch("process", "Remap to cut-timeline\nsource→record sec\nremapper.py:11",
                     from_id=rm, label="no", dx=380)
    place = b.step("decision",
                   "Fusion Title template\nfound ?\nfusion_placer.py:66", prev=rm,
                   label="yes / after remap")
    b.arrow(remap, place)
    fus = b.step("process",
                 "Place Text+ clips on\nSubtitle track + style\nfusion_placer.py:102",
                 prev=place, label="yes")
    srt = b.branch("process", "SRT fallback import\nimport_srt_to_timeline\n_subtitles_workers.py:117",
                   from_id=place, label="no", dx=380)
    end = b.step("terminal", "Subtitle track on timeline", prev=fus)
    b.arrow(srt, end)
    b.legend("Thresholds / presets", [
        "ElevenLabs model = scribe_v1",
        "  max file = 100 MB · timeout = 300 s",
        "Whisper compute  = int8 · device = auto",
        "micro-segment    = 10 ms",
        "",
        "Presets (words/line, lines/block, caps):",
        "  Standard  8 / 2 / no",
        "  YouTube   7 / 2 / no",
        "  TikTok    5 / 1 / UPPER",
        "  Hormozi   3 / 1 / UPPER  (word-by-word)",
        "",
        "Edit fallback: word-count change →",
        "  proportional timing (approx).",
    ])


# ── Pace Control ──────────────────────────────────────────────────────────────
def pace(b: Builder) -> None:
    b.title("Pace Control — slider → preset → Smart Cuts")
    s = b.step("terminal", "Slider 1–10\n(default 5 = YouTube)", prev=None)
    upd = b.step("process",
                 "Live preview update\nthreshold · ms · WPM · retention\npace_tab.py:25",
                 prev=s)
    ap = b.step("decision", "Apply Pace\nconnected ?\npace_tab.py:39", prev=upd)
    nx = b.branch("exit", "error\n(not connected)", from_id=ap, label="no", dx=380)
    dlg = b.step("process", "Timeline dialog\nnew vs append\ntimeline_dialog.py", prev=ap,
                 label="yes")
    look = b.step("process",
                  "Preset lookup\np = pace_presets[level]\n_pace_workers.py:29", prev=dlg)
    call = b.step("io",
                  "apply_cuts(threshold_db,\nmin_silence, padding=120)\ncutter.py:37",
                  prev=look)
    end = b.step("terminal", "New '..._cuts' timeline\ntime_saved logged", prev=call)
    b.legend("Pace presets (level → params)", [
        " L  label       dB    silence  WPM  keep%",
        " 1  VerySlow   -55   1500ms   100   62",
        " 2  Slow       -50   1200ms   115   65",
        " 3  Relaxed    -45    900ms   125   68",
        " 4  Moderate   -40    600ms   135   72",
        " 5  YouTube★   -35    350ms   145   77",
        " 6  Crisp      -33    280ms   155   80",
        " 7  Snappy     -30    220ms   165   83",
        " 8  Fast       -28    160ms   175   85",
        " 9  VeryFast   -25    120ms   185   87",
        "10  TikTok     -22     80ms   200   89",
        "",
        "padding = 120 ms (constant) · default L5",
        "Delegates entirely to Smart Cuts engine.",
    ])


# ── Music & SFX ───────────────────────────────────────────────────────────────
def music(b: Builder) -> None:
    b.title("Music & SFX — mood music + auto SFX with ducking")
    s = b.step("terminal", "Transcript + keywords\n(shared app state)", prev=None)
    mood = b.step("process",
                  "Mood analysis\nkeyword → mood bucket\nmood_analyzer.py:36", prev=s)
    fetch = b.step("io",
                   "Fetch music (Pixabay)\nsearch = MOOD_BUCKETS[mood]\naudio_provider.py",
                   prev=mood)
    proc = b.step("process",
                  "Bake volume + fades\ngain_db = 10·log10(vol%/100)\naudio_processor.py:44",
                  prev=fetch)
    pm = b.step("process", "Place on 'Music' track\nplacer.place_audio_clip", prev=proc)
    # SFX branch
    sfx = b.branch("process",
                   "Collect SFX events\ncuts · zooms · b-roll\nsfx_engine.py:44",
                   from_id=pm, label="SFX pipeline", dx=380, w=300)
    dedup = b.branch("decision", "event gap\n≥ MIN_GAP ?\nsfx_engine.py:118",
                     from_id=sfx, at_y=None, dx=380)
    sfxdl = b.branch("io", "Map event → term\ndl Pixabay SFX\nsfx_engine.py:156",
                     from_id=dedup, label="yes", dx=380, w=300)
    gain = b.branch("process", "Apply -10 dB gain\nplace on 'SFX' track\naudio_processor.py:17",
                    from_id=sfxdl, dx=380, w=300)
    end = b.step("terminal", "Music + SFX tracks placed", prev=pm)
    b.legend("Thresholds / mappings", [
        "DEFAULT_MOOD   = 'upbeat'",
        "MOOD_BUCKETS   = energetic / calm /",
        "  emotional / corporate / dramatic / upbeat",
        "KEYWORD_MOOD_MAP: ~80 stems → bucket",
        "",
        "Music volume bake:",
        "  gain_db = 10·log10(vol% / 100)",
        "  e.g. 35% → -4.56 dB",
        "  fades clamped to clip_len // 3",
        "",
        "SFX_GAIN_DB      = -10.0 dB (fixed)",
        "MIN_EVENT_GAP    = 0.5 s (dedup)",
        "SFX_TERM_MAP: event_type → search term",
        "  (no API per-clip volume → baked to file)",
    ])


# ── Motion Graphics (BETA) ────────────────────────────────────────────────────
def graphics(b: Builder) -> None:
    b.title("Motion Graphics (BETA) — rule-based suggester")
    s = b.step("decision", "transcript exists ?\ngraphics_tab.py:113", prev=None)
    gx = b.branch("exit", "error\n(no transcript)", from_id=s, label="no", dx=380)
    sent = b.step("process",
                  "Build sentences\nsplit on .!? or ≥15 words\nsuggester.py:64", prev=s,
                  label="yes")
    rule = b.step("decision",
                  "Test 7 regex rules\nfirst match wins\nsuggester.py:88", prev=sent)
    hit = b.branch("process",
                   "Emit suggestion\n{type, desc, timestamp}\nsuggester.py:93",
                   from_id=rule, label="match", dx=380)
    nomatch = b.branch("exit", "skip sentence\n(no rule hit)", from_id=rule,
                       label="none", dx=-360)
    fmt = b.step("process", "Format + display\n[M:SS] type / desc\ngraphics_tab.py:137",
                 prev=rule)
    b.arrow(hit, fmt)
    end = b.step("terminal", "Suggestions textbox\n(read-only, V1)", prev=fmt)
    b.legend("Rules (regex → graphic, in order)", [
        "1 \\d+(%|k|million)  → Statistic Callout",
        "2 step/first/next…   → Process Diagram",
        "3 \"quote\" 10–80 ch  → Quote Card",
        "4 i'm/welcome to…    → Lower Third",
        "5 \\d+ tips/ways…     → Number Counter",
        "6 before/after/vs…   → Before/After Split",
        "7 link/subscribe…    → CTA Overlay",
        "",
        "max words/sentence = 15",
        "first match wins → 1 suggestion/sentence",
        "BETA: read-only, no Resolve placement yet.",
    ])


# ── System / data-flow overview ───────────────────────────────────────────────
def overview(b: Builder) -> None:
    b.title("System overview — HTTP bridge + cross-feature data flow")
    r = b.step("terminal", "DaVinci Resolve\n(Scripts ▸ Utility)", prev=None)
    m = b.step("io", "main.py (Resolve-side)\nacquires resolve, no UI\nmain.py", prev=r)
    srv = b.step("process",
                 "rpc_server (daemon thread)\nhttp://127.0.0.1:<rand>\nrpc_server.py", prev=m)
    bj = b.branch("io", "~/.clutter/bridge.json\n(port handshake)",
                  from_id=srv, label="writes", dx=380)
    gui = b.step("process", "subprocess: gui.py\nCTk window\ngui.py", prev=srv,
                 label="spawns + proc.wait()")
    cli = b.step("process",
                 "rpc_client.ResolveProxy\nresolve_api.connect()\nrpc_client.py", prev=gui)
    app = b.step("process", "app.py (AIEditorApp)\nresolve · project · transcript\napp.py",
                 prev=cli)
    tabs = b.step("process", "Feature tabs\nbuild() + setup()\nui/*_tab.py", prev=app)
    # cross-feature data-flow cluster (right side)
    tx = b.branch("io", "transcript\n(Subtitles tab)", from_id=tabs, at_y=180,
                  label="produces", dx=420, w=240, h=70)
    b.branch("process", "→ B-Roll  (keywords)", from_id=tx, at_y=180, dx=720, w=240, h=60)
    b.branch("process", "→ Graphics (rules)", from_id=tx, at_y=270, dx=720, w=240, h=60)
    b.branch("process", "→ Music (mood)", from_id=tx, at_y=360, dx=720, w=240, h=60)
    cuts = b.branch("io", "cut segments\n(Smart Cuts / Pace)", from_id=tabs, at_y=480,
                    label="produces", dx=420, w=240, h=70)
    b.branch("process", "→ Subtitle remap", from_id=cuts, at_y=480, dx=720, w=240, h=60)
    b.branch("process", "→ SFX triggers", from_id=cuts, at_y=570, dx=720, w=240, h=60)
    b.legend("Bridge invariants", [
        "Bridge exists because Resolve FREE",
        "disables external scripting:",
        "  scriptapp('Resolve') → None outside Resolve.",
        "",
        "Server runs INSIDE Resolve's process →",
        "  reaches live `resolve` via module globals.",
        "",
        "random localhost port · bridge.json handshake",
        "main.py blocks on proc.wait() → keeps",
        "  daemon thread (and connection) alive.",
        "GUI connect: daemon thread, 5 s timeout →",
        "  UI opens even without Resolve.",
    ], y=160)


BUILDERS: dict[str, Callable[[Builder], None]] = {
    "overview": overview,
    "smartcuts": smartcuts,
    "pace": pace,
    "zooms": zooms,
    "subtitles": subtitles,
    "broll": broll,
    "music": music,
    "graphics": graphics,
}
