"""
Code Deployment API - Interface with r10k for Puppet code deployment.
"""
import json
import logging
import re
import socket
import subprocess
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from ..middleware.security import rate_limit_heavy, concurrency_heavy
from ..dependencies import require_role
from ..utils.sudo import run_sudo

router = APIRouter(prefix="/api/deploy", tags=["deploy"])
logger = logging.getLogger(__name__)

# r10k can take several minutes on large Puppetfiles; keep this aligned with the UI.
R10K_DEPLOY_TIMEOUT = 300
R10K_DEPLOY_SCRIPT = "/opt/openvox-gui/scripts/r10k-deploy.sh"


class DeployRequest(BaseModel):
    environment: Optional[str] = None  # None = all environments


def _run_command(cmd: List[str], timeout: int = 300) -> dict:
    """Run a non-privileged shell command (e.g. git status reads) and return output.

    Do **not** use this for ``sudo`` / r10k. Privileged deploy paths must go
    through ``_run_r10k_deploy`` → ``run_sudo`` so requiretty is satisfied under
    systemd (see backend/app/utils/sudo.py).
    """
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        return {
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "success": result.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": "Command timed out",
            "success": False,
        }
    except Exception as e:
        logger.error("deploy _run_command failed: %s", e, exc_info=True)
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": str(e),
            "success": False,
        }


def _r10k_cmd(environment: Optional[str] = None) -> List[str]:
    """Build the exact argv allowed by sudoers for r10k-deploy.sh."""
    cmd = ["sudo", R10K_DEPLOY_SCRIPT]
    if environment:
        cmd.append(environment)
    cmd.extend(["-pv"])
    return cmd


async def _run_r10k_deploy(environment: Optional[str] = None, timeout: int = R10K_DEPLOY_TIMEOUT) -> dict:
    """Run r10k via run_sudo (PTY/script) so Code Deployment works under requiretty.

    Historically this path used bare ``subprocess.run(["sudo", ...])``, which
    fails with ``sudo: sorry, you must have a tty to run sudo`` whenever the
    service has no TTY and ``Defaults requiretty`` is in effect — even when
    other GUI pages worked because they already used ``run_sudo``.
    """
    cmd = _r10k_cmd(environment)
    result = await run_sudo(cmd, timeout=timeout)
    rc = result.get("returncode", -1)
    try:
        exit_code = int(rc) if rc is not None else -1
    except (TypeError, ValueError):
        exit_code = -1
    return {
        "exit_code": exit_code,
        "stdout": result.get("stdout") or "",
        "stderr": result.get("stderr") or "",
        "success": exit_code == 0,
    }


@router.get("/environments")
async def list_deployable_environments():
    """List available environments for deployment."""
    from ..services.puppetserver import puppetserver_service
    envs = await puppetserver_service.fetch_environments()
    return {"environments": envs}


