"""Modal Toplevel showing search results from Pixabay / Pexels.

One scrollable card per result, grouped by the keyword that produced
it. Each card has a Download button (spawns a download worker) and an
Open Page button (opens the provider's landing page in the user's
default browser).
"""

from __future__ import annotations
import io
import threading
import webbrowser
from pathlib import Path
from typing import Any, Callable

import customtkinter as ctk

from src.broll.providers.base import ClipResult
from src.utils.logger import get_logger

log = get_logger(__name__)


class BrollResultsWindow(ctk.CTkToplevel):
    """Modal, scrollable result window. Self-destructs on close."""

    def __init__(
        self,
        master: Any,
        *,
        app: Any,
        results_by_keyword: dict[str, list[ClipResult]],
        target_dir: str,
        set_status: Callable,
        ui: Callable,
    ) -> None:
        super().__init__(master)

        self._app = app
        self._set_status = set_status
        self._ui = ui
        self._target_dir = target_dir

        self.title("B-Roll Search Results")
        self.geometry("780x620")
        self.minsize(620, 400)
        self.configure(fg_color="#141414")

        # Resolve to the actual top-level window. ``master`` may be a
        # CTkFrame inside a CTkTabview, in which case ``transient(master)``
        # would target a non-toplevel and silently no-op. Falling back to
        # the resolved toplevel keeps the modal + grab working.
        top_master = None
        try:
            top_master = master.winfo_toplevel() if master else None
        except Exception:
            top_master = None

        try:
            if top_master is not None and top_master is not self:
                self.transient(top_master)
            self.grab_set()
            self.focus_set()
        except Exception as e:
            log.warning("Results window modal setup partial: %s", e)

        self._build(results_by_keyword)
        # Force layout, then lift on the next tick so the window is fully
        # realised before we ask the window manager to raise it.
        self.update_idletasks()
        self.after(300, self._raise)

    def _raise(self) -> None:
        """Bring the window to the front and re-assert the grab."""
        try:
            self.deiconify()
            self.lift()
            self.focus_force()
            self.grab_set()
        except Exception as e:
            log.debug("Results window raise failed: %s", e)

    # ── Layout ──────────────────────────────────────────────────────

    def _build(self, results_by_keyword: dict[str, list[ClipResult]]) -> None:
        header = ctk.CTkFrame(self, fg_color="#1e1e1e", corner_radius=0, height=48)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)
        ctk.CTkLabel(
            header,
            text=f"B-Roll Results  —  {len(results_by_keyword)} keyword(s)  ·  "
                 f"{sum(len(v) for v in results_by_keyword.values())} clip(s)",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#4fc3f7", anchor="w",
        ).pack(side="left", padx=14, pady=12)

        ctk.CTkLabel(
            header,
            text=f"Saving to: {self._target_dir}",
            font=ctk.CTkFont(size=10),
            text_color="#888888", anchor="e",
        ).pack(side="right", padx=14, pady=12)

        # Scrollable body
        body = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
        body.pack(fill="both", expand=True, padx=8, pady=(4, 8))
        body.grid_columnconfigure(0, weight=1)

        for keyword, hits in results_by_keyword.items():
            if not hits:
                continue
            self._build_section(body, keyword, hits)

        # Footer
        footer = ctk.CTkFrame(self, fg_color="#1e1e1e", corner_radius=0, height=36)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)
        ctk.CTkLabel(
            footer,
            text="Downloaded clips are saved locally and added to Resolve's Media Pool.",
            font=ctk.CTkFont(size=10),
            text_color="#888888", anchor="w",
        ).pack(side="left", padx=14, pady=8)
        ctk.CTkButton(
            footer, text="Close", width=80,
            fg_color="#2a2a2a", hover_color="#3a3a3a",
            command=self.destroy,
        ).pack(side="right", padx=14, pady=6)

    def _build_section(
        self, parent: Any, keyword: str, hits: list[ClipResult],
    ) -> None:
        # Section header
        ctk.CTkLabel(
            parent,
            text=f"  '{keyword}'  —  {len(hits)} result(s)",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#aaaaaa", anchor="w",
            fg_color="#1e1e1e", corner_radius=4,
        ).pack(fill="x", padx=4, pady=(10, 4), ipady=4)

        for idx, hit in enumerate(hits):
            self._build_card(parent, hit, keyword, idx)

    def _build_card(
        self, parent: Any, clip: ClipResult, keyword: str, idx: int,
    ) -> None:
        card = ctk.CTkFrame(parent, fg_color="#2a2a2a", corner_radius=6)
        card.pack(fill="x", padx=4, pady=(0, 4))

        # Top row: source tag + title
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=(8, 2))
        top.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            top, text=clip.source.upper(),
            font=ctk.CTkFont(size=9, weight="bold"),
            text_color="#141414",
            fg_color="#4fc3f7" if clip.source == "pixabay" else "#ffa726",
            corner_radius=3, width=64,
        ).grid(row=0, column=0, padx=(0, 8), sticky="w", ipady=2)

        ctk.CTkLabel(
            top, text=clip.title or "(untitled)",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#ffffff", anchor="w",
        ).grid(row=0, column=1, sticky="ew")

        # Thumbnail preview
        thumb_lbl = ctk.CTkLabel(
            card, text="", fg_color="#1e1e1e",
            width=320, height=90, corner_radius=4,
        )
        thumb_lbl.pack(fill="x", padx=10, pady=(4, 2))

        if clip.thumbnail_url:
            def _fetch_thumb(url: str = clip.thumbnail_url, lbl: Any = thumb_lbl) -> None:
                import requests as _req
                from PIL import Image as _Img
                try:
                    resp = _req.get(url, timeout=5)
                    resp.raise_for_status()
                    img = _Img.open(io.BytesIO(resp.content)).convert("RGB")
                    img.thumbnail((320, 180))
                    ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
                    self.after(0, lambda i=ctk_img, h=img.height: lbl.configure(image=i, height=h))
                except Exception:
                    pass  # gray placeholder stays
            threading.Thread(target=_fetch_thumb, daemon=True).start()

        # Meta row
        meta_bits = []
        if clip.duration_sec:
            meta_bits.append(f"{clip.duration_sec}s")
        if clip.width and clip.height:
            meta_bits.append(f"{clip.width}×{clip.height}")
        if clip.external_id:
            meta_bits.append(f"id:{clip.external_id}")
        ctk.CTkLabel(
            card,
            text="  ·  ".join(meta_bits) if meta_bits else " ",
            font=ctk.CTkFont(size=10),
            text_color="#888888", anchor="w",
        ).pack(fill="x", padx=10, pady=(0, 2))

        # Page URL
        if clip.page_url:
            ctk.CTkLabel(
                card, text=clip.page_url,
                font=ctk.CTkFont(size=9),
                text_color="#555555", anchor="w", wraplength=720,
            ).pack(fill="x", padx=10, pady=(0, 4))

        # Action row
        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.pack(fill="x", padx=10, pady=(2, 8))
        actions.grid_columnconfigure(0, weight=1)

        status_lbl = ctk.CTkLabel(
            actions, text="",
            font=ctk.CTkFont(size=10),
            text_color="#aaaaaa", anchor="w",
        )
        status_lbl.grid(row=0, column=0, sticky="w")

        if clip.page_url:
            ctk.CTkButton(
                actions, text="Open Page", width=90,
                fg_color="#2a2a2a", hover_color="#3a3a3a",
                command=lambda url=clip.page_url: self._open_url(url),
            ).grid(row=0, column=1, padx=(0, 6))

        download_btn = ctk.CTkButton(
            actions, text="Download", width=100,
            fg_color="#1b5e20", hover_color="#2e7d32",
        )
        download_btn.grid(row=0, column=2)

        def on_download(clip=clip, btn=download_btn, lbl=status_lbl) -> None:
            btn.configure(state="disabled", text="Downloading…")
            lbl.configure(text="Starting download…", text_color="#4fc3f7")

            def per_card_status(msg: str, color: str) -> None:
                self._ui(lambda m=msg, c=color: lbl.configure(text=m, text_color=c))

            def worker() -> None:
                from src.broll.downloader import BrollDownloader
                from src.broll.providers.base import NetworkError
                try:
                    per_card_status(f"Downloading {clip.title}…", "#4fc3f7")
                    downloader = BrollDownloader(self._target_dir, self._app)
                    result = downloader.download_and_import(clip)
                    name = Path(result["path"]).name
                    per_card_status(
                        f"Saved: {name} → media pool.", "#66bb6a")
                except NetworkError as e:
                    log.error("Download failed for %s: %s", clip.external_id, e)
                    per_card_status(f"Download failed: {e}", "#ff6b6b")
                except Exception as e:
                    log.error("Unexpected download error: %s", e)
                    per_card_status(f"Error: {e}", "#ff6b6b")
                finally:
                    self._ui(lambda: btn.configure(state="normal", text="Download"))

            threading.Thread(target=worker, daemon=True).start()

        download_btn.configure(command=on_download)

    # ── Actions ─────────────────────────────────────────────────────

    @staticmethod
    def _open_url(url: str) -> None:
        try:
            webbrowser.open(url)
        except Exception as e:
            log.warning("webbrowser.open failed: %s", e)
