"""One-time data directory migration: ~/.clutter → ~/.clautter."""

from __future__ import annotations


def migrate_data_dir() -> None:
    from pathlib import Path
    old = Path.home() / ".clutter"
    new = Path.home() / ".clautter"
    if old.exists() and not new.exists():
        import shutil
        shutil.copytree(str(old), str(new))
        print("[Clautter] Migrated ~/.clutter → ~/.clautter (old folder kept for safety)")
