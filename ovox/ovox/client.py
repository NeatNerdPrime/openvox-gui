"""
OvoxClient — thin HTTP client for the OpenVox GUI REST API.

All commands ultimately go through this class. It handles:
- Base URL + SSL verification from config
- Bearer token auth (JWT from /api/auth/login)
- Consistent error handling and JSON decoding
- Timeouts and simple retry for transient network issues

The client is deliberately small; complex orchestration stays on the server.
"""

import json
import os
import ipaddress
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse

import httpx
from rich.console import Console

from .config import ConfigManager, get_config_manager
from .version import VERSION


console = Console()


def _hostname_bypasses_proxy(hostname: str) -> bool:
    """True if GUI base URL host must not use HTTP(S)_PROXY.

    httpx honors NO_PROXY when trust_env=True, but operators often only list
    one console FQDN while ovox uses another name (corp vs twitter.biz,
    short name, VIP). Internal OpenVox traffic must never go through the
    corporate proxy (407 / broken mTLS).
    """
    h = (hostname or "").strip().lower().rstrip(".")
    if not h:
        return False
    if h in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return True
    try:
        ip = ipaddress.ip_address(h)
        if ip.is_loopback or ip.is_private or ip.is_link_local:
            return True
    except ValueError:
        pass

    # Explicit env (both cases). Comma/space separated; leading-dot suffixes OK.
    raw = os.environ.get("NO_PROXY") or os.environ.get("no_proxy") or ""
    for part in raw.replace(",", " ").split():
        p = part.strip().lower().rstrip(".")
        if not p:
            continue
        if p.startswith("."):
            if h.endswith(p) or h == p[1:]:
                return True
        elif h == p or h.endswith("." + p):
            return True

    # Built-in internal estate suffixes (xAI / lab). Still honor env first above.
    internal_suffixes = (
        ".corp.int-x.ai",
        ".int-x.ai",
        ".twitter.biz",
        ".twttr.net",
        ".questy.org",
        ".local",
    )
    for suf in internal_suffixes:
        if h.endswith(suf) or h == suf[1:]:
            return True
    return False


def _client_proxy_setting(base_url: str) -> Any:
    """Return httpx proxy= value: None to force bypass, True to use trust_env."""
    try:
        host = urlparse(base_url).hostname or ""
    except Exception:
        host = ""
    if _hostname_bypasses_proxy(host):
        return None
    # Let httpx read HTTP_PROXY / HTTPS_PROXY / NO_PROXY from the environment.
    return True


class OvoxAPIError(Exception):
    """Raised for 4xx/5xx responses or malformed replies from the GUI."""

    def __init__(self, status_code: int, message: str, detail: Optional[Any] = None):
        self.status_code = status_code
        self.message = message
        self.detail = detail
        super().__init__(f"[{status_code}] {message}")

    def __str__(self) -> str:
        if self.detail:
            return f"[{self.status_code}] {self.message}: {self.detail}"
        return f"[{self.status_code}] {self.message}"


