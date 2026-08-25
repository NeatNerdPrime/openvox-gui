# openvox-gui 3.12.0 -- Announcement Copy

> **Release:** v3.12.0 (current download) -- clustered consoles, one fleet status, all-in-one still first.
> **Generated:** 2026-08-25
> **Canonical URLs:**
> - Repo: https://github.com/cvquesty/openvox-gui
> - Latest release: https://github.com/cvquesty/openvox-gui/releases/latest
> - v3.12.0 release notes (current): https://github.com/cvquesty/openvox-gui/releases/tag/v3.12.0
> - Status / operator map: https://github.com/cvquesty/openvox-gui/blob/main/docs/STATUS.md
> - Clustered runbook: https://github.com/cvquesty/openvox-gui/blob/main/docs/CLUSTERED_SHARED_DB.txt
> - Upgrade: https://github.com/cvquesty/openvox-gui/blob/main/UPDATE.md
> - Changelog: https://github.com/cvquesty/openvox-gui/blob/main/CHANGELOG.md

## How to use this file

Each section below is calibrated to one platform's voice, length limits, and markdown dialect. Copy the contents of the fenced code block under each heading and paste into the target surface.

Internal train numbers stay in CHANGELOG. Public copy leads with what an operator sees.

| # | Platform | Length | Tone | Markdown? |
|---|----------|--------|------|-----------|
| 1 | GitHub Discussions (canonical) | Long | Formal, polished | Yes (GFM) |
| 2 | VoxPupuli Connect (Discourse) | Medium | Conversational | Yes |
| 3 | VoxPupuli Slack | Short | Casual, link-heavy | Slack syntax |
| 4 | Reddit r/sysadmin / r/Puppet | Medium | "I built this" | Yes |
| 5 | Mastodon (Fosstodon, hachyderm) | 1 toot, ~470 chars | Factual + hashtags | Plain |
| 6 | X / Twitter | 3-tweet thread, ~270 chars each | Punchy | Plain |
| 7 | LinkedIn | Medium, story-shaped | Professional | Plain |
| 8 | Hacker News (Show HN) | Title + first comment | Technical, no marketing | Plain |

---

## 1. GitHub Discussions -- Announcement post

Best home for the canonical announcement. Pin it.

### Title

```
openvox-gui 3.12.0 -- Clustered consoles and one fleet status
```

### Body

````markdown
# openvox-gui 3.12.0 is out

