# openvox-gui 3.14.0 -- Announcement Copy

> **Release:** v3.14.0 (current download) -- clustered ops that do not need compiler TTY, a package mirror that stays on the disk you have, Monitoring charts that actually paint.
> **Generated:** 2026-09-21
> **Canonical URLs:**
>
> - Repo: <https://github.com/cvquesty/openvox-gui>
> - Latest release: <https://github.com/cvquesty/openvox-gui/releases/latest>
> - v3.14.0 release notes (current): <https://github.com/cvquesty/openvox-gui/releases/tag/v3.14.0>
> - Status / operator map: <https://github.com/cvquesty/openvox-gui/blob/main/docs/STATUS.md>
> - Agent installer: <https://github.com/cvquesty/openvox-gui/blob/main/docs/INSTALLER.md>
> - Upgrade: <https://github.com/cvquesty/openvox-gui/blob/main/UPDATE.md>
> - Changelog: <https://github.com/cvquesty/openvox-gui/blob/main/CHANGELOG.md>

## How to use this file

Each section below is calibrated to one platform's voice, length limits, and markdown dialect. Copy the contents of the fenced code block under each heading and paste into the target surface.

Internal train numbers (`3.13.0-rc.N`, `3.12.1-dev.N`) stay in CHANGELOG. Public copy leads with what an operator sees. There is no 3.13.0 GitHub Release; 3.14.0 is the next stable after 3.12.0.

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
openvox-gui 3.14.0 -- Clustered ops, lean PDB, and an installer that fits on disk
```

### Body

````markdown
# openvox-gui 3.14.0 is out

Stable **v3.14.0** is on the [Releases page](https://github.com/cvquesty/openvox-gui/releases/latest). This is the next stable after 3.12.0 (the 3.13.0-rc train; there is no 3.13.0 GitHub Release). All-in-one on the OpenVox Server is still the default install.

## Clustered ops without compiler TTY (the headline)

Code Deploy, Hiera Lookup, and Agent Install no longer need a sudo TTY on the compiler, and they no longer lean on the compiler's PuppetDB termini.

- Clustered `install.bash` writes `ca_server=` from `OPENVOX_GUI_PUPPET_CA_HOST`. That must be the **CA VIP**, never the compiler VIP (compilers have CA off).
- Hiera Lookup uses a throwaway confdir (`storeconfigs = false`, facter facts) so explain does not trip compiler `server_urls` / CRL.
- ENC menus list live r10k environments. Bolt inventory is `openvox_enc`.

## Lean PDB and last-good fleet

Overview and Monitoring talk to **one** PuppetDB VIP and a lean report extract. A flaky or one-node VIP probe no longer replaces a known fleet -- last-good is stored so both consoles share it.

## Monitoring charts paint

HTTP latency, storage timing, and catalog dedup were drawing a 0×0 SVG. Chart panels now pass a measured width. Empty series still show the current Jolokia snapshot as bars. Fleet Population is dual-axis. Top 10 Slowest Nodes is a rank bar.

## Agent package mirror stays on the disk you have

Selecting only EL9/EL10 and OpenVox 8/9 used to recurse `src/` and `ppc64le/` and leave a ~40G apt pool after you unchecked Debian. 3.14.0:

- Follows `.mirror-selections.json` strictly
- Fetches yum per selected arch (`x86_64`, `aarch64`) only
- Prunes unselected trees on Apply Changes and every sync
- Finds both rsync `apt/pool/` and curl `apt/openvoxN/` layouts

EL9+EL10 yum-only is about **9 GB**, not 50+.

## Run OpenVox

Puppet agent exit **2** (changes applied) is success. The Human tab shows the agent's Info/Notice lines, not the Bolt JSON wrapper.

## Upgrading

```bash
sudo /opt/openvox-gui/scripts/update_local.sh
```

After upgrade:

1. Hard-refresh browsers once.
2. Clustered consoles: set `OPENVOX_GUI_PUPPET_CA_HOST` to the CA VIP.
3. If `/opt/openvox-pkgs` already filled the disk, see [TROUBLESHOOTING](https://github.com/cvquesty/openvox-gui/blob/main/TROUBLESHOOTING.md) then Sync now.

Full notes: [v3.14.0](https://github.com/cvquesty/openvox-gui/releases/tag/v3.14.0) · [CHANGELOG](https://github.com/cvquesty/openvox-gui/blob/main/CHANGELOG.md) · [UPDATE.md](https://github.com/cvquesty/openvox-gui/blob/main/UPDATE.md) · [STATUS](https://github.com/cvquesty/openvox-gui/blob/main/docs/STATUS.md).

Issues / feedback / PRs welcome.
````

---

## 2. VoxPupuli Connect (Discourse forum)

Slightly less formal than the GitHub post, conversational opener.

### Title

```
[Release] openvox-gui 3.14.0 -- clustered ops, lean PDB, installer that fits
```

### Body

````markdown
Just shipped openvox-gui 3.14.0. Next stable after 3.12.0.

**1. Clustered ops without compiler TTY.** Code Deploy, Hiera Lookup, and Agent Install no longer need sudo TTY on the compiler. Set `OPENVOX_GUI_PUPPET_CA_HOST` to the CA VIP -- never the compiler VIP.

**2. Package mirror.** EL9/EL10 + OpenVox 8/9 no longer pull src/ppc64le or leave a 40G apt pool. Unselected trees are pruned. ~9 GB for yum-only.

**3. Monitoring actually draws.** Chart width, duration axes, last-good fleet so a VIP probe cannot show one node.

Also: Run OpenVox treats Puppet exit 2 as success; Human tab shows CLI, not Bolt JSON.

Repo + release notes: https://github.com/cvquesty/openvox-gui/releases/latest
Operator map: https://github.com/cvquesty/openvox-gui/blob/main/docs/STATUS.md
Installer: https://github.com/cvquesty/openvox-gui/blob/main/docs/INSTALLER.md

Feedback welcome -- happy to iterate based on what folks need.
````

---

## 3. VoxPupuli Slack (`#openvox`, `#general`, `#announcements`)