@router.get("/repos")
async def get_repos():
    """Discover configured git source repos (control repo + r10k sources)."""
    try:
        from ..config import settings
        from pathlib import Path
        import re
        import yaml

        repos = []

        # 1. Read r10k.yaml for source repos (control repo, etc.)
        r10k_paths = [
            Path("/etc/puppetlabs/r10k/r10k.yaml"),
            Path("/etc/puppetlabs/code/r10k.yaml"),
        ]
        for r10k_path in r10k_paths:
            if r10k_path.exists():
                try:
                    r10k_cfg = yaml.safe_load(r10k_path.read_text())
                    sources = r10k_cfg.get("sources", {})
                    for name, src in sources.items():
                        url = src.get("remote", "")
                        basedir = src.get("basedir", "")
                        display_url = re.sub(r'oauth2:[^@]+@', '', url)
                        display_url = re.sub(r'://[^:]+:[^@]+@', '://', display_url)
                        repos.append({
                            "name": name,
                            "url": display_url,
                            "basedir": basedir,
                            "type": "control",
                            "source": str(r10k_path),
                        })
                except Exception as e:
                    logger.warning(f"Error reading {r10k_path}: {e}")
                break

        # 2. Parse Puppetfile for git modules (roles, profiles, etc.)
        puppetfile = Path(settings.puppet_codedir) / "environments" / "production" / "Puppetfile"
        if puppetfile.exists():
            content = puppetfile.read_text()
            # Match: mod 'name', :git => 'url'  OR  mod 'name', git: 'url'
            git_pattern = re.compile(
                r"mod\s+'([^']+)'\s*,\s*"
                r"(?::git\s*=>\s*'([^']+)'|git:\s*'([^']+)')",
                re.MULTILINE
            )
            branch_pattern = re.compile(
                r"(?::(?:branch|ref|tag)\s*=>\s*'([^']+)'|(?:branch|ref|tag):\s*'([^']+)')"
            )
            for match in git_pattern.finditer(content):
                name = match.group(1)
                url = match.group(2) or match.group(3)
                display_url = re.sub(r'oauth2:[^@]+@', '', url)
                display_url = re.sub(r'://[^:]+:[^@]+@', '://', display_url)
                # Find associated branch
                branch = "main"
                rest = content[match.end():]
                br_match = branch_pattern.search(rest[:200])
                if br_match:
                    branch = br_match.group(1) or br_match.group(2) or "main"
                repos.append({
                    "name": name,
                    "url": display_url,
                    "branch": branch,
                    "type": "module",
                    "source": str(puppetfile),
                })

        return {"repos": repos}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_deploy_status():
    """Get last deployment status info."""
    try:
        from ..config import settings
        from pathlib import Path

        env_dir = Path(settings.puppet_codedir) / "environments" / "production"
        last_commit = "unknown"
        if (env_dir / ".git").exists():
            result = _run_command(["git", "-C", str(env_dir), "log", "-1", "--format=%H %ci %s"])
            last_commit = result["stdout"].strip() if result["success"] else "unknown"

        return {
            "last_commit": last_commit,
            "environments_path": str(env_dir.parent),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/webhook", include_in_schema=True)
async def webhook_deploy(request: Request):
    """GitHub webhook endpoint for automatic code deployment.

    Configured as a GitHub webhook with HMAC-SHA256 signature
    verification. When the operator configures a shared secret via
    OPENVOX_GUI_DEPLOY_WEBHOOK_SECRET in .env (and the same string
    in the GitHub webhook settings), every push event triggers an
    r10k deployment of the pushed branch.

    GitHub webhook setup:
      1. Go to your control repo -> Settings -> Webhooks -> Add webhook
      2. Payload URL: https://your-server:4567/api/deploy/webhook
      3. Content type: application/json
      4. Secret: same value as OPENVOX_GUI_DEPLOY_WEBHOOK_SECRET
      5. Events: Just the push event

    Security model (hardened in 3.3.5-27 -- audit CRIT-3):

    * If OPENVOX_GUI_DEPLOY_WEBHOOK_SECRET is empty / unset, EVERY
      request to this endpoint returns 503. The previous "anonymous,
      please add an IP filter yourself" posture was an open
      r10k-deploy-as-root entrypoint.

    * If the secret is set, the request must carry a valid
      X-Hub-Signature-256: sha256=<hex> header (HMAC-SHA256 of the
      raw request body, keyed by the shared secret). Mismatched
      signatures return 401. hmac.compare_digest is used to avoid
      timing attacks.

    * The 'ref' field from the payload (what r10k-deploy.sh receives
      as the environment name) is validated against
      OPENVOX_GUI_DEPLOY_WEBHOOK_REF_PATTERN before being passed to
      sudo/subprocess. The default pattern (^[a-zA-Z0-9._/-]{1,200}$)
      matches what git itself accepts in branch names; anything else
      returns 400.
    """
    import hmac
    import hashlib
    import json
    import re as _re
    from ..config import settings

    # Hard refusal when no secret is configured. This used to be
    # "warn and continue" -- now it's a fail-closed default so an
    # accidentally-exposed openvox-gui can't be turned into an
    # arbitrary-code-deploy oracle by a passing scanner.
    secret = (settings.deploy_webhook_secret or "").strip()
    if not secret:
        logger.warning("Webhook called but OPENVOX_GUI_DEPLOY_WEBHOOK_SECRET is unset; returning 503.")
        raise HTTPException(
            status_code=503,
            detail="Deploy webhook is disabled. Set OPENVOX_GUI_DEPLOY_WEBHOOK_SECRET in .env to enable it.",
        )

    # Read the raw body (we need the unparsed bytes for HMAC) and
    # only THEN parse it as JSON.
    raw_body = await request.body()

    sig_header = request.headers.get("X-Hub-Signature-256", "")
    if not sig_header.startswith("sha256="):
        logger.warning("Webhook called without X-Hub-Signature-256 header.")
        raise HTTPException(status_code=401, detail="Missing X-Hub-Signature-256 header")

    expected = hmac.new(
        secret.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    provided = sig_header[len("sha256="):]
    if not hmac.compare_digest(expected, provided):
        logger.warning("Webhook signature mismatch (expected vs provided differ).")
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Signature is valid -- parse the payload.
    try:
        payload = json.loads(raw_body or b"{}")
    except (ValueError, TypeError):
        payload = {}

    ref = payload.get("ref", "")
    branch = ref.split("/")[-1] if "/" in ref else ref
    pusher = payload.get("pusher", {}).get("name", "unknown")
    head_commit = payload.get("head_commit", {})
    commit_msg = head_commit.get("message", "")[:100] if head_commit else ""

    # Strict ref validation -- prevents arg injection into the r10k
    # subprocess. The default pattern allows what git itself allows
    # in branch names but rejects anything with whitespace, shell
    # metacharacters, or path traversal sequences.
    ref_pattern = _re.compile(settings.deploy_webhook_ref_pattern)
    if branch and not ref_pattern.match(branch):
        logger.warning(f"Webhook rejected: invalid branch name '{branch}'")
        raise HTTPException(status_code=400, detail="Invalid branch / ref")

    logger.info(f"Webhook authenticated: branch={branch}, pusher={pusher}, commit={commit_msg}")

    # Trigger r10k deploy for the pushed branch (or all environments
    # if the ref couldn't be determined / is the default 'main').
    # Must use run_sudo (via _run_r10k_deploy) — bare subprocess sudo fails
    # under systemd when requiretty is set.
    env_name = branch if branch and branch not in ("", "main") else None
    result = await _run_r10k_deploy(environment=env_name, timeout=R10K_DEPLOY_TIMEOUT)

    from ..utils.audit import audit_event
    from ..services import deploy_history as deploy_hist

    out_preview = ((result.get("stdout") or "") + (result.get("stderr") or ""))[:500]
    deploy_hist.record_deploy(
        environment=branch or "all",
        triggered_by=f"github-webhook ({pusher})",
        success=result["success"],
        exit_code=result["exit_code"],
        output_lines=len(out_preview.splitlines()),
        output_preview=out_preview,
        commit=commit_msg,
    )
    try:
        from ..database import async_session
        async with async_session() as db:
            await deploy_hist.record_deploy_execution(
                db,
                environment=branch or "all",
                executed_by=f"webhook:{pusher}",
                success=result["success"],
                exit_code=result["exit_code"],
                output_preview=out_preview,
            )
    except Exception:
        pass

    audit_event(
        "deploy_webhook",
        user=f"webhook:{pusher}",
        targets=branch or "all",
        detail=(commit_msg or "")[:120],
        rc=result["exit_code"],
        success=result["success"],
    )

    return {
        "success": result["success"],
        "branch": branch,
        "pusher": pusher,
        "exit_code": result["exit_code"],
    }


@router.post("/run")
@rate_limit_heavy()
async def run_deployment(
    deploy: DeployRequest,
    request: Request,
    current_user: str = Depends(require_role("admin", "operator")),
    _=Depends(concurrency_heavy),
):
    """
    Trigger an r10k deployment.
    Requires admin or operator role (srdev2 A7 — Depends, not inline RBAC).
    """
    username = current_user or "anonymous"

    try:
        cmd = _r10k_cmd(deploy.environment)
        logger.info("User '%s' triggered r10k deployment: %s", username, " ".join(cmd))

        # PTY-aware sudo runner — Code Deployment used to call bare subprocess
        # and hit "must have a tty to run sudo" on RHEL requiretty systems.
        result = await _run_r10k_deploy(
            environment=deploy.environment,
            timeout=R10K_DEPLOY_TIMEOUT,
        )

        from ..utils.audit import audit_event
        from ..services import deploy_history as deploy_hist

        audit_event(
            "deploy_run",
            user=username,
            targets=deploy.environment or "all",
            detail="r10k-deploy.sh -pv",
            rc=result["exit_code"],
            success=result["success"],
        )

        log_lines = []
        if result["stdout"]:
            log_lines.extend(result["stdout"].strip().splitlines())
        if result["stderr"]:
            log_lines.extend(result["stderr"].strip().splitlines())

        preview = "\n".join(log_lines)[:500]
        deploy_hist.record_deploy(
            environment=deploy.environment or "all",
            triggered_by=username,
            success=result["success"],
            exit_code=result["exit_code"],
            output_lines=len(log_lines),
            output_preview=preview,
        )
        # Dual-write SQLite execution_history (srdev2 A6)
        try:
            from ..database import async_session
            async with async_session() as db:
                await deploy_hist.record_deploy_execution(
                    db,
                    environment=deploy.environment or "all",
                    executed_by=username,
                    success=result["success"],
                    exit_code=result["exit_code"],
                    output_preview=preview,
                    error_message=None if result["success"] else (result.get("stderr") or "")[:500],
                )
        except Exception as db_exc:
            logger.warning("deploy execution_history dual-write failed: %s", db_exc)

        response = {
            "success": result["success"],
            "exit_code": result["exit_code"],
            "environment": deploy.environment or "all",
            "triggered_by": username,
            "output": log_lines,
        }
        return response
    except Exception as e:
        logger.error("Deployment error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


STAGE_ACTIVATE_SCRIPT = "/opt/openvox-gui/scripts/r10k-stage-activate.sh"
# SSH probe must fail fast. A password prompt on compilers without bolt@
# used to hang the uvicorn worker until R10K_DEPLOY_TIMEOUT (or kill it).
_CLUSTER_SSH_PROBE_TIMEOUT = 25
_ENV_NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")


class ClusterDeployRequest(BaseModel):
    environment: Optional[str] = None
    targets: Optional[List[str]] = None  # override configured deploy targets


_NOEXEC_HINT = (
    "OpenBolt uploaded the helper under /tmp (or another noexec mount) and "
    "the kernel refused to execute it. CIS on this estate mounts /tmp "
    "noexec. GUI inventory must use ssh.tmpdir=/home/bolt/.bolt/tmp. "
    "On a compiler: findmnt -no OPTIONS /tmp"
)

_TMPDIR_HINT = (
    "OpenBolt could not create ssh.tmpdir (/home/bolt/.bolt/tmp). "
    "It uses mkdir -m 700 $tmpdir/<uuid> with no -p, so the parents "
    "must already exist and be writable by bolt. Stage now runs "
    "`install -d -o bolt -g bolt -m 700 /home/bolt /home/bolt/.bolt "
    "/home/bolt/.bolt/tmp` as root first — update_local to alpha.47+. "
    "On a compiler: getent passwd bolt; ls -ld /home/bolt /home/bolt/.bolt"
)

# OpenBolt `mkdir -m 700 $tmpdir/<uuid>` (no -p). Created as root before script run.
# Also fail-fast if r10k / r10k.yaml is missing — otherwise one compiler
# runs a 5-minute deploy while the others die and the GUI just spins.
_PREP_BOLT_TMPDIR = (
    "install -d -o bolt -g bolt -m 700 "
    "/home/bolt /home/bolt/.bolt /home/bolt/.bolt/tmp && "
    "if [ -x /opt/puppetlabs/puppet/bin/r10k ]; then R10K=/opt/puppetlabs/puppet/bin/r10k; "
    "elif command -v r10k >/dev/null 2>&1; then R10K=$(command -v r10k); "
    "else echo MISSING_R10K host=$(hostname -f); exit 2; fi && "
    "if [ ! -f /etc/puppetlabs/r10k/r10k.yaml ]; then "
    "echo MISSING_R10K_YAML host=$(hostname -f) r10k=$R10K; exit 3; fi && "
    "echo OK host=$(hostname -f) r10k=$R10K yaml=/etc/puppetlabs/r10k/r10k.yaml"
)


_ANSI_RE = re.compile(r"\x1b\[[0-9;:]*[A-Za-z]|\x1b\][^\x07]*\x07|\x00")
_CLI_OVERRIDE_RE = re.compile(r"CLI arguments .* might be overridden", re.I)
_SKIP_BODY = (
    "error during concurrent deploy of a module",
    "the command failed with exit code",
)


def _strip_ctrl(text: str) -> str:
    return _ANSI_RE.sub("", text or "").replace("\x00", "")


def _extract_bolt_json(blob: str) -> Optional[dict]:
    """Bolt --format json is often prefixed with ANSI / cli_overrides warnings."""
    cleaned = _strip_ctrl(blob).strip()
    if "{" in cleaned:
        cleaned = cleaned[cleaned.find("{") :]
    if not cleaned.startswith("{"):
        return None
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _script_body(value: dict) -> str:
    for key in ("merged_output", "stderr", "stdout"):
        text = value.get(key) or ""
        if str(text).strip():
            return str(text)
    err = value.get("_error") if isinstance(value.get("_error"), dict) else {}
    return str(err.get("msg") or "")


def _clean_script_lines(text: str) -> List[str]:
    out: List[str] = []
    seen_err: set = set()
    for raw in _strip_ctrl(text).splitlines():
        ln = raw.replace("\t", " ").strip()
        if not ln:
            continue
        if _CLI_OVERRIDE_RE.search(ln):
            continue
        low = ln.lower()
        if any(skip in low for skip in _SKIP_BODY):
            continue
        if "failed to synchronize" in low or "unable to connect to https://forgeapi" in low:
            if ln in seen_err:
                continue
            seen_err.add(ln)
        if out and out[-1] == ln:
            continue
        out.append(ln)
    return out


def _host_headline(target: str, ok: bool, exit_code: Any, body: str) -> str:
    mark = "ok" if ok else "FAIL"
    reason = ""
    low = body.lower()
    if "github.com" in low and (
        "could not connect" in low or "unable to access" in low or "failed to connect" in low
    ):
        reason = " — github.com:443 (git fetch; root needs https.proxy)"
    elif "forgeapi.puppet.com" in low:
        reason = (
            " — forgeapi.puppet.com:443 (Puppetfile; r10k uses HTTPS_PROXY, "
            "not gitconfig)"
        )
    elif "missing_r10k_yaml" in low:
        reason = " — missing /etc/puppetlabs/r10k/r10k.yaml"
    elif "missing_r10k" in low:
        reason = " — r10k not installed"
    return f"── {target}  {mark}  exit {exit_code}{reason}"


def _flatten_bolt_json(
    result: Dict[str, Any],
    targets: List[str],
    via: str = "bolt",
) -> tuple:
    """Turn ``bolt --format json`` into per-host headlines + cleaned log lines.

    Never dump the raw JSON blob. Bolt prefixes JSON with ANSI / warnings;
    extract the object. Prefer merged_output once (stdout+stderr are copies).
    """
    rc = result.get("returncode")
    rc = -1 if rc is None else int(rc)
    stdout = result.get("stdout") or ""
    stderr = result.get("stderr") or ""
    lines: List[str] = []
    for ln in _strip_ctrl(stderr).splitlines():
        ln = ln.strip()
        if ln and not _CLI_OVERRIDE_RE.search(ln):
            lines.append(ln)
    hosts: List[dict] = []

    data = _extract_bolt_json(stdout)
    if data is None:
        for ln in _clean_script_lines(stdout):
            lines.append(ln)
        return rc, lines, [
            {"host": t, "success": rc == 0, "via": via, "exit_code": rc}
            for t in targets
        ]

    items = data.get("items") or []
    saw_noexec = False
    saw_tmpdir = False
    summaries: List[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        target = item.get("target") or "unknown"
        status = item.get("status")
        value = item.get("value") if isinstance(item.get("value"), dict) else {}
        exit_code = value.get("exit_code")
        err = value.get("_error") if isinstance(value.get("_error"), dict) else {}
        if exit_code is None:
            details = err.get("details") if isinstance(err.get("details"), dict) else {}
            exit_code = details.get("exit_code")
        if exit_code is None:
            exit_code = 0 if status == "success" else rc
        ok = status == "success"
        hosts.append({
            "host": target,
            "success": ok,
            "via": via,
            "exit_code": exit_code,
        })
        body = _script_body(value)
        summaries.append(_host_headline(target, ok, exit_code, body))
        for ln in _clean_script_lines(body):
            lines.append(f"[{target}] {ln}")
        issue = str(err.get("issue_code") or "")
        combined = f"{body}\n{issue}".lower()
        if (
            "permission denied" in combined
            or "noexec" in combined
            or exit_code in (126, 13)
        ):
            saw_noexec = True
        if "tmpdir" in combined or issue == "TMPDIR_ERROR":
            saw_tmpdir = True

    if not hosts:
        hosts = [
            {"host": t, "success": rc == 0, "via": via, "exit_code": rc}
            for t in targets
        ]
    if summaries:
        lines = summaries + [""] + lines
    if saw_tmpdir:
        lines.append(_TMPDIR_HINT)
    elif saw_noexec:
        lines.append(_NOEXEC_HINT)
    return rc, lines, hosts


def _cluster_env_args(mode: str, environment: Optional[str]) -> List[str]:
    """Build [mode] or [mode, env]. Treat All Environments as no env name."""
    args = [mode]
    env = (environment or "").strip()
    if env and env.lower() not in ("all", "none", "*"):
        if not _ENV_NAME_RE.match(env):
            raise ValueError(f"Invalid environment name: {environment!r}")
        args.append(env)
    return args


def _local_hostnames() -> set:
    """Local short + FQDN names. Avoid socket.getfqdn() — it can hang on DNS."""
    names: set = set()
    try:
        n = socket.gethostname()
    except OSError:
        n = ""
    if n:
        names.add(n.lower())
        names.add(n.split(".")[0].lower())
    return names


def _cluster_result(
    mode: str,
    environment: Optional[str],
    targets: List[str],
    success: bool,
    exit_code: int,
    output: List[str],
    hosts: List[dict],
) -> Dict[str, Any]:
    return {
        "success": success,
        "exit_code": exit_code,
        "hosts": hosts,
        "output": output,
        "mode": mode,
        "environment": environment or "all",
        "targets": targets,
    }


async def _run_on_targets(
    mode: str,
    environment: Optional[str],
    targets: List[str],
    timeout: int = R10K_DEPLOY_TIMEOUT,
) -> dict:
    """Stage/activate via OpenBolt on every code-deploy target.

    Compilers do not have ``/opt/openvox-gui``. ``bolt script run`` uploads
    ``r10k-stage-activate.sh`` and executes it as root on each target.

    This path must never raise into FastAPI — production uvicorn maps
    uncaught exceptions to a generic ``500 Internal Server Error`` with
    no detail (that is what the Code Deployment pane showed).
    """
    from ..routers.bolt_runtime import find_bolt, run_bolt_command
    from ..services.cluster_config import load_cluster_config

    try:
        env_args = _cluster_env_args(mode, environment)
    except ValueError as e:
        return _cluster_result(mode, environment, targets, False, 64, [str(e)], [])

    cfg = load_cluster_config()
    script = Path(STAGE_ACTIVATE_SCRIPT)
    if not script.is_file():
        msg = (
            f"Missing {STAGE_ACTIVATE_SCRIPT}. Run update_local.sh so the "
            "clustered stage/activate helper is installed on this console."
        )
        return _cluster_result(
            mode, environment, targets, False, 127, [msg],
            [{"host": t, "success": False, "via": "missing-script", "exit_code": 127} for t in targets],
        )

    bolt = find_bolt()
    local_names = _local_hostnames()
    targets_are_local = bool(targets) and all(t.lower() in local_names for t in targets)

    # Dedicated consoles are not compilers. Never silently r10k *this* host
    # when the targets are remote FQDNs and OpenBolt is missing from PATH.
    if not bolt and not targets_are_local:
        msg = (
            "OpenBolt is not installed (or not on PATH) on this console. "
            "Clustered Stage/Activate needs `bolt` plus SSH as bolt@ to each "
            "code-deploy target. Install OpenBolt and classify compilers with "
            "profiles::base::bolt_user."
        )
        return _cluster_result(
            mode, environment, targets, False, 127, [msg],
            [{"host": t, "success": False, "via": "no-bolt", "exit_code": 127} for t in targets],
        )

    if bolt and targets and not targets_are_local:
        # SSH probe + create Bolt tmpdir. OpenBolt script run does
        # `mkdir -m 700 $tmpdir/<uuid>` (no -p). /tmp is CIS noexec, so
        # inventory tmpdir is /home/bolt/.bolt/tmp — which does not exist
        # until bolt_user (or this install) creates it.
        probe_args = [
            "command", "run", _PREP_BOLT_TMPDIR,
            "--targets", ",".join(targets),
            "--run-as", "root",
            "--no-tty",
            "--connect-timeout", "8",
            "--no-host-key-check",
            "--format", "json",
        ]
        try:
            probe = await run_bolt_command(probe_args, timeout=_CLUSTER_SSH_PROBE_TIMEOUT)
        except Exception as e:
            logger.error("cluster %s SSH probe raised: %s", mode, e, exc_info=True)
            return _cluster_result(
                mode, environment, targets, False, 1,
                [
                    f"OpenBolt SSH probe raised: {e}",
                    "Check journalctl -u openvox-gui and that bolt@ can SSH to each compiler.",
                ],
                [{"host": t, "success": False, "via": "bolt-probe", "exit_code": -1} for t in targets],
            )
        probe_rc, probe_out, probe_hosts = _flatten_bolt_json(
            probe, targets, via="bolt-probe"
        )
        if probe_rc != 0:
            blob = "\n".join(probe_out)
            if "MISSING_R10K_YAML" in blob:
                hint = (
                    "r10k is installed but /etc/puppetlabs/r10k/r10k.yaml is "
                    "missing on one or more compilers. Copy the working file "
                    "from ovcompiler1.pdxc-it.corp.int-x.ai, or: "
                    "sudo /opt/openvox-gui/scripts/bootstrap-compiler.sh "
                    "--yaml /path/to/r10k.yaml"
                )
            elif "MISSING_R10K" in blob:
                hint = (
                    "r10k is not installed on one or more compilers. That is "
                    "why Stage spins with no log (one host deploys, the rest "
                    "die). On each compiler, or via bolt script run from the "
                    "console: sudo /opt/openvox-gui/scripts/bootstrap-compiler.sh"
                )
            else:
                hint = (
                    "OpenBolt cannot prepare the code-deploy targets as bolt@. "
                    "Classify those hosts with profiles::base::bolt_user (same "
                    "id_bolt.pub as this console) and retry Stage."
                )
            return _cluster_result(
                mode, environment, targets, False, probe_rc or 1,
                [hint, ""] + [ln for ln in probe_out if ln],
                probe_hosts or [
                    {"host": t, "success": False, "via": "bolt-probe", "exit_code": probe_rc}
                    for t in targets
                ],
            )

        # script run uploads the helper (compilers do not have /opt/openvox-gui).
        # --run-as root uses bolt@ passwordless sudo once bolt_user is applied.
        # --format json is required: human format hides script stderr behind
        # "The command failed with exit code 1".
        # run_bolt_command appends -i / --project after these args.
        script_args = [
            "script", "run", str(script),
            *env_args,
            "--targets", ",".join(targets),
            "--run-as", "root",
            "--no-tty",
            "--connect-timeout", "15",
            "--no-host-key-check",
            "--format", "json",
        ]
        try:
            result = await run_bolt_command(script_args, timeout=timeout)
        except Exception as e:
            logger.error("cluster %s bolt script run raised: %s", mode, e, exc_info=True)
            return _cluster_result(
                mode, environment, targets, False, 1,
                [f"OpenBolt {mode} raised: {e}"],
                [{"host": t, "success": False, "via": "bolt", "exit_code": -1} for t in targets],
            )
        rc, out, hosts = _flatten_bolt_json(result, targets, via="bolt")
        # Inventory tty:true used to return COMMAND_ERROR with empty
        # stdout/stderr. If the helper logged to disk, pull that.
        if rc != 0 and not any("r10k-stage-activate.sh:" in (ln or "") for ln in out):
            log_args = [
                "command", "run", "cat /var/tmp/r10k-stage-activate.log",
                "--targets", ",".join(targets),
                "--run-as", "root",
                "--no-tty",
                "--connect-timeout", "8",
                "--no-host-key-check",
                "--format", "json",
            ]
            try:
                fetched = await run_bolt_command(log_args, timeout=25)
                _, log_lines, _ = _flatten_bolt_json(
                    fetched, targets, via="stage-log"
                )
                out = list(out) + ["── /var/tmp/r10k-stage-activate.log ──"] + log_lines
            except Exception as e:
                logger.warning("cluster %s could not fetch stage log: %s", mode, e)
        return _cluster_result(
            mode, environment, targets, rc == 0, 0 if rc == 0 else 1,
            out,
            hosts,
        )

    # Local-only target (console is also the compiler): run the helper here.
    staging = cfg.get("staging_codedir", "/etc/puppetlabs/code-staging")
    live = cfg.get("live_codedir", "/etc/puppetlabs/code")
    env_prefix = f"OPENVOX_STAGING_CODEDIR={staging} OPENVOX_LIVE_CODEDIR={live} "
    result = await run_sudo(
        ["sudo", "bash", "-c", f"{env_prefix}{script} {' '.join(env_args)}"],
        timeout=timeout,
    )
    rc = result.get("returncode")
    rc = -1 if rc is None else int(rc)
    out = ((result.get("stdout") or "") + "\n" + (result.get("stderr") or "")).splitlines()
    host_label = targets[0] if targets else "local"
    return _cluster_result(
        mode, environment, targets, rc == 0, 0 if rc == 0 else 1,
        [ln for ln in out if ln is not None],
        [{"host": host_label, "success": rc == 0, "via": "local", "exit_code": rc}],
    )


async def _cluster_deploy(kind: str, deploy: ClusterDeployRequest, current_user: str) -> dict:
    """Shared stage/activate entry: validate, run, audit, never leak 500."""
    from ..services.cluster_config import is_clustered, deploy_targets
    from ..utils.audit import audit_event

    if not is_clustered():
        raise HTTPException(
            status_code=400,
            detail="Clustered deployment mode is not enabled. Enable it under Settings → Application → Cluster.",
        )
    targets = deploy.targets or deploy_targets()
    if not targets:
        raise HTTPException(status_code=400, detail="No code_deploy_targets configured")
    try:
        result = await _run_on_targets(kind, deploy.environment, targets)
    except Exception as e:
        logger.error("cluster %s failed: %s", kind, e, exc_info=True)
        result = _cluster_result(
            kind, deploy.environment, targets, False, 1,
            [
                f"Cluster {kind} failed: {e}",
                "See journalctl -u openvox-gui for the traceback.",
            ],
            [{"host": t, "success": False, "via": "error", "exit_code": -1} for t in targets],
        )
    audit_event(
        f"deploy_{kind}",
        user=current_user,
        targets=",".join(targets),
        detail=deploy.environment or "all",
        rc=result["exit_code"],
        success=result["success"],
    )
    return result


@router.post("/stage")
@rate_limit_heavy()
async def stage_deployment(
    deploy: ClusterDeployRequest,
    request: Request,
    current_user: str = Depends(require_role("admin", "operator")),
    _=Depends(concurrency_heavy),
):
    """Stage r10k deploy to staging codedir on all cluster deploy targets."""
    return await _cluster_deploy("stage", deploy, current_user)


@router.post("/activate")
@rate_limit_heavy()
async def activate_deployment(
    deploy: ClusterDeployRequest,
    request: Request,
    current_user: str = Depends(require_role("admin", "operator")),
    _=Depends(concurrency_heavy),
):
    """Promote staged code to live codedir on all cluster deploy targets."""
    return await _cluster_deploy("activate", deploy, current_user)


# ─── Deploy History (JSON via services.deploy_history; srdev2 A6) ──
from ..services.deploy_history import (

    add_json_history_entry as _add_history_entry,
    load_json_history as _load_history,
)


@router.get("/history")
async def get_deploy_history():
    """Get deployment history (JSON file; also dual-written to execution_history on run)."""
    return {"history": _load_history()}


# Basic Prometheus-style /metrics (actionable #9, P2 from srsysarch1).
# Exposes a few key operational values in exposition format.
# Extend with real counters as needed.
@router.get("/metrics", response_class=PlainTextResponse)
async def ops_metrics():
    from ..utils.maintenance import get_maintenance_info
    maint = get_maintenance_info()
    maint_enabled = "1" if maint.get("enabled") else "0"
    lines = [
        "# HELP openvox_gui_maintenance_active 1 if maintenance mode is active",
        "# TYPE openvox_gui_maintenance_active gauge",
        f"openvox_gui_maintenance_active {maint_enabled}",
        "# HELP openvox_gui_last_deploy_timestamp Unix time of last known deploy (best effort from history)",
        "# TYPE openvox_gui_last_deploy_timestamp gauge",
    ]
    if maint.get("message"):
        # Simple text metric for current maintenance reason (can be extended to labels).
        lines.append(f'# Maintenance message: {maint["message"]}')
    try:
        hist = _load_history()
        if hist:
            ts = hist[0].get("timestamp")
            if ts:
                from datetime import datetime
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                lines.append(f"openvox_gui_last_deploy_timestamp {dt.timestamp()}")
    except Exception:
        pass
    # Add more (ps health, mirror age, sqlite rows) in follow-up.
    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain")