Stable **v3.12.0** is on the [Releases page](https://github.com/cvquesty/openvox-gui/releases/latest). This is the first stable that treats a dedicated console as a real install path, while keeping **all-in-one on the OpenVox Server** as the default.

## One fleet status (the headline)

Overview, Nodes, Node Detail, Monitoring, Heatmap, and Environments now share the same live fleet.

- Membership is active OpenVoxDB `/nodes` (DNS-only VIP names hidden; HAProxy boxes such as `ovcompilers.*` stay).
- The badge is the **newest report document** for that certname, not the CA list and not a 24-hour rewrite. A day-old Unchanged stays Unchanged. Clicking a node no longer flips gray to green.
- **Needs attention** is failed, unreported, or last report older than 24 hours -- the same rule on the Dashboard table and on Nodes `?status=attention`.
- On a two-site estate the GUI **merges newest reports from peer OpenVoxDBs**, so one console does not list six stale hosts while the other shows a clean fleet.

Compilers still have to store reports (`[server] reports = puppetdb`) and write to site `ovdb1`/`ovdb2`. The GUI will not invent a report that never landed.

## Clustered consoles (optional)

If you run more than one datacenter you can put the GUI on dedicated hosts:

- VIP-safe sessions (no reload storm on 401)
- Shared Postgres database `openvox_gui` (not the `puppetdb` database) and the same `SECRET_KEY` on every console
- ENC HTTPS verified against the Puppet CA
- `ovox infra health` against members and VIPs
- Bolt estate inventory for Play / Orchestration

Most people should still run `sudo ./install.sh` on the OpenVox Server. SQLite is fine. Clustering is documented in [STATUS](https://github.com/cvquesty/openvox-gui/blob/main/docs/STATUS.md) and the [clustered DB runbook](https://github.com/cvquesty/openvox-gui/blob/main/docs/CLUSTERED_SHARED_DB.txt).

## Also in 3.12.0

- Log Viewer empty host returns 200, not 502
- Sortable PQL result columns
- Run OpenVox treats agent exit **2** as success (changes applied)
- Clustered Code Deploy via Bolt / r10k
- LDAP and session polish (bind password keep-on-blank, no false "session expired")

## Upgrading

```bash
sudo /opt/openvox-gui/scripts/update_local.sh
```

Or `scripts/update_remote.sh`. After upgrade:

1. Hard-refresh browsers once.
2. Dual-console: identical `OPENVOX_GUI_SECRET_KEY` and `OPENVOX_GUI_DATABASE_URL`.
3. Compilers: `[server] reports = puppetdb`. Do not point writes at a dual-A name.

Full notes: [v3.12.0](https://github.com/cvquesty/openvox-gui/releases/tag/v3.12.0) · [CHANGELOG](https://github.com/cvquesty/openvox-gui/blob/main/CHANGELOG.md) · [UPDATE.md](https://github.com/cvquesty/openvox-gui/blob/main/UPDATE.md).

Issues / feedback / PRs welcome.
````

---

## 2. VoxPupuli Connect (Discourse forum)

Slightly less formal than the GitHub post, conversational opener.

### Title

```
[Release] openvox-gui 3.12.0 -- clustered consoles, one fleet status
```

### Body

````markdown
Just shipped openvox-gui 3.12.0.

**1. One fleet status.** Overview, Nodes, and Node Detail all show the newest OpenVoxDB report. A day-old Unchanged stays Unchanged. Needs attention is failed / unreported / older than 24h on both the Dashboard and the Nodes filter. Two site consoles merge peer reports so they stop disagreeing.

**2. Clustered consoles are optional.** Dedicated GUI hosts, VIP-safe sessions, shared Postgres `openvox_gui`, ENC TLS to the Puppet CA, ovox estate health. All-in-one on the OpenVox Server is still the default install.

Also: Log Viewer empty≠502, sortable PQL, Run OpenVox treats exit 2 as success.

Repo + release notes: https://github.com/cvquesty/openvox-gui/releases/latest
Operator map: https://github.com/cvquesty/openvox-gui/blob/main/docs/STATUS.md

Feedback welcome -- happy to iterate based on what folks need.
````

---

## 3. VoxPupuli Slack (`#openvox`, `#general`, `#announcements`)

Slack syntax (`*bold*`, `_italic_`).

````
*openvox-gui 3.12.0 is out* -- clustered consoles and one fleet status.

Overview / Nodes / detail now share the newest OpenVoxDB report. Two site consoles merge peer reports so Needs attention matches. AIO on the OpenVox Server is still the default install.

Releases: https://github.com/cvquesty/openvox-gui/releases/latest
STATUS: https://github.com/cvquesty/openvox-gui/blob/main/docs/STATUS.md
````

---

## 4. Reddit r/sysadmin and/or r/Puppet

Reddit favors honest, "I built this and here's what changed" framing. Avoid marketing-speak.

### Title (works for r/Puppet, r/sysadmin, r/devops)

```
[Release] openvox-gui 3.12.0 -- web GUI for OpenVox with optional clustered consoles
```

### Body

````markdown
Maintainer here. Just cut [openvox-gui](https://github.com/cvquesty/openvox-gui) **3.12.0** -- the Apache-2.0 web GUI for [OpenVox](https://voxpupuli.org/) (the community Puppet fork). Dashboard, Nodes, ENC, CA, Bolt/OpenBolt, r10k, PQL, Hiera.

**What changed.** The badge on Overview is now the newest OpenVoxDB report, same as the node page. We stopped aging Unchanged to Unreported after 24 hours (Needs attention still lists stale hosts). If you run two site consoles they merge peer reports so one site does not show six "needs attention" nodes while the other shows none.

**Install path.** Most people still drop it on the OpenVox Server (`sudo ./install.sh`, SQLite). 3.12.0 is the first stable that also documents dedicated consoles: VIP sessions, shared Postgres for ENC/users, ENC TLS to the Puppet CA.

Upgrade:

```bash
sudo /opt/openvox-gui/scripts/update_local.sh
```

Hard-refresh once. Compilers need `[server] reports = puppetdb` or the GUI will never see the run.

Apache-2.0. Repo: https://github.com/cvquesty/openvox-gui

Happy to answer questions or take feedback in the thread.
````

---

## 5. Mastodon (Fosstodon, hachyderm.io)

Single toot, ~470 chars, hashtags at the end.

````
openvox-gui 3.12.0 shipped. Overview now shows the newest OpenVoxDB report on every page; two site consoles merge peer reports so Needs attention matches. Dedicated consoles are optional. All-in-one on the OpenVox Server stays the default.

https://github.com/cvquesty/openvox-gui/releases/latest

#OpenVox #Puppet #DevOps #SysAdmin
````

---

## 6. X / Twitter (3-tweet thread, ~270 chars each)

Post tweets 2 and 3 as replies to tweet 1.

### Tweet 1 (anchor)

````
openvox-gui 3.12.0 is out -- clustered consoles and one fleet status.

Overview, Nodes, and node detail now share the newest OpenVoxDB report. A day-old Unchanged stays Unchanged.
````

### Tweet 2

````
Two site consoles merge peer reports so Needs attention is the same list on both.

Dedicated consoles (VIP sessions, shared ENC Postgres) are optional. All-in-one on the OpenVox Server is still the default install.
````

### Tweet 3 (CTA)

````
Apache-2.0. Upgrade with update_local.sh, then hard-refresh. Compilers need reports = puppetdb.

Releases: https://github.com/cvquesty/openvox-gui/releases/latest
STATUS: https://github.com/cvquesty/openvox-gui/blob/main/docs/STATUS.md
````

---

## 7. LinkedIn

Professional, story-shaped. SS Consulting Group voice.

````
Shipped openvox-gui 3.12.0 today.

openvox-gui is the Apache-2.0 web console for OpenVox, the community continuation of Puppet. Operators use it for fleet status, certificates, ENC classification, Bolt, r10k, and PQL without living in five different CLIs.

3.12.0 is the first stable that treats a dedicated console as a real architecture: VIP-safe sessions, shared Postgres for ENC and users, and a merge of newest OpenVoxDB reports so two site consoles stop disagreeing about which nodes need attention. All-in-one on the OpenVox Server remains the default path for everyone else.

The badge on Overview is now the same newest-report status you see when you click the node. That sounds small. It is the difference between trusting the dashboard and ignoring it.

Repo: https://github.com/cvquesty/openvox-gui
Release: https://github.com/cvquesty/openvox-gui/releases/latest

#OpenVox #Puppet #DevOps #InfrastructureAsCode #OpenSource
````

---

## 8. Hacker News (Show HN -- optional)

Title <80 chars, no emoji, no marketing-speak.

### Title

```
Show HN: openvox-gui 3.12.0 -- clustered web console for OpenVox
```

### First comment (post immediately after submission)

````
Maintainer here. openvox-gui is an Apache-2.0 web GUI for OpenVox, the community-led continuation of Puppet open-source. It gives you a fleet dashboard, node detail, ENC classification, CA signing, Bolt/OpenBolt, r10k deploys, PQL, and Hiera from one systemd service.

3.12.0 is the first stable with optional dedicated consoles (shared Postgres ENC, VIP sessions) while all-in-one on the OpenVox Server stays the default install.

The fleet badge is the newest OpenVoxDB report document, not the CA list and not a 24-hour rewrite. On a dual-VIP estate we merge newest reports from peer OpenVoxDBs so two consoles do not invent different "unreported" lists. Compilers still have to store reports; we do not stub certnames.

Stack is FastAPI + React/TypeScript/Mantine, SQLite or Postgres via SQLAlchemy. install.sh, update_local.sh, systemd unit.

Happy to dig into any of the design choices.

https://github.com/cvquesty/openvox-gui
````

---

## Notes

- Each section's body is in a fenced code block so you can triple-click + copy without picking up surrounding text.
- Do not mention rc.N numbers in public posts. CHANGELOG is the audit trail.
- LinkedIn uses the SS Consulting Group voice -- shorten the first paragraph if you want it personal.
- For the X thread, post tweets 2 and 3 as replies to tweet 1.
- The Mastodon toot fits a default 500-char instance.
- Creating this document is a standard step for an official GitHub Release (AGENTS.md "Press release / announcement document").
