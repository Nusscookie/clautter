"""Local HTTP bridge for the DaVinci Resolve API.

Runs INSIDE DaVinci Resolve's process (started by main.py). Exposes the
``resolve`` COM object and everything reachable from it to a separate
``gui.py`` subprocess via a localhost HTTP endpoint. The subprocess wraps
the response in a transparent ``ResolveProxy`` so existing feature code
works unchanged.

Why: ``DaVinciResolveScript.scriptapp("Resolve")`` from outside Resolve
returns ``None`` on the free edition (external scripting is restricted).
By running the server inside Resolve's process we get a real ``resolve``
object via ``getattr(builtins, "resolve", None)`` and forward calls to it.

Wire format (POST /call)::

    Request:  {"ref": "<uuid>" | null, "method": "GetX", "args": [...], "kwargs": {...}}
    Response: {"value": <primitive>} | {"ref": "<uuid>"} | {"error": "<repr>"}
"""

from __future__ import annotations
import http.server
import json
import os
import socketserver
import threading
from pathlib import Path
from typing import Any

from src.utils.logger import get_logger
from src.utils.rpc_handler import _Handler, _State

log = get_logger(__name__)

_BRIDGE_FILE = Path.home() / ".clutter" / "bridge.json"


class _ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """Handle each request in its own thread — the client may pipeline."""

    daemon_threads = True
    allow_reuse_address = True


def start_server(resolve_obj: Any) -> tuple[_ThreadingServer, int]:
    """Start the bridge HTTP server on a random localhost port.

    Returns the live server (caller may hold it for shutdown) and the
    port that was bound. Writes ``{port, pid}`` to ``~/.clutter/bridge.json``
    so the client subprocess can find us.
    """
    if resolve_obj is None:
        raise ValueError("resolve_obj must not be None")

    state = _State
    state.root = resolve_obj
    state.objects = {}

    server = _ThreadingServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]

    thread = threading.Thread(target=server.serve_forever, daemon=True, name="clutter-bridge")
    thread.start()
    log.info("bridge listening on http://127.0.0.1:%d", port)

    _write_bridge_file(port)
    return server, port


def _write_bridge_file(port: int) -> None:
    """Atomically write the port + pid to ``bridge.json``."""
    _BRIDGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {"port": port, "pid": os.getpid()}
    tmp = _BRIDGE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(tmp, _BRIDGE_FILE)
    log.debug("bridge file written: %s", _BRIDGE_FILE)
