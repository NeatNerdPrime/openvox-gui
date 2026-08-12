# Compiler ENC setup (Classification → catalogs)

OpenVox GUI stores classification (Common → Environment → Groups → Node).
**Catalog compilers** load that classification at compile time via an
external node classifier (`enc.py`). Dedicated GUI consoles do **not**
compile agent catalogs; they only serve the classify API.

If Classification looks correct in the UI but agents get empty catalogs,
the gap is almost always on the **compiler**, not the console curl.

## What every catalog compiler must have

| Piece | Path / setting | Why |
|-------|----------------|-----|
| ENC script | **`/usr/local/bin/enc.py`** | `external_nodes` runtime (not the console package tree) |
| API base env | **`/etc/sysconfig/openvox-enc`** | `OPENVOX_GUI_API_BASE=…` for the **puppetserver** process |
| systemd drop-in | `/etc/systemd/system/puppetserver.service.d/openvox-enc.conf` | Loads the sysconfig (`EnvironmentFile=-…`) |
| puppet.conf `[server]` | `node_terminus = exec` | Use external ENC |
| puppet.conf `[server]` | `external_nodes = /usr/local/bin/enc.py` | Path must match the installed script |
| Live code | `/etc/puppetlabs/code/environments/<env>/…` | Classes named in ENC must exist (Stage/Activate) |

Package/source copy on the **console** (for Bolt upload):

- `/opt/openvox-gui/scripts/enc.py`
- `/opt/openvox-gui/scripts/bootstrap-compiler-enc.sh`
- `/opt/openvox-gui/scripts/bootstrap-compiler.sh`

## One-shot install (recommended)

From a console after `bolt@` works on the compilers:

```bash
sudo -u bolt bolt script run /opt/openvox-gui/scripts/bootstrap-compiler-enc.sh \
  --targets ovcompiler1.example.com,ovcompiler2.example.com \
  --run-as root --no-tty --project /etc/puppetlabs/bolt -- \
  --api-base 'https://openvox.site-with-data.example.com:4567,https://openvox.other.example.com:4567' \
  --enc-src /opt/openvox-gui/scripts/enc.py \
  --force --restart
```

Or fold into first-install r10k bootstrap:

```bash
sudo -u bolt bolt script run /opt/openvox-gui/scripts/bootstrap-compiler.sh \
  --targets <compilers> --run-as root --no-tty --project /etc/puppetlabs/bolt -- \
  --enc-api-base 'https://openvox.site-with-data.example.com:4567,...' \
  --enc-src /opt/openvox-gui/scripts/enc.py
```

`install.sh` on a **co-located** single-server host (GUI + puppetserver)
runs the same ENC bootstrap when `CONFIGURE_ENC=auto|true` and local
puppetserver is detected. Dedicated consoles should leave
`CONFIGURE_ENC=false` (or auto will skip) and push ENC to compilers.

## Manual layout (if not using the bootstrap script)

```bash
# 1. Script
install -m 0755 /opt/openvox-gui/scripts/enc.py /usr/local/bin/enc.py

# 2. Env for puppetserver (not only your shell)
cat > /etc/sysconfig/openvox-enc <<'EOF'
OPENVOX_GUI_API_BASE=https://openvox.site-with-data.example.com:4567,https://openvox.other.example.com:4567
EOF
chmod 644 /etc/sysconfig/openvox-enc

# 3. Drop-in
mkdir -p /etc/systemd/system/puppetserver.service.d
cat > /etc/systemd/system/puppetserver.service.d/openvox-enc.conf <<'EOF'
[Service]
EnvironmentFile=-/etc/sysconfig/openvox-enc
EOF

# 4. puppet.conf [server]
#    node_terminus = exec
#    external_nodes = /usr/local/bin/enc.py

systemctl daemon-reload
systemctl restart puppetserver
```

Example sysconfig template: `etc/openvox-enc.sysconfig.example` in the
package (copy to `/etc/sysconfig/openvox-enc` and edit).

## Multi-console and split SQLite

Each console’s default database is its **own** SQLite file
(`/opt/openvox-gui/data/openvox_gui.db`) unless you configure shared
Postgres (`OPENVOX_GUI_DATABASE_URL`).

- Classification saved on console **A** is **not** visible on console **B**.
- `enc.py` tries `OPENVOX_GUI_API_BASE` URLs **in order**; the **first HTTP 200**
  wins — including a 200 with empty `classes: {}`.
- Until both GUIs share one ENC database, put the console that **has**
  the data **first** in `OPENVOX_GUI_API_BASE`.

```bash
# Verify per console (do not assume failover order)
curl -sk "https://openvox.atlc.example.com:4567/api/enc/classify/<certname>/yaml"
curl -sk "https://openvox.pdxc.example.com:4567/api/enc/classify/<certname>/yaml"
```

Ideal long-term: one Postgres `openvox_gui` for both consoles so either
URL returns the same classification.

## Smoke tests

```bash
# On a compiler — same env puppetserver should load
set -a; . /etc/sysconfig/openvox-enc; set +a
/usr/local/bin/enc.py <agent-certname>
# Expect: classes: and parameters: matching Classification UI

systemctl show puppetserver -p EnvironmentFiles
grep -E 'node_terminus|external_nodes' /etc/puppetlabs/puppet/puppet.conf

# On the agent
puppet config print server ca_server   # server = compiler VIP
sudo puppet agent -t
```

Empty agent catalogs with a good ENC smoke test → check that
`profiles::…` (or whatever class ENC names) exists under the live
environment on the **compiler** (Stage/Activate).

## install.conf knobs

```bash
# Compiler VIP for class discovery / metrics (not necessarily this host)
PUPPET_SERVER_HOST="compile.example.com"
# CA VIP when console is not the CA
# PUPPET_CA_HOST="ovca.example.com"

# auto | true | false — wire local ENC when puppetserver is on this host
CONFIGURE_ENC="auto"
# Comma-separated; primary classification console FIRST without shared DB
# ENC_API_BASE="https://openvox.site1.example.com:4567,https://openvox.site2.example.com:4567"
```

## Related

- `scripts/bootstrap-compiler-enc.sh` — ENC only  
- `scripts/bootstrap-compiler.sh --enc-api-base` — r10k + optional ENC  
- `scripts/list-classes-remote.py` / `hiera-list-remote.py` — console→compiler Bolt helpers  
- TROUBLESHOOTING.md — “Compilers ignore ENC classes”, empty Common Classes  
