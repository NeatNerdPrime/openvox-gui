# OpenVox GUI — Project status (release readiness)

**As of:** 2026-08-14  
**Branch:** `main`  
**VERSION file:** `3.12.0-rc.14`
**Last stable GitHub Release:** **3.10.6** (still recommended for production AIO unless you opt into 3.12-rc)

This document freezes **where we are** after the 3.12 clustering/VIP/ovox week, so Monday’s **roles/profiles** work starts from a clean map. It covers **all-in-one (AIO)** and **clustered** installs.

---

## 1. Product intent (do not lose this)

| Audience | Path |
|----------|------|
| **Most users** | **All-in-one:** GUI on the OpenVox Server host (SQLite OK, local puppetserver/CA/PDB/Bolt) |
| **Large / multi-DC** | **Clustered:** dedicated console(s), compilers, CA HA, OpenVoxDB mesh, shared Postgres `openvox_gui` |

**AIO remains the primary install path** in INSTALL, Quick Start, and installer defaults. Clustering is documented and functional for early production **by intent**, not yet a “stable 3.12.0” GitHub Release.

---

## 2. Version line

| Line | Status | Notes |
|------|--------|--------|
| **3.10.6** | Stable | Last published GitHub Release; fine for classic AIO |
| **3.11.x** | Historical beta | Clustered console foundations |
| **3.12.0-rc.N** | Active pre-release on `main` | VIP sessions, fleet exclude, ovox clustered infra, Bolt estate inventory, docs |

Pre-release labels must be PEP 440 (`rc` / `a` / `b` / `dev`). Do **not** use `gamma` in `VERSION` (pip rejects it).

**ovox** is version-locked to the GUI via root `VERSION` + `scripts/bump-version.sh`.

---

## 3. What shipped in the 3.12.0-rc train (summary)

### Dual-console / VIP
- Session gate (no hard reload on 401)
- Denylist fail-open on DB blips
- JWT ≥4h floor, sliding renew
- `access_mode` vip|direct + VIP poll floor
- Console footer: hostname + IP (`/api/version`)
- Cluster fields: `vip_hosts`, `infra_vips`, `fleet_exclude`

### Fleet / Nodes
- Live fleet = active PDB ∩ signed CA − fleet exclusions  
- VIP LB names (e.g. `ovcompilers.*`) excluded when listed in cluster config / env  
- Status badge = newest OpenVoxDB **report** `status` (not CA)

### Log Viewer
- Empty remote logs → **200** + message, not 502 “no log JSON”
- Bolt + journalctl/tail fallback

### PQL
- Sortable OpsTable result columns

### ovox / infra (clustered)
- `ovox infra health` → full estate members **and** VIPs via HTTP probes  
- Estate inventory from **cluster_config + OPENVOX_GUI_*** (not PuppetDB Bolt plugin inventory)  
- Bolt inventory written under `/opt/openvox-gui/data/` **644**, readable by user `bolt`  
- `ovox infra settings show` samples remote conf via Bolt when local conf missing  
- Local tune **apply** refused on clustered console (would only mutate GUI host)  
- Proxy bypass for internal GUI URLs (avoid 407)

### Known gaps (not done)
- **Remote tune apply** to every compiler/ovdb via Bolt  
- **Puppet roles/profiles** for compiler / CA / PDB / console auto-join (**Monday**)  
- Full **pip-audit** in CI (unpinned ranges; local audit blocked by psycopg2 build env)  
- Promote **3.12.0** stable GitHub Release (deliberate later)

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
Infra: local files + local systemd; `ovox infra *` works on-box.

### Clustered (multi-server)

```text
[ Console openvox.pdxc / openvox.atlc ]
  openvox-gui + ovox
  Postgres openvox_gui (shared) + same SECRET_KEY
  cluster_config.json (members + VIPs)
  Bolt SSH → estate (generated inventory)

[ Compilers ]  reports=store,puppetdb → PDB VIP; termini; no CA admin
[ CA HA ]      Pacemaker+DRBD; pcs owns puppetserver; auth.conf cert-status allow
[ OpenVoxDB ]  mesh / VIP; not termini clients
```

Compilers need `reports` under **`[server]`**. CA-only: **no** `reports=store,puppetdb`, **no** facts→puppetdb terminus.

---

## 5. Documentation map (post-tidy)

