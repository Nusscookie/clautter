# Installation Guide — Clutter

## Requirements

| Requirement | Version | Notes |
|---|---|---|
| DaVinci Resolve | 18+ (free or Studio) | Both editions supported |
| Python | **3.10, 3.11, or 3.12** | DaVinci Resolve's `DaVinciResolveScript.pyd` is built against CPython ≤3.12 ABI. Python 3.13+ causes `import DaVinciResolveScript` to segfault. Use the `py` launcher to pin the version. |
| ffmpeg | Any recent | Required by pydub for audio decoding |

---

## Step 1 — Install Python Dependencies

**Important:** Clutter spawns its GUI in a separate Python process. The version **must** be 3.10–3.12 because DaVinci Resolve's compiled scripting module segfaults on newer interpreters. Pin the version with the `py` launcher.

Open a terminal/command prompt and run:

```bash
py -3.12 -m pip install -r requirements.txt
```

This installs:
- `customtkinter` — the GUI toolkit (only used by the spawned GUI process)
- `pydub` — audio analysis for Smart Cuts
- `requests` — ElevenLabs API for Subtitles
- `numpy` — RMS computation for Auto Zooms

---

## Step 2 — Install ffmpeg

ffmpeg is required by pydub to decode audio from video files.

**Windows:**
1. Download from https://ffmpeg.org/download.html (BtbN or gyan.dev builds)
2. Extract to `C:\ffmpeg\`
3. Add `C:\ffmpeg\bin` to your system PATH
4. Verify: open a new terminal and run `ffmpeg -version`

**macOS:**
```bash
brew install ffmpeg
```

**Linux:**
```bash
sudo apt install ffmpeg   # Debian/Ubuntu
sudo dnf install ffmpeg   # Fedora
```

---

## Step 3 — Copy Plugin to DaVinci Resolve Scripts Folder

### Option A — Automatic (recommended)

```bash
python install.py
```

### Option B — Manual

1. Copy the entire `clutter/` project folder to the app-data directory:

   | Platform | Path |
   |---|---|
   | **Windows** | `%LOCALAPPDATA%\Clutter\` |
   | **macOS** | `~/Library/Application Support/Clutter/` |
   | **Linux** | `~/.local/share/Clutter/` |

2. Create a stub file at the Scripts/Utility folder. Replace `<APP_DIR>` with the path from step 1:

   | Platform | Stub path |
   |---|---|
   | **Windows** | `%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility\Clutter.py` |
   | **macOS** | `~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility/Clutter.py` |
   | **Linux** | `~/.local/share/DaVinciResolve/Fusion/Scripts/Utility/Clutter.py` |

   ```python
   import sys
   from pathlib import Path

   _APP_DIR = Path("<APP_DIR>")
   if str(_APP_DIR) not in sys.path:
       sys.path.insert(0, str(_APP_DIR))

   import main as _clutter_main

   _resolve_obj = globals().get("resolve")
   if _resolve_obj is not None:
       _clutter_main.resolve = _resolve_obj

   _clutter_main.main()
   ```

---

## Step 4 — Launch the Plugin

1. Open DaVinci Resolve
2. Click **Workspace → Scripts → Utility → Clutter**

The plugin window opens.

---

## Step 5 — Enter ElevenLabs API Key (for Subtitles)

1. Go to https://elevenlabs.io and create a free account
2. Copy your API key from the profile menu
3. In the plugin's **Subtitles** tab, paste the key and click **Save**

The key is stored locally at `~/.clutter/config.json`.

---

## Troubleshooting

### "Cannot connect to DaVinci Resolve"
- Make sure DaVinci Resolve is running before launching the script
- Run the script from the Workspace > Scripts menu (not as a standalone Python script)

### "pydub is not installed" / "ffmpeg not found"
- Run `pip install pydub` in the Python environment that DaVinci Resolve uses
- DaVinci Resolve may use its own embedded Python; check which Python is active:
  ```bash
  # In DaVinci Resolve's Script Console (Workspace > Console):
  import sys; print(sys.executable)
  ```
  Then use that Python to install dependencies.

### "ElevenLabs API error (HTTP 401)"
- Your API key is invalid or expired
- Log in at elevenlabs.io and generate a new key

### Subtitle track not appearing in timeline
- The SRT file is saved to a temp directory (path shown in the status bar)
- Manually drag the SRT file from the Media Pool onto the subtitle track
- Or use File > Import > Subtitles in DaVinci Resolve

### Smart Cuts creates empty timeline
- Check that the media files are accessible (not offline)
- Verify ffmpeg is installed: `ffmpeg -version` in terminal
- Lower the silence threshold (e.g., from -35 to -45 dB) and retry

---

## Settings File

Settings are stored at: `~/.clutter/config.json`

To reset to defaults, delete this file and restart the plugin.