class OvoxClient:
    """
    Synchronous client used by all CLI commands.

    Usage:
        client = OvoxClient()
        nodes = client.get_nodes(status="failed")
        client.login("admin", "openvox")  # stores token
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        verify_ssl: Optional[bool] = None,
        timeout: Optional[int] = None,
        config_manager: Optional[ConfigManager] = None,
    ):
        self.cm = config_manager or get_config_manager()
        self.base_url = (base_url or self.cm.get_effective_url()).rstrip("/")
        self.token = token or self.cm.get_token()
        cfg = self.cm.load_config()

        # verify_ssl here is the *user intent* (bool or None).
        # We still expose self.verify_ssl for the CLI layer, but the actual
        # value passed to httpx (which can be bool or a CA bundle path) lives
        # in self.verify.
        user_verify = verify_ssl if verify_ssl is not None else cfg.verify_ssl

        if user_verify is False:
            # User explicitly wants no verification
            self.verify_ssl = False
            self.verify = False
        else:
            self.verify_ssl = True
            # Let the config manager decide: normal trust, or Puppet CA bundle
            # when running locally against the internal listener.
            self.verify = self.cm.get_effective_verify()

        self.timeout = timeout or cfg.timeout

        # Proxy: never send console/API calls to internal hosts via corp proxy
        # (fixes 407 when HTTPS_PROXY is set but NO_PROXY is incomplete).
        proxy_setting = _client_proxy_setting(self.base_url)
        client_kwargs: Dict[str, Any] = {
            "base_url": self.base_url,
            "timeout": self.timeout,
            "verify": self.verify,
            "headers": {
                "User-Agent": f"ovox/{VERSION}",
                "Accept": "application/json",
            },
            "trust_env": True,
        }
        # httpx: proxy=None disables proxies; omit or trust_env for env proxies.
        if proxy_setting is None:
            client_kwargs["proxy"] = None
            client_kwargs["trust_env"] = False  # do not re-pick HTTPS_PROXY

        self._client = httpx.Client(**client_kwargs)

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    # ──────────────────────────────────────────────────────────────────────
    # Low-level request helpers
    # ──────────────────────────────────────────────────────────────────────

    def _auth_headers(self) -> Dict[str, str]:
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        expect_json: bool = True,
    ) -> Union[Dict[str, Any], List[Any], str, bytes]:
        """Core request with uniform error handling."""
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        req_headers = {**self._auth_headers(), **(headers or {})}

        try:
            resp = self._client.request(
                method.upper(),
                url,
                params=params,
                json=json,
                data=data,
                headers=req_headers,
            )
        except httpx.RequestError as exc:
            raise OvoxAPIError(0, f"Connection failed: {exc}") from exc

        if resp.status_code >= 400:
            detail = None
            try:
                body = resp.json()
                if isinstance(body, dict):
                    detail = body.get("detail") or body.get("message") or body
            except Exception:
                detail = resp.text[:500] if resp.text else None
            raise OvoxAPIError(resp.status_code, f"API error on {path}", detail)

        if not expect_json:
            return resp.content

        if not resp.content:
            return {}

        try:
            return resp.json()
        except json.JSONDecodeError:
            # Some endpoints return plain text or empty bodies
            return resp.text

    def get(self, path: str, **kw) -> Any:
        return self._request("GET", path, **kw)

    def post(self, path: str, **kw) -> Any:
        return self._request("POST", path, **kw)

    def put(self, path: str, **kw) -> Any:
        return self._request("PUT", path, **kw)

    def delete(self, path: str, **kw) -> Any:
        return self._request("DELETE", path, **kw)

    # ──────────────────────────────────────────────────────────────────────
    # Auth surface (maps to /api/auth/*)
    # ──────────────────────────────────────────────────────────────────────

    def login(self, username: str, password: str, store: bool = True) -> Dict[str, Any]:
        """
        Perform login against the configured GUI. On success, optionally
        persist the returned JWT so future commands are authenticated.
        """
        payload = {"username": username, "password": password}
        data = self.post("/api/auth/login", json=payload)
        if "token" not in data:
            raise OvoxAPIError(200, "Login response missing token", data)

        self.token = data["token"]
        if store:
            self.cm.save_token(self.token)
        return data

    def logout(self) -> None:
        """Forget local token (server-side sessions are stateless JWTs)."""
        self.cm.clear_token()
        self.token = None

    def whoami(self) -> Optional[Dict[str, Any]]:
        """Return current user info if we have a valid token."""
        if not self.token:
            return None
        try:
            # The middleware injects the user; a lightweight protected endpoint
            # is /api/auth/status or we can hit any small endpoint.
            # Use /api/auth/status which is cheap.
            return self.get("/api/auth/status")
        except OvoxAPIError:
            return None

    # ──────────────────────────────────────────────────────────────────────
    # High-level domain methods (add more as command groups are written)
    # ──────────────────────────────────────────────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        """Fleet + server health summary.

        Uses the real /api/dashboard/node-status endpoint when available.
        Falls back to a simple node count if needed.
        """
        try:
            # Lightweight and actually exists
            counts = self.get("/api/dashboard/node-status")
            if isinstance(counts, dict):
                return {
                    "node_status": counts,
                    "url": self.base_url,
                }
            return counts
        except OvoxAPIError:
            # Fallback
            try:
                total = len(self.get_nodes())
                return {
                    "nodes_total": total,
                    "url": self.base_url,
                }
            except Exception:
                return {
                    "status": "partial",
                    "url": self.base_url,
                }

    def get_nodes(
        self,
        status: Optional[str] = None,
        environment: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List nodes with optional filtering."""
        params: Dict[str, Any] = {}
        if status:
            params["status"] = status
        if environment:
            params["environment"] = environment
        if limit:
            params["limit"] = limit
        if offset:
            params["offset"] = offset
        return self.get("/api/nodes/", params=params)  # type: ignore[return-value]

    def get_node(self, certname: str) -> Dict[str, Any]:
        """Detailed view of one node (facts, last report, resources, etc.)."""
        return self.get(f"/api/nodes/{certname}")

    def get_certificates(
        self,
        status: Optional[str] = None,
        all: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Return certificates from the Puppet CA.

        Matches the behavior of `puppetserver ca list`:

        - By default (all=False, no status): only return **pending/requested**
          (unsigned CSRs). This is what most operators want 90% of the time.
        - With all=True: return everything (signed + pending + revoked).
        - Explicit --status can still be used for power users.
        """
        data = self.get("/api/certificates/list")

        if isinstance(data, dict):
            signed = data.get("signed", []) or []
            requested = data.get("requested", []) or []
            revoked = data.get("revoked", []) or []
            all_certs = signed + requested + revoked
        elif isinstance(data, list):
            all_certs = data
        else:
            all_certs = []

        # Explicit status filter takes precedence
        if status:
            status = status.lower()
            if status in ("pending", "requested"):
                items = data.get("requested", []) if isinstance(data, dict) else \
                        [c for c in all_certs if "requested" in str(c.get("raw", "")).lower()]
                return [_normalize_cert_entry(c, status="requested") for c in items]
            if status == "signed":
                items = data.get("signed", []) if isinstance(data, dict) else \
                        [c for c in all_certs if "requested" not in str(c.get("raw", "")).lower()]
                return [_normalize_cert_entry(c, status="signed") for c in items]
            if status == "revoked":
                items = data.get("revoked", []) if isinstance(data, dict) else \
                        [c for c in all_certs if "revoked" in str(c).lower()]
                return [_normalize_cert_entry(c, status="revoked") for c in items]
            return [_normalize_cert_entry(c) for c in all_certs]

        # No explicit status
        if all:
            # Return everything, normalized
            return [_normalize_cert_entry(c) for c in all_certs]

        # Default behavior: only pending/unsigned certs (matches `puppetserver ca list`)
        items = data.get("requested", []) if isinstance(data, dict) else \
                [c for c in all_certs if "requested" in str(c.get("raw", "")).lower()]
        return [_normalize_cert_entry(c, status="requested") for c in items]

    def get_trusted_facts(
        self,
        *,
        certname: Optional[str] = None,
        key: Optional[str] = None,
        value: Optional[str] = None,
        only_with_extensions: bool = True,
    ) -> Dict[str, Any]:
        """Return Puppet trusted facts (certificate extension requests) from signed PEMs.

        Maps to GET /api/certificates/trusted-facts.
        """
        params: Dict[str, Any] = {
            "only_with_extensions": str(only_with_extensions).lower(),
        }
        if certname:
            params["certname"] = certname
        if key:
            params["key"] = key
        if value is not None and value != "":
            params["value"] = value
        return self.get("/api/certificates/trusted-facts", params=params)  # type: ignore[return-value]

    def sign_certificate(self, certname: str) -> Dict[str, Any]:
        """Sign a pending CSR. Backend expects JSON body { "certname": "..." }."""
        return self.post("/api/certificates/sign", json={"certname": certname})

    def revoke_certificate(self, certname: str, clean: bool = False) -> Dict[str, Any]:
        """
        Revoke a certificate.

        The backend has separate /revoke and /clean endpoints.
        If clean=True we call both (revoke first, then clean).
        """
        res = self.post("/api/certificates/revoke", json={"certname": certname})
        if clean:
            try:
                clean_res = self.post("/api/certificates/clean", json={"certname": certname})
                if isinstance(clean_res, dict) and clean_res.get("message"):
                    # Merge messages for the caller
                    res = res if isinstance(res, dict) else {"status": "success"}
                    res["message"] = (res.get("message", "") + " + " + clean_res["message"]).strip(" +")
            except Exception as exc:
                # Don't fail the whole operation if clean has issues; surface it
                if isinstance(res, dict):
                    res["clean_error"] = str(exc)
        return res

    def run_pql(self, query: str, timeout: Optional[int] = None) -> Any:
        """Execute a PQL query against PuppetDB via the GUI proxy."""
        payload = {"query": query}
        if timeout:
            payload["timeout"] = timeout
        return self.post("/api/pql", json=payload)

    def db_reseed(self) -> Dict[str, Any]:
        """Trigger safe re-seed of ENC nodes from the current live fleet.

        Calls POST /api/enc/reseed. This is additive only (no deletes).
        """
        return self.post("/api/enc/reseed")

    # Add more thin wrappers here as we implement command groups:
    #   get_reports, get_facts, deploy_trigger, bolt_task, etc.


def _normalize_cert_entry(entry: Dict[str, Any], status: Optional[str] = None) -> Dict[str, Any]:
    """Make sure every cert dict the CLI sees has 'certname' and 'status' keys."""
    if not isinstance(entry, dict):
        return entry
    out = dict(entry)
    if "certname" not in out:
        out["certname"] = out.get("name") or out.get("certname") or "?"
    if status:
        out["status"] = status
    elif "status" not in out:
        # best-effort from raw line
        raw = str(out.get("raw", ""))
        if "Requested" in raw:
            out["status"] = "requested"
        elif "Signed" in raw:
            out["status"] = "signed"
        elif "Revoked" in raw:
            out["status"] = "revoked"
    return out


def get_client(**overrides) -> OvoxClient:
    """Factory used by commands so they don't have to import ConfigManager."""
    return OvoxClient(**overrides)