Slack syntax (`*bold*`, `_italic_`).

````
*openvox-gui 3.14.0 is out* -- clustered Code Deploy / Hiera / Agent Install without compiler sudo TTY, and a package mirror that will not fill a 70G disk.

Set OPENVOX_GUI_PUPPET_CA_HOST to the CA VIP. EL9/EL10 yum-only is ~9 GB. Monitoring charts finally get a width.

Releases: https://github.com/cvquesty/openvox-gui/releases/latest
STATUS: https://github.com/cvquesty/openvox-gui/blob/main/docs/STATUS.md
````

---

## 4. Reddit r/sysadmin and/or r/Puppet

Reddit favors honest, "I built this and here's what changed" framing. Avoid marketing-speak.

### Title (works for r/Puppet, r/sysadmin, r/devops)

```
[Release] openvox-gui 3.14.0 -- OpenVox web GUI; clustered install and a local package mirror that fits
```

### Body

````markdown
Maintainer here. Just cut [openvox-gui](https://github.com/cvquesty/openvox-gui) **3.14.0** -- the Apache-2.0 web GUI for [OpenVox](https://voxpupuli.org/) (the community Puppet fork). Dashboard, Nodes, ENC, CA, Bolt/OpenBolt, r10k, PQL, Hiera, local agent installer.

**What changed since 3.12.0.** Clustered Code Deploy / Hiera / Agent Install no longer need a sudo TTY on the compiler. The agent one-liner sets `ca_server` from `OPENVOX_GUI_PUPPET_CA_HOST` (the CA VIP -- compilers have CA off). The local yum/apt mirror used to recurse `src/` and `ppc64le/` and leave a 40G apt pool after you unchecked Debian; 3.14.0 prunes unselected trees. EL9+EL10 yum-only is about 9 GB. Monitoring charts were painting a 0×0 SVG; they get a real width now. Puppet agent exit 2 is treated as success.

AIO on the OpenVox Server is still the default. Clustering is optional.

Apache-2.0 licensed. Repo: https://github.com/cvquesty/openvox-gui

Happy to answer questions or take feedback in the thread.
````

---

## 5. Mastodon (sysadmin / DevOps community -- Fosstodon, hachyderm.io)

Single toot, ~470 chars, hashtags at the end.

````
openvox-gui 3.14.0 just shipped. Clustered Code Deploy / Hiera / Agent Install no longer need compiler sudo TTY. The local package mirror prunes unselected distros (EL9/EL10 yum-only ~9 GB). Monitoring charts finally get a width.

https://github.com/cvquesty/openvox-gui/releases/latest

#OpenVox #Puppet #DevOps #SysAdmin
````

---

## 6. X / Twitter (3-tweet thread, ~270 chars each)

### Tweet 1 (anchor)

````
openvox-gui 3.14.0 just shipped -- clustered ops without compiler sudo TTY, and a package mirror that stays on the disk you have.
````

### Tweet 2

````
EL9/EL10 + OpenVox 8/9 no longer pull src/ppc64le or leave a 40G apt pool. Unselected trees are pruned. Monitoring charts get a real width. Puppet exit 2 is success.
````

### Tweet 3 (CTA)

````
AIO on the OpenVox Server is still the default. Clustered consoles set OPENVOX_GUI_PUPPET_CA_HOST to the CA VIP.

Apache-2.0. Releases: https://github.com/cvquesty/openvox-gui/releases/latest
````

---

## 7. LinkedIn

Professional, story-shaped. Good fit for the SS Consulting Group identity.

````
Shipped openvox-gui 3.14.0 today.

OpenVox GUI is the Apache-2.0 web console for OpenVox, the community continuation of Puppet open-source: fleet status, ENC, CA, Bolt/OpenBolt, r10k, PQL, and a PE-style agent installer.

3.14.0 is the ops-hardening release after 3.12.0. Clustered Code Deploy, Hiera Lookup, and Agent Install no longer require a sudo TTY on the compiler. New agents get ca_server from OPENVOX_GUI_PUPPET_CA_HOST (the CA VIP -- never the compiler). The local package mirror now honors what you actually checked: EL9/EL10 yum-only is about 9 GB instead of filling a 70 GB disk with src RPMs and leftover apt. Monitoring charts get a measured width so they stop rendering as a blank box.

All-in-one on the OpenVox Server remains the default. Clustering is optional and documented.

Repo: https://github.com/cvquesty/openvox-gui
Release: https://github.com/cvquesty/openvox-gui/releases/latest

#OpenVox #Puppet #DevOps #InfrastructureAsCode #OpenSource
````

---

## 8. Hacker News (Show HN -- optional)

If you want to test community reception there. HN audience is harsher but if it lands it'll drive real eyeballs to the repo. Title <80 chars, no emoji, no marketing-speak.

### Title

```
Show HN: openvox-gui 3.14.0 -- web GUI for OpenVox (community Puppet)
```

### First comment (post immediately after submission so it appears at top)

````
Maintainer here. openvox-gui is an Apache-2.0 web GUI for OpenVox, the community-led continuation of Puppet open-source. It gives you fleet status, ENC, CA, Bolt/OpenBolt orchestration, r10k, PQL, Hiera, and a local agent package mirror with PE-style curl | bash.

3.14.0 is the next stable after 3.12.0. Two things that were hurting operators:

1. Clustered Code Deploy / Hiera / Agent Install needed a sudo TTY on the compiler and sometimes used the compiler VIP as CA (compilers have CA disabled). The GUI now passes ca_server from OPENVOX_GUI_PUPPET_CA_HOST.

2. The local yum/apt mirror recursed src/ and ppc64le and left a 40G apt pool after you unchecked Debian. Selections are now authoritative; unselected trees are pruned. EL9+EL10 yum-only is ~9 GB.

Stack is FastAPI + React/TypeScript/Mantine, SQLite (AIO) or Postgres openvox_gui (clustered). systemd unit, install.sh.

Happy to dig into any of the design choices.

https://github.com/cvquesty/openvox-gui
````

---

## Notes

- Each section's body is in a fenced code block so you can triple-click + copy without picking up surrounding text.
- Internal `3.13.0-rc` / `3.12.1-dev` numbers stay out of public copy except the one sentence that 3.14.0 follows 3.12.0 with no 3.13.0 GitHub Release.
- For the X thread, post tweets 2 and 3 as replies to tweet 1.
- **Process note:** GitHub Releases (`gh release create`) are a separate, deliberate step. This file is the announcement kit for when that step is taken.
