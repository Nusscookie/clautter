"""Generator for Clutter's Excalidraw feature flow maps.

Standalone — no project / Resolve deps. Emits one `.excalidraw` scene per
feature into `docs/whiteboard/`, each a high-level flow (process boxes,
decision diamonds, terminal ellipses, io rectangles) plus a side **legend**
panel listing the real thresholds/constants pulled from the source.

Run:  py -3.12 docs/whiteboard/_build/gen.py
Output is deterministic (stable ids/seeds) so re-running yields no git diff.

Schema notes (Excalidraw):
- Every element: id, type, x, y, width, height, angle, strokeColor,
  backgroundColor, fillStyle, strokeWidth, strokeStyle, roughness, opacity,
  groupIds, frameId, roundness, seed, version, versionNonce, isDeleted,
  boundElements, updated, link, locked.
- Text bound to a container: text element has containerId; container lists
  {type:"text", id} in its own boundElements (two-way).
- Arrow binds via startBinding/endBinding {elementId, focus, gap}; both nodes
  list {type:"arrow", id} in boundElements (two-way).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # for `import builders`

# ── Output location ───────────────────────────────────────────────────────────
OUT_DIR = Path(__file__).resolve().parent.parent  # docs/whiteboard/

# ── Palette (brand accents on a light canvas for readability) ─────────────────
PALETTE = {
    "process":  {"stroke": "#1971c2", "bg": "#e7f5ff"},   # accent blue  — steps
    "decision": {"stroke": "#f08c00", "bg": "#fff4e6"},   # warn orange  — branches
    "io":       {"stroke": "#2f9e44", "bg": "#ebfbee"},   # success green— external calls
    "terminal": {"stroke": "#868e96", "bg": "#f1f3f5"},   # grey         — start/end
    "exit":     {"stroke": "#e03131", "bg": "#fff5f5"},   # error red    — guard exits
    "legend":   {"stroke": "#868e96", "bg": "#fff9db"},   # sticky yellow— threshold panel
}
LINE = "#343a40"   # arrows + text

# ── Layout constants ──────────────────────────────────────────────────────────
NODE_W, NODE_H = 280, 80
LANE_X = 120                 # main spine x
BRANCH_DX = 360             # horizontal offset for branch nodes
V_GAP = 130                 # vertical gap between spine nodes
TOP = 120


class _Ids:
    """Deterministic id + seed counter so output diffs are stable."""

    def __init__(self) -> None:
        self.n = 0

    def next(self, prefix: str) -> str:
        self.n += 1
        return f"{prefix}{self.n:04d}"

    def seed(self) -> int:
        self.n += 1
        return 100000 + self.n * 7


class Builder:
    """Accumulates Excalidraw elements for one scene with auto vertical layout."""

    def __init__(self, ids: _Ids) -> None:
        self.ids = ids
        self.elements: list[dict] = []
        self._y = TOP

    # ── element factories ────────────────────────────────────────────────────
    def _base(self, etype: str, x: float, y: float, w: float, h: float,
              stroke: str, bg: str, roundness: dict | None) -> dict:
        eid = self.ids.next("el")
        return {
            "id": eid, "type": etype, "x": x, "y": y, "width": w, "height": h,
            "angle": 0, "strokeColor": stroke, "backgroundColor": bg,
            "fillStyle": "solid", "strokeWidth": 2, "strokeStyle": "solid",
            "roughness": 0, "opacity": 100, "groupIds": [], "frameId": None,
            "roundness": roundness, "seed": self.ids.seed(), "version": 1,
            "versionNonce": self.ids.seed(), "isDeleted": False,
            "boundElements": [], "updated": 1, "link": None, "locked": False,
        }

    def _text(self, container_id: str, text: str, x: float, y: float,
              w: float, h: float, size: int = 16, align: str = "center") -> dict:
        eid = self.ids.next("tx")
        lines = text.count("\n") + 1
        return {
            "id": eid, "type": "text", "x": x, "y": y, "width": w, "height": h,
            "angle": 0, "strokeColor": LINE, "backgroundColor": "transparent",
            "fillStyle": "solid", "strokeWidth": 2, "strokeStyle": "solid",
            "roughness": 0, "opacity": 100, "groupIds": [], "frameId": None,
            "roundness": None, "seed": self.ids.seed(), "version": 1,
            "versionNonce": self.ids.seed(), "isDeleted": False,
            "boundElements": [], "updated": 1, "link": None, "locked": False,
            "text": text, "fontSize": size, "fontFamily": 1,
            "textAlign": align, "verticalAlign": "middle",
            "containerId": container_id, "originalText": text,
            "lineHeight": 1.25, "autoResize": True,
        }

    def shape(self, kind: str, text: str, x: float, y: float,
              w: float = NODE_W, h: float = NODE_H) -> str:
        """Emit a container shape + bound centered label. Returns container id."""
        shape_map = {
            "process": "rectangle", "io": "rectangle",
            "decision": "diamond", "terminal": "ellipse", "exit": "ellipse",
        }
        pal = PALETTE[kind]
        etype = shape_map[kind]
        roundness = {"type": 3} if etype == "rectangle" else None
        node = self._base(etype, x, y, w, h, pal["stroke"], pal["bg"], roundness)
        label = self._text(node["id"], text, x, y, w, h)
        node["boundElements"].append({"type": "text", "id": label["id"]})
        self.elements.append(node)
        self.elements.append(label)
        return node["id"]

    def _find(self, eid: str) -> dict:
        return next(e for e in self.elements if e["id"] == eid)

    def arrow(self, a_id: str, b_id: str, label: str = "") -> str:
        """Bound arrow a→b with sensible edge anchors. Returns arrow id."""
        a, b = self._find(a_id), self._find(b_id)
        ax, ay = a["x"] + a["width"] / 2, a["y"] + a["height"] / 2
        bx, by = b["x"] + b["width"] / 2, b["y"] + b["height"] / 2
        node = self._base("arrow", ax, ay, bx - ax, by - ay, LINE, "transparent", None)
        node["points"] = [[0, 0], [bx - ax, by - ay]]
        node["startBinding"] = {"elementId": a_id, "focus": 0.0, "gap": 4}
        node["endBinding"] = {"elementId": b_id, "focus": 0.0, "gap": 4}
        node["startArrowhead"] = None
        node["endArrowhead"] = "arrow"
        node["lastCommittedPoint"] = None
        a["boundElements"].append({"type": "arrow", "id": node["id"]})
        b["boundElements"].append({"type": "arrow", "id": node["id"]})
        self.elements.append(node)
        if label:
            lbl = self._text(node["id"], label, ax, ay, 120, 24, size=13)
            node["boundElements"].append({"type": "text", "id": lbl["id"]})
            self.elements.append(lbl)
        return node["id"]

    # ── high-level spine API ─────────────────────────────────────────────────
    def step(self, kind: str, text: str, *, prev: str | None,
             label: str = "") -> str:
        """Place a node on the main spine below the cursor, wire from prev."""
        nid = self.shape(kind, text, LANE_X, self._y)
        self._y += V_GAP
        if prev:
            self.arrow(prev, nid, label)
        return nid

    def branch(self, kind: str, text: str, *, at_y: float | None = None,
               dx: float = BRANCH_DX, from_id: str | None = None,
               label: str = "", w: float = NODE_W, h: float = NODE_H) -> str:
        """Place a node offset to the right (alternate path / sub-detail)."""
        y = self._y - V_GAP if at_y is None else at_y
        nid = self.shape(kind, text, LANE_X + dx, y, w, h)
        if from_id:
            self.arrow(from_id, nid, label)
        return nid

    def legend(self, title: str, rows: list[str], *, x: float | None = None,
               y: float = TOP) -> str:
        """Sticky-note panel listing thresholds/constants on the far right."""
        x = (LANE_X + BRANCH_DX + NODE_W + 120) if x is None else x
        body = "\n".join(rows)
        lines = len(rows) + 2
        h = max(140, 30 + lines * 22)
        w = 380
        pal = PALETTE["legend"]
        panel = self._base("rectangle", x, y, w, h, pal["stroke"], pal["bg"],
                           {"type": 3})
        self.elements.append(panel)
        # title (own text element, not container-bound, so it sits top-left)
        head = self._text(panel["id"], f"⚙  {title}", x + 16, y + 12, w - 32, 24,
                          size=18, align="left")
        head["containerId"] = None
        head["verticalAlign"] = "top"
        self.elements.append(head)
        rows_t = self._text(panel["id"], body, x + 16, y + 48, w - 32, h - 60,
                           size=14, align="left")
        rows_t["containerId"] = None
        rows_t["verticalAlign"] = "top"
        self.elements.append(rows_t)
        return panel["id"]

    def title(self, text: str, *, x: float = LANE_X, y: float = 40) -> None:
        t = self._text("", text, x, y, 700, 40, size=28, align="left")
        t["containerId"] = None
        self.elements.append(t)


def scene(elements: list[dict]) -> dict:
    return {
        "type": "excalidraw",
        "version": 2,
        "source": "clutter-whiteboard-gen",
        "elements": elements,
        "appState": {"gridSize": 20, "viewBackgroundColor": "#ffffff"},
        "files": {},
    }


def write(name: str, b: Builder) -> None:
    path = OUT_DIR / f"{name}.excalidraw"
    path.write_text(
        json.dumps(scene(b.elements), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"  wrote {path.relative_to(OUT_DIR.parent.parent)}  "
          f"({len(b.elements)} elements)")


def main() -> None:
    from builders import BUILDERS  # local module; imported here to avoid cycle

    print("Generating Clutter whiteboard scenes…")
    for name, fn in BUILDERS.items():
        ids = _Ids()
        b = Builder(ids)
        fn(b)
        write(name, b)
    print("Done.")


if __name__ == "__main__":
    main()
