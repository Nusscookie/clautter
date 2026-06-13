"""HTTP client and wire-format helpers for the Resolve bridge.

Extracted from rpc_client.py. rpc_client.py imports ResolveHTTP from here
so existing callers are unaffected.
"""

from __future__ import annotations
import json
from typing import Any, Optional

import requests

from src.constants import PATHS

from src.utils.logger import get_logger

log = get_logger(__name__)

_BRIDGE_FILE = PATHS.BRIDGE_FILE
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
        """POST /call. Returns the parsed JSON response dict."""
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


def _encode_refs(value: Any) -> Any:
    """Walk a value and replace ResolveProxy instances with ref markers."""
    # Avoid importing ResolveProxy here to keep the dependency one-way.
    # Instead, check for the _ref attribute that all proxies carry.
    if hasattr(value, "_ref") and hasattr(value, "_http"):
        return {_REF_KEY: value._ref} if value._ref is not None else {_REF_KEY: None}
    if isinstance(value, dict):
        return {k: _encode_refs(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_encode_refs(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_encode_refs(v) for v in value)
    return value


def _reconstruct_error(response: dict[str, Any]) -> Exception:
    """Build a Python exception that mirrors the server-side error."""
    msg = response.get("error", "unknown error")
    err_type = response.get("type", "Exception")
    return RuntimeError(f"{err_type}: {msg}")


def _unwrap_refs(value: Any, http: ResolveHTTP) -> Any:
    """Walk a returned JSON value and convert ref markers to ResolveProxy.

    Imported lazily to avoid a circular import — rpc_client imports us.
    """
    from src.utils.rpc_client import ResolveProxy
    if isinstance(value, dict):
        if set(value.keys()) == {_REF_KEY}:
            return ResolveProxy(value[_REF_KEY], http)
        return {k: _unwrap_refs(v, http) for k, v in value.items()}
    if isinstance(value, list):
        return [_unwrap_refs(v, http) for v in value]
    if isinstance(value, tuple):
        return tuple(_unwrap_refs(v, http) for v in value)
    return value
