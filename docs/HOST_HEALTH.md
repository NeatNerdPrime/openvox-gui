# Host Health (Serving Estate)

**Route:** Insights catalog → Host Health (`/insights/host-health`), also embeddable on Monitoring.  
**Since:** 3.11+ Host Health collector; disk ring under `data/host_metrics/`.

**Insights → Host Health** shows OS-level saturation for the **OpenVox serving estate** only:

| Included | Not included |
|----------|----------------|
| GUI / console host | Puppet **agents** (fleet) |
| Catalog **compilers** (Settings → Cluster) | Arbitrary inventory nodes |
| **OpenVoxDB** application hosts | |
| **CA** member hosts | |

Agent-fleet host metrics may be added later; they are intentionally out of scope today.

## What you see

- **CPU used / iowait / steal**, load averages, memory & swap
- **Saturation** badge (green / yellow / red) with reasons
- **Time series** (local ring buffer, also persisted under `data/host_metrics/`)
- **OpenVox-related processes** (java, postgres, puppet, uvicorn, bolt, r10k, …) via `pidstat` when available

## Data sources

| Source | Where |
|--------|--------|
| `/proc` (load, mem, cpu, diskstats) | Always, on the GUI host; remote via Bolt one-liner |
| `sar` (sysstat) | GUI host when package installed — better short-interval CPU |
| `pidstat` (sysstat) | GUI host when installed — process CPU samples |
| Bolt `command run` | Remote compilers / ovdb / CA when inventory can reach them |

### Install sysstat (recommended on the GUI host)

```bash
# RHEL / Rocky / Alma
sudo dnf install -y sysstat
sudo systemctl enable --now sysstat   # optional historical sa logs

# Verify
sar -u 1 1
pidstat -u 1 1
```

Remote nodes do **not** require sysstat for basic load/memory/CPU ratios (Bolt uses `/proc`).

## Cluster configuration

1. **Settings → Application → Cluster** → set **clustered**
2. List **compiler**, **OpenVoxDB**, and **CA** FQDNs
3. Host Health uses those lists (plus the local GUI hostname)

Single-server installs still work: the local host is labeled `gui` + compiler/puppetdb roles.

## API

| Method | Path | Notes |
|--------|------|--------|
| GET | `/api/insights/host-health` | Full estate snapshot + history |
| GET | `/api/insights/host-health/targets` | Planned targets only |
| POST | `/api/insights/host-health/collect` | Force collect (admin/operator) |

## Background collection

A small asyncio loop (started with the GUI) samples the **local** host every ~15s and runs a full estate collect (including Bolt remotes) every fourth tick. History is capped (~360 points) and written under:

```text
/opt/openvox-gui/data/host_metrics/
```

## Security / operations

- No new public ports; local commands and existing Bolt transport only
- Does not run against the agent fleet
- Pair with **OpenVox Server Health** / **OpenVoxDB Health** (JVM/Jolokia) for full “is it Puppet or the box?” diagnosis
