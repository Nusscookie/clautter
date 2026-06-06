"""Rebuild assets/subtitle_template.drb with plain white Open Sans.

Run this from inside DaVinci Resolve (Workspace > Scripts > this file, or
`py -3.12 main.py` then a call to this module). The script:

1. Records the current project so we can restore it.
2. Creates a scratch project called ``Clutter_Template_Builder``.
3. Inserts a stock ``Text+`` title into its timeline, opens the Fusion comp,
   and mutates the tool so the .drb contains exactly the style we want:
   Font = "Open Sans", white, no border, no shadow.
4. Saves the scratch project.
5. Copies the resulting project file to ``assets/subtitle_template.drb``.
6. Deletes the scratch project and switches back to the original.

If anything goes wrong, the original project is reopened untouched. The
script never writes to the user's active project.

Note: the per-clip ``_apply_fusion_text_style`` in ``src/subtitles/generator.py``
already overrides font, color, and outline on every placed clip, so the
bundled .drb's *style* is irrelevant for normal operation. The only reason
to keep a clean .drb around is to give new users something to import when
``InsertFusionTitleIntoTimeline`` is unavailable (Free edition).
"""

from __future__ import annotations

import os
import shutil
from typing import Any


SCRATCH_PROJECT_NAME = "Clutter_Template_Builder"
TARGET_FONT = "Open Sans"
TARGET_SIZE_PT = 36.0        # 36 pt → ~0.10 in Fusion's 0-1 internal scale
TARGET_RED = 1.0             # white
TARGET_GREEN = 1.0
TARGET_BLUE = 1.0
# Outline left at 0 / black so the .drb is the absolute baseline.


def _resolve_connect() -> Any:
    """Return a live DaVinciResolveScript module from inside Resolve.

    Callers must run this where ``DaVinciResolveScript`` is importable
    (i.e. from the Resolve Scripts menu, or via main.py's bridge).
    """
    import DaVinciResolveScript as dvr  # type: ignore
    return dvr.scriptapp("Resolve")


def _find_project_file(resolve: Any, project_name: str) -> str | None:
    """Locate the on-disk .drp file Resolve saved for ``project_name``.

    Resolve does not expose the project file path through scripting, so we
    sniff the default project library. Common locations: Movies/Resolve
    Projects/, Documents/Resolve Projects/, ~/Resolve Projects/.
    """
    candidates = [
        os.path.expanduser("~/Movies/Resolve Projects/"),
        os.path.expanduser("~/Documents/Resolve Projects/"),
        os.path.expanduser("~/Resolve Projects/"),
    ]
    for folder in candidates:
        if not os.path.isdir(folder):
            continue
        for entry in os.listdir(folder):
            if entry.startswith(project_name) and entry.endswith(".drp"):
                return os.path.join(folder, entry)
    return None


def build(target_drb: str) -> bool:
    """Build the .drb in place at ``target_drb``. Returns True on success."""
    resolve = _resolve_connect()
    if not resolve:
        print("[build_template] Could not connect to Resolve.")
        return False

    pm = resolve.GetProjectManager()
    original_name = None
    original = pm.GetCurrentProject()
    if original:
        original_name = original.GetName()

    # ── 1. Create scratch project ──────────────────────────────────────
    scratch = pm.CreateProject(SCRATCH_PROJECT_NAME)
    if not scratch:
        print(f"[build_template] Failed to create {SCRATCH_PROJECT_NAME!r}")
        return False

    try:
        # ── 2. Insert stock Text+ ─────────────────────────────────────
        timeline = scratch.GetMediaPool().CreateEmptyTimeline("TemplateTL")
        if not timeline:
            print("[build_template] CreateEmptyTimeline returned None")
            return False
        clip = timeline.InsertFusionTitleIntoTimeline("Text+")
        if not clip:
            print("[build_template] InsertFusionTitleIntoTimeline failed")
            return False

        # ── 3. Mutate the comp to plain white Open Sans ──────────────
        comp = clip.GetFusionCompByIndex(1)
        if not comp:
            print("[build_template] No Fusion comp on inserted Text+")
            return False
        tool = comp.FindToolByID("TextPlus") or comp.FindTool("Template")
        if not tool:
            print("[build_template] No TextPlus tool in comp")
            return False

        sets = (
            ("Font",   TARGET_FONT),
            ("Size",   TARGET_SIZE_PT / 360.0),
            ("Red1",   TARGET_RED),
            ("Green1", TARGET_GREEN),
            ("Blue1",  TARGET_BLUE),
            ("Bold",     0),
            ("Italic",   0),
            ("Underline", 0),
            ("BorderWidth", 0.0),
            ("BorderRed",   0.0),
            ("BorderGreen", 0.0),
            ("BorderBlue",  0.0),
        )
        for attr, val in sets:
            try:
                tool.SetInput(attr, val)
            except Exception as e:
                print(f"[build_template] SetInput({attr}) failed: {e}")

        # ── 4. Save scratch project ───────────────────────────────────
        if not scratch.SaveProject():
            print("[build_template] SaveProject failed")
            return False

        # ── 5. Find the saved .drp and copy to target .drb ───────────
        drp_path = _find_project_file(resolve, SCRATCH_PROJECT_NAME)
        if not drp_path:
            print(
                "[build_template] Could not locate saved .drp; "
                "Resolve may have stored it outside the default library. "
                "Search manually for Clutter_Template_Builder.drp."
            )
            return False
        os.makedirs(os.path.dirname(target_drb), exist_ok=True)
        shutil.copy2(drp_path, target_drb)
        print(f"[build_template] Wrote {target_drb}")
        return True

    finally:
        # ── 6. Always close scratch + restore original project ───────
        try:
            pm.CloseProject(scratch)
            pm.DeleteProject(SCRATCH_PROJECT_NAME)
        except Exception as e:
            print(f"[build_template] Cleanup warning: {e}")
        if original_name:
            try:
                pm.LoadProject(original_name)
            except Exception:
                pass


if __name__ == "__main__":
    import sys
    target = (
        sys.argv[1]
        if len(sys.argv) > 1
        else os.path.join(os.path.dirname(__file__), "subtitle_template.drb")
    )
    ok = build(target)
    sys.exit(0 if ok else 1)
