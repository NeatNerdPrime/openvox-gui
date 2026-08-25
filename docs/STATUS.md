# OpenVox GUI — Project status (3.12.0)

**As of:** 2026-08-25  
**Branch:** `main`  
**VERSION file:** `3.12.0`  
**Current stable GitHub Release:** **3.12.0** (`v3.12.0`)

This file is the operator map after the 3.12 clustering / VIP / fleet-status
train was promoted to stable.

---

## 1. Product intent

| Audience | Path |
|----------|------|
| **Most users** | **All-in-one:** GUI on the OpenVox Server host (SQLite OK, local puppetserver/CA/PDB/Bolt) |
| **Large / multi-DC** | **Clustered:** dedicated console(s), compilers, CA HA, OpenVoxDB mesh, shared Postgres `openvox_gui` |

**AIO remains the primary install path** in INSTALL, Quick Start, and installer
defaults. Clustering is documented and supported in 3.12.0.

---

## 2. Version line

| Line | Status | Notes |
|------|--------|--------|
| **3.12.0** | **Stable** | Current GitHub Release. AIO + clustered. |
| **3.10.6** | Prior stable | Fine for classic AIO if you are not ready to upgrade |
| **3.11.x** | Historical beta | Clustered console foundations; prefer 3.12.0 |
| **3.12.0-rc.N** | Promoted | Audit trail stays in CHANGELOG |

Pre-release labels must be PEP 440 (`rc` / `a` / `b` / `dev`). Do **not** use
`gamma` in `VERSION` (pip rejects it).

**ovox** is version-locked to the GUI via root `VERSION` + `scripts/bump-version.sh`.

---

## 3. What 3.12.0 ships

### Dual-console / VIP
- Session gate (no hard reload on 401)
- Denylist fail-open on DB blips
- JWT ≥4h floor, sliding renew
- `access_mode` vip|direct + VIP poll floor
- Console footer: hostname + IP (`/api/version`)
- Cluster fields: `vip_hosts`, `infra_vips`, `fleet_exclude`

### Fleet / Nodes / Overview
- Live fleet = active PDB `/nodes` − DNS RR names only (`ovcompilers.*` stay)
- Status badge = newest OpenVoxDB **report** `status` (not CA, not aged to Unreported)
- Overview, Nodes, Node Detail, Monitoring, Heatmap, and Environments share
  that census (including Bolt live-run overlay)
- Newest reports are **merged from peer OpenVoxDBs** so two consoles do not
  disagree when each VIP stored a different last report
- Needs attention = failed, unreported, or last report older than 24h
  (same rule on Dashboard and Nodes `?status=attention`)

### Clustered data plane
- `cluster-preflight.sh` refuses `/etc/hosts` pins of the PDB VIP
- `ensure-puppetdb-spock.sh` grants `pg_replication_origin_*` on database **puppetdb**
- `bootstrap-openvox-gui-db.sh` provisions database **openvox_gui** (separate mesh)
- ENC HTTPS verifies the console cert against the Puppet CA
- Compilers: `[server] reports = puppetdb` and site-local `server_urls`

### Log Viewer / PQL / ovox
- Empty remote logs → **200** + message, not 502
- Sortable PQL result columns
- `ovox infra health` probes estate members **and** VIPs
- Bolt estate inventory under `/opt/openvox-gui/data/` **644**

### Known gaps (not 3.12.0 blockers)
- Remote tune apply to every compiler/ovdb via Bolt
- Classify live compilers with `roles::catalog_compiler` (profile exists; production classify not confirmed)
- Dual-console **same** `OPENVOX_GUI_SECRET_KEY` + `openvox_gui` DSN is an ops requirement, not a code fix

---

## 4. Architecture cheat sheet

### All-in-one (default)

```text
[ OpenVox Server host ]
  puppetserver + CA + agent
  openvoxdb (optional co-located)
  openvox-gui + ovox
  SQLite openvox_gui.db  OR  local Postgres openvox_gui
  Bolt local + inventory
```

Install: `sudo ./install.sh` on the server.

### Clustered (multi-server)

```text
[ Console openvox.site-a / openvox.site-b ]
  openvox-gui + ovox
  Postgres openvox_gui (shared) + same SECRET_KEY
  cluster_config.json (members + VIPs)
  Bolt SSH → estate

[ Compilers ]  CA-off; termini → site ovdb1,ovdb2; reports = puppetdb
[ CA HA ]      Pacemaker+DRBD
[ OpenVoxDB ]  Spock mesh / site HAProxy
```

See [CLUSTERED_SHARED_DB.txt](CLUSTERED_SHARED_DB.txt).

---

## 5. Documentation map

| Doc | Role |
|-----|------|
| [INSTALL.md](../INSTALL.md) | **AIO first**; clustered in advanced section |
| [UPDATE.md](../UPDATE.md) | Clone-then-deploy |
| [FEATURES.md](FEATURES.md) | Page/API inventory |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Single vs clustered |
| [STATUS.md](STATUS.md) | **This file** |
| [VIP_SESSIONS.md](VIP_SESSIONS.md) | Dual console sessions |
| [CLUSTERED_SHARED_DB.txt](CLUSTERED_SHARED_DB.txt) | Two DBs, two Spock meshes |
| [ESTATE_HEALTH.md](ESTATE_HEALTH.md) | Post-install checks |
| [TROUBLESHOOTING.md](../TROUBLESHOOTING.md) | Ops failures |
| [SECURITY.md](../SECURITY.md) | Support matrix |
| [TUNING.md](TUNING.md) | ovox infra |

---

## 6. Ops truth

1. Node **Failed** = newest **OpenVoxDB report** status, not CA.
2. Report processors = **compilers** `[server] reports = puppetdb`.
3. CA-only: no termini, no PDB reports line.
4. Dual-console Overview must merge peer reports (`OPENVOX_GUI_PUPPETDB_PEERS` or cluster consoles).
5. **Two databases:** `puppetdb` vs `openvox_gui`. CREATE DATABASE does not follow the other mesh.
6. `/nodes` follows **catalogs**. Never `INSERT` fleet stubs; never `sub_resync_table` on `certnames`.
7. Same `SECRET_KEY` on every console or LDAP decrypts on one site only.

---

*Update this file when the next train starts or a new stable is cut.*
