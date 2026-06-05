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

Refs: a ``ref`` is a uuid string the server hands out for any non-primitive
return value. The client must echo that ref back on the next call to
identify the target object. ``null`` (or the root marker) means the root
``resolve`` object.
"""

from __future__ import annotations
import http.server
import json
import os
import socketserver
import threading
import uuid
from pathlib import Path
from typing import Any

from src.utils.logger import get_logger

log = get_logger(__name__)

# Where the client looks to find us. Both processes run as the same user
# on the same machine, so Path.home() resolves to the same location.
_BRIDGE_FILE = Path.home() / ".clutter" / "bridge.json"

# Marker dict key for ref-tagged values. We use a magic key shape rather
# than a list/tuple so JSON encoding survives a round trip unchanged.
_REF_KEY = "__clutter_ref__"


class _State:
    """Process-wide state shared by all request handler instances.

    Lives at class level on the handler so we don't pass it through every
    request. ``ThreadingHTTPServer`` instantiates one handler per request.
    """

    root: Any = None
    objects: dict[str, Any] = {}


def _walk(obj: Any, refs: _State) -> Any:
    """Recursively replace ``{__clutter_ref__: "<uuid>"}`` markers in *obj*
    with the corresponding live object from *refs*. Walks dicts, lists,
    and tuples; passes everything else through unchanged.
    """
    if isinstance(obj, dict):
        if set(obj.keys()) == {_REF_KEY}:
            ref = obj[_REF_KEY]
            if ref in refs.objects:
                return refs.objects[ref]
            raise KeyError(f"unknown ref: {ref}")
        return {k: _walk(v, refs) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_walk(v, refs) for v in obj]
    if isinstance(obj, tuple):
        return tuple(_walk(v, refs) for v in obj)
    return obj


def _encode(value: Any, refs: _State) -> Any:
    """Return a JSON-friendly representation of *value*.

    Primitives (str, int, float, bool, None) pass through. Lists, tuples,
    and dicts are walked recursively so each Resolve object inside gets
    its own ref. Anything else (a COM object) is stored on the server
    and returned as a ref marker.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return [_encode(v, refs) for v in value]
    if isinstance(value, tuple):
        return tuple(_encode(v, refs) for v in value)
    if isinstance(value, dict):
        return {k: _encode(v, refs) for k, v in value.items()}
    ref = uuid.uuid4().hex
    refs.objects[ref] = value
    return {_REF_KEY: ref}


class _Handler(http.server.BaseHTTPRequestHandler):
    """HTTP handler. One instance per request (per BaseHTTPRequestHandler)."""

    # Suppress the default access-log line — too noisy in Resolve's console.
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return

    def _send_json(self, status: int, body: dict[str, Any]) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
        if self.path == "/ping":
            self._send_json(200, {"ok": True})
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/call":
            self._send_json(404, {"error": "not found"})
            return

        length = int(self.headers.get("Content-Length", "0") or "0")
        try:
            raw = self.rfile.read(length) if length else b"{}"
            body = json.loads(raw.decode("utf-8"))
            ref = body.get("ref")
            method = body.get("method")
            args = body.get("args", [])
            kwargs = body.get("kwargs", {})
        except Exception as e:
            log.error("bridge: bad request: %s", e)
            self._send_json(400, {"error": f"bad request: {e!r}"})
            return

        if not isinstance(method, str):
            self._send_json(400, {"error": "method must be a string"})
            return

        # Resolve target object. ``ref`` None (or root marker) -> the resolve root.
        state = _State
        if ref is None or ref == "root":
            target = state.root
        else:
            target = state.objects.get(ref)
            if target is None:
                self._send_json(404, {"error": f"unknown ref: {ref}"})
                return

        try:
            material_args = _walk(args, state)
            material_kwargs = _walk(kwargs, state)
            result = getattr(target, method)(*material_args, **material_kwargs)
        except Exception as e:
            log.exception("bridge: %s.%s failed", type(target).__name__, method)
            # Return errors in the body with HTTP 200 — the client
            # inspects ``error`` and re-raises. Returning 500 trips
            # ``requests.raise_for_status()`` before we can read it.
            self._send_json(200, {"error": repr(e), "type": type(e).__name__})
            return

        encoded = _encode(result, state)
        if isinstance(encoded, dict) and _REF_KEY in encoded:
            self._send_json(200, {"ref": encoded[_REF_KEY]})
        else:
            self._send_json(200, {"value": encoded})


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
