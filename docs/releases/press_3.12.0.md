# openvox-gui 3.12.0 -- Announcement Copy

> **Release:** v3.12.0 (stable) -- Clustered consoles, one fleet status, AIO still first.
> **Generated:** 2026-08-25
> **Canonical URLs:**
> - Repo: https://github.com/cvquesty/openvox-gui
> - Latest release: https://github.com/cvquesty/openvox-gui/releases/latest
> - v3.12.0: https://github.com/cvquesty/openvox-gui/releases/tag/v3.12.0
> - Status: https://github.com/cvquesty/openvox-gui/blob/main/docs/STATUS.md
> - Upgrade: https://github.com/cvquesty/openvox-gui/blob/main/UPDATE.md
> - Changelog: https://github.com/cvquesty/openvox-gui/blob/main/CHANGELOG.md

## How to use this file

Copy platform sections as needed. Pre-release train detail (`3.12.0-rc.N`) stays in CHANGELOG; public copy leads with user outcomes.

| # | Platform | Length | Tone |
|---|----------|--------|------|
| 1 | GitHub Release / Discussions | Long | Formal |
| 2 | VoxPupuli Connect | Medium | Conversational |
| 3 | Slack | Short | Casual |

---

## 1. GitHub Release / Discussions

### Title

```
openvox-gui 3.12.0 -- Clustered consoles and one fleet status
```

### Body

````markdown
# openvox-gui 3.12.0 is out

Stable **v3.12.0** is on [Releases](https://github.com/cvquesty/openvox-gui/releases/latest) — promoting the **3.12.0-rc** train on `main` after lab validation of dual-console sessions, live-fleet membership, and Overview status that matches OpenVoxDB.

## Highlights

- **One fleet census.** Overview, Nodes, Node Detail, Monitoring, Heatmap, and Environments share the same live PuppetDB list. The badge is the newest OpenVoxDB report status — a day-old Unchanged stay Unchanged. Needs attention still flags failed, unreported, or reports older than 24 hours.
- **Two consoles, one picture.** Newest reports are merged from peer OpenVoxDBs so Needs attention does not show six stale nodes on one site and none on the other.
- **Clustered optional.** Dedicated consoles, VIP-safe sessions, shared Postgres `openvox_gui`, ENC TLS against the Puppet CA, ovox estate health, Bolt inventory. All-in-one on the OpenVox Server remains the default install.
- **Also** — Log Viewer empty≠502, sortable PQL, Run OpenVox treats exit 2 as success, clustered Code Deploy, LDAP/session polish.

## Upgrading

```bash
sudo /opt/openvox-gui/scripts/update_local.sh
```

Or remote deploy via `scripts/update_remote.sh`. After upgrade:

1. Hard-refresh browsers once.
2. Dual-console: identical `OPENVOX_GUI_SECRET_KEY` and `OPENVOX_GUI_DATABASE_URL`.
3. Compilers: `[server] reports = puppetdb`. Point writes at site `ovdb1`,`ovdb2`, not the dual-A name.

Details: [UPDATE.md](https://github.com/cvquesty/openvox-gui/blob/main/UPDATE.md) · [STATUS.md](https://github.com/cvquesty/openvox-gui/blob/main/docs/STATUS.md) · [CLUSTERED_SHARED_DB.txt](https://github.com/cvquesty/openvox-gui/blob/main/docs/CLUSTERED_SHARED_DB.txt).

Full notes: [v3.12.0](https://github.com/cvquesty/openvox-gui/releases/tag/v3.12.0) · [CHANGELOG](https://github.com/cvquesty/openvox-gui/blob/main/CHANGELOG.md).

Issues and PRs welcome.
````

---

## 2. VoxPupuli Connect (Discourse)

### Title

```
[Release] openvox-gui 3.12.0 -- clustered consoles, one fleet status
```

### Body

```markdown
**openvox-gui 3.12.0** is out. Overview now shows the newest OpenVoxDB report on every page, dual consoles merge peer reports so Needs attention matches, and clustered install is documented while AIO stays the default path.

Repo + release notes: https://github.com/cvquesty/openvox-gui/releases/latest
```

---

## 3. VoxPupuli Slack

```
*openvox-gui 3.12.0 is out* -- clustered consoles and one fleet status (newest OpenVoxDB report everywhere; peer merge so two sites don't disagree).

Releases: https://github.com/cvquesty/openvox-gui/releases/latest
```

---

## 4. Reddit r/sysadmin / r/Puppet

### Title

```
[Release] openvox-gui 3.12.0 -- web GUI for OpenVox with clustered consoles
```

### Body

````markdown
Maintainer here. Just cut [openvox-gui](https://github.com/cvquesty/openvox-gui) 3.12.0 — the Apache-2.0 web GUI for OpenVox (the community Puppet fork).

This train adds optional dedicated consoles (VIP sessions, shared Postgres ENC, peer OpenVoxDB report merge) while keeping the all-in-one install as the default. Overview / Nodes / Monitoring now share one newest-report badge so a node doesn't flip Unreported on the dashboard and Unchanged on the detail page.

Repo: https://github.com/cvquesty/openvox-gui
````

---

## 5. Mastodon

```
openvox-gui 3.12.0 shipped. Clustered consoles are optional; all-in-one stays the default. Overview now shows the newest OpenVoxDB report everywhere, including across two site consoles.

https://github.com/cvquesty/openvox-gui/releases/latest

#OpenVox #Puppet #DevOps #SysAdmin
```

---

## 6. X / Twitter

### Tweet 1

```
openvox-gui 3.12.0 is out -- clustered consoles and one fleet status.

Newest OpenVoxDB report on Overview, Nodes, and detail. Two sites no longer disagree on Needs attention.
```

### Tweet 2

```
All-in-one on the OpenVox Server is still the default install. Dedicated consoles, VIP sessions, and shared ENC Postgres are optional and documented.

https://github.com/cvquesty/openvox-gui/releases/latest
```

---

## 7. LinkedIn

```
Shipped openvox-gui 3.12.0 today.

openvox-gui is the Apache-2.0 web console for OpenVox, the community continuation of Puppet. 3.12.0 promotes the clustered-console train to stable: one newest-report status across Overview, Nodes, and Monitoring, peer OpenVoxDB merge so two site consoles show the same Needs attention list, and VIP-safe sessions. All-in-one install on the OpenVox Server remains the default path.

Repo: https://github.com/cvquesty/openvox-gui
Release: https://github.com/cvquesty/openvox-gui/releases/latest

#OpenVox #Puppet #DevOps #InfrastructureAsCode #OpenSource
```

---

## 8. Hacker News (Show HN)

### Title

```
Show HN: openvox-gui 3.12.0 -- clustered web console for OpenVox/Puppet
```

### First comment

```
Maintainer here. openvox-gui is an Apache-2.0 FastAPI + React console for OpenVox. 3.12.0 is the first stable with optional dedicated consoles (shared Postgres ENC, VIP sessions) while AIO on the Puppet/OpenVox Server stays the default.

The fleet badge is the newest OpenVoxDB report document, merged across site VIPs so two consoles don't invent different "unreported" lists.

https://github.com/cvquesty/openvox-gui
```
