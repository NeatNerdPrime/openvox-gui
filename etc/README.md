# Operator-managed config snippets (`/opt/openvox-gui/etc/`)

Files deployed as **examples only** (deploy does not overwrite live operator files):

| Example | Live path | Purpose |
|---------|-----------|---------|
| `allowed-environments.txt.example` | `allowed-environments.txt` | Optional strict r10k environment allow-list |
| `installer-ip-allowlist.txt.example` | `installer-ip-allowlist.txt` | Optional IP/CIDR allow-list for agent install scripts on :4567 |
| `openvox-enc.sysconfig.example` | **`/etc/sysconfig/openvox-enc`** (on **compilers**) | `OPENVOX_GUI_API_BASE` for puppetserver + `enc.py` |

**Compiler ENC** (not optional if you use Classification): install
`/usr/local/bin/enc.py`, load the sysconfig via a puppetserver
`EnvironmentFile` drop-in, set `node_terminus=exec`. Prefer
`scripts/bootstrap-compiler-enc.sh` — see **`docs/COMPILER_ENC.md`**.

Also see env vars: `OPENVOX_GUI_BOOTSTRAP_TOKEN`, `OPENVOX_GUI_INSTALLER_IP_ALLOWLIST`.

Package mirror sync remains **root** via `scripts/sync-openvox-repo.sh` (write + chown). A dedicated least-priv sync user is deferred; use firewall + token/IP allowlist for the installer script surface in the meantime.
