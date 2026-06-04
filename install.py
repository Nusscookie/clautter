"""Installation helper — copies the plugin to DaVinci Resolve's Scripts folder.

Run:  python install.py
"""

from __future__ import annotations
import os
import shutil
import sys
from pathlib import Path

_PLUGIN_DIR = Path(__file__).resolve().parent
_PLUGIN_NAME = "Clutter"

# Target directories per platform
_TARGETS = {
    "win32": Path(os.environ.get("APPDATA", "~")) / "Blackmagic Design" / "DaVinci Resolve"
             / "Support" / "Fusion" / "Scripts" / "Utility",
    "darwin": Path.home() / "Library" / "Application Support" / "Blackmagic Design"
              / "DaVinci Resolve" / "Fusion" / "Scripts" / "Utility",
    "linux": Path.home() / ".local" / "share" / "DaVinciResolve" / "Fusion" / "Scripts" / "Utility",
}


def main() -> None:
    platform = sys.platform
    if platform not in _TARGETS:
        print(f"Unsupported platform: {platform}")
        sys.exit(1)

    target_dir = _TARGETS[platform].expanduser()
    dest = target_dir / _PLUGIN_NAME

    print(f"Source:      {_PLUGIN_DIR}")
    print(f"Destination: {dest}")
    print()

    answer = input("Install/update plugin? [y/N] ").strip().lower()
    if answer != "y":
        print("Aborted.")
        return

    target_dir.mkdir(parents=True, exist_ok=True)

    action = "Updating" if dest.exists() else "Installing"
    print(f"{action}: {dest}")

    shutil.copytree(
        str(_PLUGIN_DIR),
        str(dest),
        ignore=shutil.ignore_patterns(
            ".git", ".claude", "__pycache__", "*.pyc",
            "install.py", "INSTALL.md", "README.md",
        ),
        dirs_exist_ok=True,
    )
    print(f"\nInstalled to: {dest}")
    print()
    print("Next steps:")
    print("  1. Install Python 3.12 dependencies (Python 3.13+ will segfault):")
    print(f"     py -3.12 -m pip install -r \"{dest / 'requirements.txt'}\"")
    print("  2. Install ffmpeg and add to PATH:")
    print("     https://ffmpeg.org/download.html")
    print("  3. Open DaVinci Resolve")
    print("  4. Go to: Workspace > Scripts > Utility > Clutter > main")
    print()
    print("Done!")


if __name__ == "__main__":
    main()
