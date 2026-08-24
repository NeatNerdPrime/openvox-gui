#!/usr/bin/env python3
"""
External Node Classifier (ENC) script for Puppet.

This script is called by PuppetServer for each node during catalog compilation.
It queries the OpenVox GUI API to get the node's classification and outputs
YAML that Puppet understands.

Usage in puppet.conf (on **compilers**, not dedicated consoles):
    [server]
    node_terminus = exec
    external_nodes = /usr/local/bin/enc.py

Install path:
    Package/source copy: /opt/openvox-gui/scripts/enc.py (on the GUI console)
    Runtime on compilers: /usr/local/bin/enc.py (via bootstrap-compiler-enc.sh)

The script expects the certname as the first argument.

Environment variables (must be set for the **puppetserver** process):
    OPENVOX_GUI_API_BASE - One URL, or comma-separated URLs tried in order
      (first HTTP 200 wins). Prefer /etc/sysconfig/openvox-enc + systemd
      EnvironmentFile on puppetserver — shell exports alone are not enough.
      Multi-console without shared Postgres: put the console that holds
      classification FIRST (split SQLite is not failover).
      Example (ATLC has ENC data, PDXC may be empty):
        https://openvox.atlc-it.corp.int-x.ai:4567,https://openvox.pdxc-it.corp.int-x.ai:4567
      Default if unset: https://localhost:4567
    OPENVOX_GUI_ENC_CA - CA bundle (default: puppet localcacert, then
      /etc/puppetlabs/puppet/ssl/certs/ca.pem). Used to verify the GUI.
    OPENVOX_GUI_ENC_TLS_VERIFY - default on. Set 0/false/off to restore
      CERT_NONE. localhost / 127.0.0.1 skip hostname check only (still
      verify the chain when a CA file exists).
"""
import os
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

import yaml


def _api_bases() -> list:
    raw = os.environ.get("OPENVOX_GUI_API_BASE", "https://localhost:4567")
    return [u.strip().rstrip("/") for u in raw.split(",") if u.strip()]


API_BASES = _api_bases()


def _truthy_off(raw: str) -> bool:
    return raw.strip().lower() in ("0", "false", "off", "no")


def _puppet_localcacert() -> str:
    env = os.environ.get("OPENVOX_GUI_ENC_CA", "").strip()
    if env and os.path.isfile(env):
        return env
    try:
        out = subprocess.check_output(
            ["/opt/puppetlabs/bin/puppet", "config", "print", "localcacert"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        ).strip()
        if out and os.path.isfile(out):
            return out
    except (OSError, subprocess.SubprocessError):
        pass
    fallback = "/etc/puppetlabs/puppet/ssl/certs/ca.pem"
    return fallback if os.path.isfile(fallback) else ""


def _ssl_context(url: str) -> ssl.SSLContext:
    """Verify the GUI with the Puppet CA. Hostname check unless loopback."""
    if _truthy_off(os.environ.get("OPENVOX_GUI_ENC_TLS_VERIFY", "1")):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    host = (urllib.parse.urlparse(url).hostname or "").lower()
    loopback = host in ("localhost", "127.0.0.1", "::1")
    cafile = _puppet_localcacert()
    if not cafile:
        print(
            "ENC TLS: no Puppet CA file; cannot verify GUI cert",
            file=sys.stderr,
        )
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    ctx = ssl.create_default_context(cafile=cafile)
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.check_hostname = not loopback
    return ctx


def classify_node(certname: str) -> str:
    """Query the OpenVox GUI API for node classification.

    Tries each OPENVOX_GUI_API_BASE URL (comma-separated). Both clustered
    consoles must serve the same ENC (shared PostgreSQL). Failover is for
    console outage, not split-brain.
    """
    last_err = None
    for base in API_BASES:
        url = f"{base}/api/enc/classify/{certname}/yaml"
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10, context=_ssl_context(base)) as response:
                return response.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return yaml.dump({
                    "environment": "production",
                    "classes": {},
                    "parameters": {},
                }, default_flow_style=False)
            last_err = e
            print(f"ENC API {url} HTTP {e.code}", file=sys.stderr)
        except Exception as e:
            last_err = e
            print(f"ENC API {url} failed: {e}", file=sys.stderr)
    print(f"Error connecting to ENC API (tried {API_BASES}): {last_err}", file=sys.stderr)
    return yaml.dump({
        "environment": "production",
        "classes": {},
        "parameters": {},
    }, default_flow_style=False)


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <certname>", file=sys.stderr)
        sys.exit(1)

    certname = sys.argv[1]
    result = classify_node(certname)
    print(result)


if __name__ == "__main__":
    main()
