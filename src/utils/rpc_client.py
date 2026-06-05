"""Client side of the Resolve HTTP bridge.

Lives in the ``gui.py`` subprocess. The subprocess has no direct access
to DaVinci Resolve's COM object (external scripting is disabled in the
free edition), so it goes through a localhost HTTP server that runs
inside Resolve's process.

Public surface:

* :class:`ResolveHTTP` — small ``requests.Session`` wrapper.
* :class:`ResolveProxy` — duck-typed stand-in for a Resolve object.
  Attribute access returns a :class:`_Caller` that performs the HTTP
  round-trip on invocation and wraps non-primitive results in another
  proxy, so chained calls like
  ``resolve.GetProjectManager().GetCurrentProject().GetMediaPool()``
  work exactly like a real local object.
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Optional

import requests

from src.utils.logger import get_logger

log = get_logger(__name__)

_BRIDGE_FILE = Path.home() / ".clutter" / "bridge.json"
_REF_KEY = "__clutter_ref__"

# Long operations (CreateEmptyTimeline, AppendToTimeline on a long
# timeline, batched SetProperty calls) can easily run for a minute or
# more. Five minutes is a generous cap; the server will cancel earlier
# if the underlying Resolve call returns.
DEFAULT_TIMEOUT_SEC = 300


class ResolveHTTP:
    """HTTP client for the bridge server.

    Construct with a base URL (``http://127.0.0.1:<port>``). Holds a
    reusable ``requests.Session`` so repeated calls don't pay the
    connection setup cost.
    """

    def __init__(self, base_url: str, timeout: float = DEFAULT_TIMEOUT_SEC) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()

    def ping(self) -> bool:
        """Return True if the server responds to /ping."""
        try:
            r = self._session.get(f"{self.base_url}/ping", timeout=2)
            return r.ok and r.json().get("ok") is True
        except Exception:
            return False

    def call(
        self,
        ref: Optional[str],
        method: str,
        args: list[Any],
        kwargs: dict[str, Any],
    ) -> dict[str, Any]:
        """POST /call. Returns the parsed JSON response dict.

        Response shapes:
          ``{"value": <primitive>}`` — primitive return
          ``{"ref": "<uuid>"}``      — non-primitive return (new ref)
          ``{"error": "...", "type": "..."}`` — exception on the server
        """
        # We rely on requests' default JSON encoder, but need to convert
        # _Caller / ResolveProxy instances into ref markers first.
        payload = {
            "ref": ref,
            "method": method,
            "args": _encode_refs(args),
            "kwargs": _encode_refs(kwargs),
        }
        r = self._session.post(
            f"{self.base_url}/call",
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()


class _Caller:
    """A bound method on a :class:`ResolveProxy`. Calling it does the HTTP round-trip."""

    __slots__ = ("_method", "_ref", "_http")

    def __init__(self, method: str, ref: Optional[str], http: ResolveHTTP) -> None:
        self._method = method
        self._ref = ref
        self._http = http

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        response = self._http.call(self._ref, self._method, list(args), kwargs)
        if "error" in response:
            raise _reconstruct_error(response)
        if "ref" in response:
            return ResolveProxy(response["ref"], self._http)
        return _unwrap_refs(response.get("value"), self._http)

    def __repr__(self) -> str:
        ref_label = self._ref or "root"
        return f"<Caller {ref_label}.{self._method}>"


class ResolveProxy:
    """Duck-typed stand-in for any Resolve COM object.

    Every attribute access returns a :class:`_Caller`. Chained calls work
    transparently: the server returns a new ``ref``, the client wraps it
    in a fresh :class:`ResolveProxy`, and the chain continues.
    """

    __slots__ = ("_ref", "_http")

    def __init__(self, ref: Optional[str], http: ResolveHTTP) -> None:
        # None means "root resolve object" — passed through as null in JSON.
        self._ref = ref
        self._http = http

    def __getattr__(self, name: str) -> _Caller:
        # __getattr__ is only called for names Python can't find via
        # normal lookup, which is exactly what we want here.
        if name.startswith("_"):
            raise AttributeError(name)
        return _Caller(name, self._ref, self._http)

    def __repr__(self) -> str:
        ref_label = self._ref or "root"
        return f"<ResolveProxy {ref_label}>"

    # Equality / hashing are identity-based by default, which is fine —
    # proxies are never compared to real objects. We only override to
    # silence the "object does not implement __hash__" warning from
    # ``__slots__`` with custom classes.

    def __eq__(self, other: object) -> bool:
        return self is other

    def __ne__(self, other: object) -> bool:
        return self is not other

    def __hash__(self) -> int:
        return id(self)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _encode_refs(value: Any) -> Any:
    """Walk a value and replace :class:`ResolveProxy` instances with ref markers."""
    if isinstance(value, ResolveProxy):
        return {_REF_KEY: value._ref} if value._ref is not None else {_REF_KEY: None}
    if isinstance(value, dict):
        return {k: _encode_refs(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_encode_refs(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_encode_refs(v) for v in value)
    return value


def _reconstruct_error(response: dict[str, Any]) -> Exception:
    """Build a Python exception that mirrors the server-side error.

    We don't have a way to rehydrate the exact class, so we use RuntimeError
    with a message that includes the original class name and repr. That's
    enough for the ``except Exception as e: log.error("...: %s", e)`` sites
    in the rest of the codebase.
    """
    msg = response.get("error", "unknown error")
    err_type = response.get("type", "Exception")
    return RuntimeError(f"{err_type}: {msg}")


def _unwrap_refs(value: Any, http: ResolveHTTP) -> Any:
    """Walk a returned JSON value and convert ref markers to :class:`ResolveProxy`.

    A bare ``{"__clutter_ref__": "abc"}`` becomes a proxy; a list/dict
    containing such markers is walked recursively. Everything else
    (strings, numbers, nested dicts of primitives) passes through.
    """
    if isinstance(value, dict):
        if set(value.keys()) == {_REF_KEY}:
            return ResolveProxy(value[_REF_KEY], http)
        return {k: _unwrap_refs(v, http) for k, v in value.items()}
    if isinstance(value, list):
        return [_unwrap_refs(v, http) for v in value]
    if isinstance(value, tuple):
        return tuple(_unwrap_refs(v, http) for v in value)
    return value


def read_bridge_file() -> Optional[ResolveHTTP]:
    """Read ``~/.clutter/bridge.json`` and return a connected :class:`ResolveHTTP`.

    Returns ``None`` if the file is missing, malformed, or the server is not
    reachable. Caller is expected to fall back to other connect strategies.
    """
    if not _BRIDGE_FILE.exists():
        return None
    try:
        data = json.loads(_BRIDGE_FILE.read_text(encoding="utf-8"))
        port = int(data["port"])
    except (OSError, ValueError, KeyError, TypeError) as e:
        log.debug("bridge file unreadable: %s", e)
        return None
    http = ResolveHTTP(f"http://127.0.0.1:{port}")
    if not http.ping():
        log.debug("bridge ping failed on port %d (stale file?)", port)
        return None
    log.info("bridge connected: http://127.0.0.1:%d", port)
    return http
