"""HTTP request handler and state for the Resolve bridge server.

Extracted from rpc_server.py. rpc_server.py imports _Handler and _State
from here; everything else stays unchanged.
"""

from __future__ import annotations
import http.server
import json
import uuid
from typing import Any

from src.utils.logger import get_logger

log = get_logger(__name__)

_REF_KEY = "__clutter_ref__"


class _State:
    """Process-wide state shared by all request handler instances."""

    root: Any = None
    objects: dict[str, Any] = {}


def _walk(obj: Any, refs: type[_State]) -> Any:
    """Recursively replace ref markers in *obj* with live objects from *refs*."""
    if isinstance(obj, dict):
        if set(obj.keys()) == {_REF_KEY}:
            ref = obj[_REF_KEY]
            if ref in refs.objects:
                return refs.objects[ref]
            raise KeyError(f"unknown ref: {ref}")
        # JSON always stringifies dict keys; restore integer keys so Fusion
        # Point2D tables ({1: x, 2: y}) survive the HTTP round-trip intact.
        result = {}
        for k, v in obj.items():
            real_k = int(k) if isinstance(k, str) and k.lstrip("-").isdigit() else k
            result[real_k] = _walk(v, refs)
        return result
    if isinstance(obj, list):
        return [_walk(v, refs) for v in obj]
    if isinstance(obj, tuple):
        return tuple(_walk(v, refs) for v in obj)
    return obj


def _encode(value: Any, refs: type[_State]) -> Any:
    """Return a JSON-friendly representation of *value*.

    Primitives pass through. Collections are walked recursively. COM objects
    (anything else) are stored in refs and returned as a ref marker.
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
    """HTTP handler. One instance per request."""

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return

    def _send_json(self, status: int, body: dict[str, Any]) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
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
            self._send_json(200, {"error": repr(e), "type": type(e).__name__})
            return

        encoded = _encode(result, state)
        if isinstance(encoded, dict) and _REF_KEY in encoded:
            self._send_json(200, {"ref": encoded[_REF_KEY]})
        else:
            self._send_json(200, {"value": encoded})