| Doc | Role |
|-----|------|
| [INSTALL.md](../INSTALL.md) | **AIO first**; clustered in advanced section |
| [UPDATE.md](../UPDATE.md) | Clone-then-deploy |
| [FEATURES.md](FEATURES.md) | Page/API inventory |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Single vs clustered |
| [STATUS.md](STATUS.md) | **This file** — where we are |
| [VIP_SESSIONS.md](VIP_SESSIONS.md) | Dual console sessions |
| [CLUSTERED_SHARED_DB.txt](CLUSTERED_SHARED_DB.txt) | Shared GUI DB |
| [TROUBLESHOOTING.md](../TROUBLESHOOTING.md) | Ops failures |
| [SECURITY.md](../SECURITY.md) | Support matrix + reporting |
| [TUNING.md](TUNING.md) | ovox infra (AIO + clustered notes) |

---

## 6. Security scan (2026-08-14)

| Check | Result |
|-------|--------|
| **npm audit** (frontend) | **0 vulnerabilities** after `nanoid` → ≥3.3.16 (was GHSA-28wg-ghj8-5hjv high) |
| **pip-audit** (backend) | Incomplete in this environment (psycopg2 build / unpinned ranges). **Action:** pin/hash requirements in CI and run `pip-audit` there before stable 3.12.0 |
| **Secret pattern scan** | No hard-coded secrets found in tree (rotate any proxy passwords that appeared in ops chat) |
| **CVE badge** | Reflects npm clean; Python deps need CI gate before claiming zero CVEs for backend |

**Note:** `react-router@8` wants Node ≥22 in engines; builds still run on Node 20 for now. Track before forcing Node 22 in install docs.

### Operator hygiene
- Never commit `.env`, bolt tokens, or proxy passwords  
- Dual console: identical `OPENVOX_GUI_SECRET_KEY` + shared `openvox_gui` DB  
- CA `auth.conf`: compilers must **not** get certificate_statuses allow  

---

## 7. Release checklist (AIO + clustered)

### All-in-one smoke
- [ ] Fresh `install.sh` on lab server  
- [ ] Login, Dashboard, Nodes, one PQL, one cert list  
- [ ] `ovox infra health` / `settings show` (local values present)  
- [ ] Agent run → report appears in GUI  
- [ ] Package mirror optional  

### Clustered smoke
- [ ] Same VERSION on all consoles  
- [ ] `cluster_config` members **and** VIPs filled  
- [ ] `ovox infra health` lists each compiler/ovdb/CA member + VIP  
- [ ] Bolt estate inventory readable by user `bolt` (644)  
- [ ] `ovox infra settings show` shows `source: bolt` + host or clear warnings  
- [ ] VIP login stable ≥ session floor; direct FQDN still OK  
- [ ] Fleet exclude hides `ovcompilers.*` etc.  
- [ ] Log Viewer empty host → 200 not 502  

### Before GitHub Release 3.12.0
- [ ] CI pip-audit + npm audit green  
- [ ] CHANGELOG stable section  
- [ ] Press kit `docs/releases/press_3.12.0.md`  
- [ ] Tag `v3.12.0` only (not auto-release from every rc)  

---

## 8. Monday backlog (roles / profiles)

Agreed approach: **roles** composed of **`profile::base` + technology profiles**.

| Role (working names) | Profiles (illustrative) |
|----------------------|-------------------------|
| `role::openvox::compiler` | base, server, pdb_client (termini+reports), r10k, bolt_target |
| `role::openvox::puppetdb` | base, openvoxdb, postgres client / spock join (plan) |
| `role::openvox::ca` | base, ca packages, pcs/drbd (plan for join) |
| `role::openvox::console` | base, openvox_gui, bolt, cluster_config from Hiera |

**Day 0 bootstrap** (first CA / first PDB / VIPs) stays checklist + Bolt plans.  
**Day N scale-out:** classify + agent run (+ optional join plan).

Estate map in Hiera should feed **both** Puppet and GUI `cluster_config.json`.

---

## 9. Ops truth (from this week — keep)

1. Node **Failed** = newest **OpenVoxDB report** status, not CA.  
2. Report processors = **compilers** `[server] reports = store,puppetdb`.  
3. CA-only: no termini, no PDB reports line.  
4. `NO_PROXY` suffixes for internal domains; **systemd** for puppetserver, not only profile.d.  
5. Dual console badge disagreement with same PQL → check **live_run** overlay vs PDB.  
6. pcs CA restart via **Pacemaker**, not bare systemctl on Promoted stack.  

---

*Update this file whenever the pre-release train theme changes or 3.12.0 stable is cut.*
