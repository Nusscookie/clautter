"""Client side of the Resolve HTTP bridge.

Lives in the ``gui.py`` subprocess. The subprocess has no direct access
to DaVinci Resolve's COM object (external scripting is disabled in the
free edition), so it goes through a localhost HTTP server that runs
inside Resolve's process.

Public surface:

* :class:`ResolveHTTP` — small ``requests.Session`` wrapper (in rpc_http.py).
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

from src.utils.logger import get_logger
from src.utils.rpc_http import (
    ResolveHTTP,
    _REF_KEY,
    _BRIDGE_FILE,
    _reconstruct_error,
    _unwrap_refs,
)

log = get_logger(__name__)


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
        self._ref = ref
        self._http = http

    def __getattr__(self, name: str) -> _Caller:
        if name.startswith("_"):
            raise AttributeError(name)
        return _Caller(name, self._ref, self._http)

    def __repr__(self) -> str:
        ref_label = self._ref or "root"
        return f"<ResolveProxy {ref_label}>"

    def __eq__(self, other: object) -> bool:
        return self is other

    def __ne__(self, other: object) -> bool:
        return self is not other

    def __hash__(self) -> int:
        return id(self)


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
