# VIP console sessions (multi-console HA)

**Since:** 3.12.0-rc.1 · Related: [FEATURES.md](FEATURES.md), [ARCHITECTURE.md](ARCHITECTURE.md)

When users hit the GUI through a **load-balanced VIP** (two or more console
nodes behind one hostname), sessions and auto-refresh must not thrash.

Direct node URLs keep the historic aggressive polling behaviour:

| URL | Mode |
|-----|------|
| `https://openvox.site-a.example.com:4567` | **direct** |
| `https://openvox.site-b.example.com:4567` | **direct** |
| `https://openvox.example.com:4567` (VIP) | **vip** |

## Symptoms this fixes

- Random full-page refreshes on Insights / Dashboard behind the VIP
- Eventual forced logout while the same browser stays fine on a node FQDN
- Version-check false positives when `index.html` ETags differ per backend

## Root cause (short)

1. VIP load-balances API calls across consoles.
2. Any intermittent `401` (secret mismatch, denylist DB blip, peer lag)
   used to call `window.location.reload()` on **every** poll.
3. Polling pages multiplied the damage into a refresh/logout storm.

## Application behaviour

| Layer | Behaviour |
|-------|-----------|
| **401 handling** | Single-flight probe of `GET /api/auth/me`; soft-land to login once — **no** `location.reload()` |
| **Denylist** | Confirmed revoke → 401; **lookup errors fail open** (signature-valid JWT still accepted) |
| **JWT** | Default 24h lifetime, **never below 4h**; cookie `max_age` matches; sliding renew under 25% remaining |
| **Session floor** | Product rule: no forced logout before **4 hours** after login (`session_min_seconds`) |
| **VIP polls** | Floor ~45s (`OPENVOX_GUI_VIP_POLL_FLOOR_MS`); focus refetch debounced 15s |
| **Version check** | Uses `/api/version` JSON, not dual-node HTML ETags |

## Operator configuration

### 1. Same secret + shared DB (required for dual console)

Both consoles **must** share:

- `OPENVOX_GUI_SECRET_KEY` (identical)
- Postgres `openvox_gui` (`OPENVOX_GUI_DATABASE_URL`) — never the `puppetdb` database

Order of operations and the two Spock meshes: [CLUSTERED_SHARED_DB.txt](CLUSTERED_SHARED_DB.txt).

### 2. Declare VIP hostnames

**Option A — Settings → Application → Cluster**

- **GUI console FQDNs** = node names (site-a, site-b)
- **Console VIP / public LB hostnames** = VIP users type in the browser

**Option B — environment (both consoles)**

```bash
OPENVOX_GUI_VIP_HOSTS=openvox.example.com
# optional:
OPENVOX_GUI_VIP_POLL_FLOOR_MS=45000
OPENVOX_GUI_AUTH_TOKEN_HOURS=24
OPENVOX_GUI_AUTH_SESSION_TIMEOUT=14400
```

### 3. Load balancer

Prefer **sticky sessions** (cookie or source IP) **and** keep both consoles on
the same GUI version. The app is RR-safe after 3.12, but stickiness reduces
noise on failover.

### 4. Verify

```bash
curl -sk https://VIP:4567/api/auth/status | jq .
# expect: "access_mode": "vip", "vip_poll_floor_ms": 45000, ...

curl -sk https://openvox.site-a.example.com:4567/api/auth/status | jq .access_mode
# expect: "direct"
```

## API

`GET /api/auth/status` (public) includes:

```json
{
  "access_mode": "vip",
  "session_ttl_seconds": 86400,
  "session_min_seconds": 14400,
  "vip_poll_floor_ms": 45000,
  "request_host": "openvox.example.com",
  "vip_hosts_configured": ["openvox.example.com"]
}
```
