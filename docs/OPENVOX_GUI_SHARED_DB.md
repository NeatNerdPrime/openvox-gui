# OpenVox GUI shared database (ovdb + Spock + consoles)

**Audience:** operators bringing up multi-console ENC on an estate that
already has OpenVoxDB on Postgres (often PG 17 + Spock).

**Related:** `docs/CLUSTERED_SHARED_DB.txt` (earlier ordinal runbook),
`docs/COMPILER_ENC.md` (compiler `enc.py` path).

**Date:** 2026-08-13

---

## 0. Architecture (what we are building)

```text
  Agents ──► compiler VIP (per region) ──► compilers
                    │
                    │ external_nodes → enc.py
                    ▼
         GUI consoles (HTTP classify API)
         openvox.pdxc + openvox.atlc
                    │
                    │ SQL (same DSN / VIP)
                    ▼
         Postgres database: openvox_gui
         (role openvox_gui — NOT database puppetdb)
                    │
                    │ Spock (optional day-1; required for site-loss ENC)
                    ▼
         ovdb1..ovdb4  (same instances that host PuppetDB, separate DB)
```

| Plane | Nodes | Access |
|-------|--------|--------|
| Classification UI + API | 2 consoles (geo) | Operators + **compilers** via HTTPS `/api/enc/classify/…` |
| ENC / users / GUI app state | Postgres DB **`openvox_gui`** | Consoles only (SQL :5432) |
| Catalog compile | 4 compilers, 2/region behind VIP | Agents → VIP :8140 |
| CA | 4 CA, Pacemaker+DRBD regional | Agents → CA VIP |
| Facts/reports | PuppetDB DB **`puppetdb`** | Compilers/consoles mTLS :8081 |

**Compilers never open Postgres for ENC.** They call the console API.
Shared DB makes both consoles return the **same** classify YAML → no drift.

---

## 1. Tablespace vs database (important)

| Term | Meaning here |
|------|----------------|
| **Wrong: PostgreSQL TABLESPACE** | Physical storage location for files. **Not** what we need. |
| **Right: separate DATABASE** | `CREATE DATABASE openvox_gui` on the **same Postgres instances** as PuppetDB. |

We do **not** add PuppetDB tables to a new tablespace. We create a
**second database** on the ovdb cluster:

- Database name: `openvox_gui`
- Role name: `openvox_gui` (no `CONNECT` on database `puppetdb`)

Spock is **per database**. Replication for `puppetdb` does **not** copy
`openvox_gui`. You must configure Spock **inside** `openvox_gui` if you
want multi-node / multi-site copies of classification data.

---

## 2. VIP and API (what “reachable everywhere” means)

### 2.1 Postgres VIP (:5432)

- PuppetDB HAProxy/VIP today is often **TCP 8081**, not 5432.
- For the GUI app DB you need either:
  - **Day-1:** both consoles use the **write primary** FQDN  
    (`ovdb1.pdxc-it.corp.int-x.ai:5432`), or
  - **Better:** a **5432 VIP** (or DNS name) that always points at the
    **current write primary** for `openvox_gui` (same promote story as PDB).

Do not put all four ovdb backends behind a dumb round-robin on 5432 for
writers unless you know your Spock topology supports multi-writer for
these tables (default Spock mesh is careful; day-1 = single writer URL).

### 2.2 “API”

| Consumer | Protocol | Endpoint / target |
|----------|----------|-------------------|
| Compilers (`enc.py`) | HTTPS | `OPENVOX_GUI_API_BASE` → `/api/enc/classify/<certname>/yaml` |
| Operators | HTTPS | Console `/enc` UI + REST under `/api/enc/*` |
| Consoles → data store | Postgres | `OPENVOX_GUI_DATABASE_URL` → VIP or primary :5432 / `openvox_gui` |

Agents never talk to the GUI DB VIP.

---

## 3. Prerequisites

- [ ] Postgres running on all four ovdb nodes (same major version as PDB).
- [ ] Superuser access on each ovdb (`postgres` OS user / superuser role).
- [ ] `psql` path known, e.g. `/usr/pgsql-17/bin/psql`.
- [ ] Spock already loaded for PuppetDB (`shared_preload_libraries` includes
      spock). **Do not change GUCs** just for this DB unless required.
- [ ] Console IPs known (PDXC + ATLC openvox hosts).
- [ ] Vault password for role `openvox_gui` (call it `GUI_DB_PASSWORD`).
- [ ] REPL user password if reusing Spock `REPL_USER` for the new DB.
- [ ] Console package has `asyncpg` (openvox-gui requirements) and alembic.

**Assumption check:** Creating objects only on `ovdb1.pdxc` does **not**
auto-create the database on other nodes via existing PuppetDB Spock.

---

## 4. Procedure — create role and empty database

Replace paths and IPs. Run as root on each ovdb unless noted.

```bash
export PSQL=/usr/pgsql-17/bin/psql
export GUI_DB_PASSWORD='…'   # from vault; do not commit
```

### 4.1 Role on **every** ovdb instance (all four)

Each Spock node is typically its own Postgres instance. Create the login
role on **each**:

```bash
# On ovdb1.pdxc, ovdb2.pdxc, ovdb1.atlc, ovdb2.atlc (names as in your estate)
sudo -u postgres "$PSQL" --no-psqlrc <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'openvox_gui') THEN
    CREATE ROLE openvox_gui LOGIN PASSWORD '${GUI_DB_PASSWORD}'
      NOSUPERUSER NOCREATEDB NOCREATEROLE;
  ELSE
    ALTER ROLE openvox_gui WITH PASSWORD '${GUI_DB_PASSWORD}';
  END IF;
END
\$\$;
SQL
```

### 4.2 Database on **every** ovdb instance

Empty database must exist on each node before Spock can subscribe.
**CREATE DATABASE does not replicate.**

```bash
# On EVERY ovdb node:
sudo -u postgres "$PSQL" --no-psqlrc <<'SQL'
SELECT 'create_db'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'openvox_gui')\gexec
SQL
# Portable form:
sudo -u postgres "$PSQL" --no-psqlrc -tc \
  "SELECT 1 FROM pg_database WHERE datname='openvox_gui'" | grep -q 1 \
  || sudo -u postgres "$PSQL" --no-psqlrc \
       -c "CREATE DATABASE openvox_gui OWNER openvox_gui;"

sudo -u postgres "$PSQL" --no-psqlrc -c \
  "GRANT ALL PRIVILEGES ON DATABASE openvox_gui TO openvox_gui;"

sudo -u postgres "$PSQL" --no-psqlrc -d openvox_gui <<'SQL'
GRANT ALL ON SCHEMA public TO openvox_gui;
ALTER SCHEMA public OWNER TO openvox_gui;
SQL
```

### 4.3 Deny GUI role access to PuppetDB

```bash
# On every node (should already be true by default if no GRANT):
sudo -u postgres "$PSQL" --no-psqlrc -c \
  "REVOKE ALL ON DATABASE puppetdb FROM openvox_gui;" 2>/dev/null || true
```

### 4.4 `pg_hba.conf` — consoles only

On **every** ovdb that might accept GUI connections (all four if Spock
multi-writer or promote; at least the day-1 primary):

```text
# OpenVox GUI application DB — consoles only (verify IPs)
host  openvox_gui  openvox_gui  <PDXC_CONSOLE_IP>/32  scram-sha-256
host  openvox_gui  openvox_gui  <ATLC_CONSOLE_IP>/32  scram-sha-256
host  openvox_gui  openvox_gui  127.0.0.1/32          scram-sha-256
```

```bash
sudo -u postgres "$PSQL" -c 'SELECT pg_reload_conf();'
```

Firewall: allow **5432** from the two console IPs only (not agent fleets).

### 4.5 Connectivity test (before Spock / before GUI cutover)

From **each console**:

```bash
PGPASSWORD="$GUI_DB_PASSWORD" psql \
  -h ovdb1.pdxc-it.corp.int-x.ai \
  -U openvox_gui -d openvox_gui \
  -c 'SELECT current_database(), current_user, inet_server_addr();'
```

Expect success. Then:

```bash
PGPASSWORD="$GUI_DB_PASSWORD" psql \
  -h ovdb1.pdxc-it.corp.int-x.ai \
  -U openvox_gui -d puppetdb \
  -c 'SELECT 1;'
# must FAIL (no connect on puppetdb)
```

---

## 5. Procedure — schema first (tables), then Spock

Spock replicates **existing tables**. Order:

1. Point **one** console at Postgres (primary).
2. Run alembic / start GUI so tables exist on primary.
3. Then Spock repset + subscriptions (section 6).

### 5.1 Day-1 writer URL

Both consoles (after tables exist, both use the same URL):

```bash
# /opt/openvox-gui/config/.env  (IDENTICAL on both consoles)
OPENVOX_GUI_DATABASE_URL=postgresql+asyncpg://openvox_gui:GUI_DB_PASSWORD@ovdb1.pdxc-it.corp.int-x.ai:5432/openvox_gui
OPENVOX_GUI_SECRET_KEY=<same long secret on both>
```

Prefer a **5432 VIP name** when you have one:

```bash
OPENVOX_GUI_DATABASE_URL=postgresql+asyncpg://openvox_gui:…@ovdb-pg-vip.example.com:5432/openvox_gui
```

Remove any `sqlite+aiosqlite://…` line.

### 5.2 Backup sqlite, restart one console, migrate schema

```bash
# On first console (e.g. PDXC)
cp -a /opt/openvox-gui/data/openvox_gui.db \
  /opt/openvox-gui/data/openvox_gui.db.bak.$(date +%Y%m%d%H%M)

sudo systemctl restart openvox-gui
journalctl -u openvox-gui -n 50 --no-pager

cd /opt/openvox-gui/backend
sudo -u puppet /opt/openvox-gui/venv/bin/alembic upgrade head
```

Verify tables on primary:

```bash
sudo -u postgres $PSQL -d openvox_gui -c '\dt'
sudo -u postgres $PSQL -d openvox_gui \
  -c "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY 1;"
```

Expected app tables include (names may grow): `enc_nodes`, `enc_groups`,
`enc_environments`, `enc_common`, `users`, … all with primary keys.

### 5.3 Load classification data

- Re-classify in UI, or  
- One-time SQLite → Postgres copy (see `CLUSTERED_SHARED_DB.txt` §E.30).

### 5.4 Second console

Same `.env` URL + same `SECRET_KEY`, restart, confirm `/enc` matches.

---

## 6. Procedure — Spock replication for database `openvox_gui`

Do this **after** tables exist on the primary (section 5).  
Mirror your **PuppetDB Spock** mesh topology; only the **database name**
and **node names** change.

### 6.1 Grants for REPL_USER (every node, database `openvox_gui`)

```bash
# Replace REPL_USER with your real Spock replication role
sudo -u postgres "$PSQL" --no-psqlrc -d openvox_gui <<'SQL'
GRANT CONNECT ON DATABASE openvox_gui TO REPL_USER;
GRANT USAGE ON SCHEMA public TO REPL_USER;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO REPL_USER;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO REPL_USER;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT ON TABLES TO REPL_USER;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT ON SEQUENCES TO REPL_USER;
SQL
```

(If Spock needs broader rights on your build, match exactly what you used
for `puppetdb` — do not invent weaker grants that break apply.)

### 6.2 Extension (every node)

```bash
sudo -u postgres "$PSQL" --no-psqlrc -d openvox_gui \
  -c 'CREATE EXTENSION IF NOT EXISTS spock;'
```

### 6.3 Spock nodes (unique names per DB — do not reuse puppetdb node names)

On each ovdb host, **in database `openvox_gui`**, as superuser:

```sql
-- Example host IPs — use your inventory
-- ovdb1.pdxc  gui_n1
SELECT spock.node_create(
  node_name := 'gui_n1',
  dsn := 'host=OVDB1_IP dbname=openvox_gui user=REPL_USER password=SPOCK_REPL_PASS'
);

-- ovdb2.pdxc → gui_n2, ovdb ATLC1 → gui_n3, ovdb ATLC2 → gui_n4
```

Use the **same DSN style** as your working `puppetdb` Spock nodes
(host IP, SSL, etc.).

### 6.4 Replication set + tables (on primary after GUI schema exists)

```sql
-- On primary (gui_n1), database openvox_gui
SELECT spock.repset_add_all_tables('default', '{public}');
```

All OpenVox GUI tables are expected to have primary keys. If a table
without PK appears, fix the schema — do not invent a nopk set unless you
already did for PuppetDB.

### 6.5 Subscriptions (mesh)

Same pattern as Phase 7 for PuppetDB: each node subscribes to the other
three, **still connected to `dbname=openvox_gui`**, `set_names := '{default}'`.

Example shape (adjust names/DSNs):

```sql
SELECT spock.sub_create(
  subscription_name := 'gui_sub_from_n1',
  provider_dsn := 'host=OVDB1_IP dbname=openvox_gui user=REPL_USER password=…',
  replication_sets := '{default}',
  synchronize_structure := false,  -- structure already created / use true only if you know your playbook
  synchronize_data := true,
  forward_origins := '{}'
);
```

**Use the exact `spock.sub_create` / attach-repset calls from your
working PuppetDB runbook** — only change `dbname=openvox_gui` and
subscription/node names. Copy-paste from a known-good `puppetdb` session
is safer than inventing flags.

If your estate uses `synchronize_structure := true` for empty peers,
create empty DB + extension + node first, then sub_create once.

### 6.6 Verify replication

On primary: insert or update a test row in `enc_nodes` (or classify in UI).

On each peer:

```bash
sudo -u postgres $PSQL -d openvox_gui -c 'SELECT count(*) FROM enc_nodes;'
sudo -u postgres $PSQL -d openvox_gui -c \
  "SELECT * FROM spock.subscription;"   -- if available in your spock version
```

Row counts for ENC tables should match (allow brief lag).

### 6.7 GUI URL after Spock

- Still prefer **single writer endpoint** (primary or 5432 VIP).  
- After **site promote**, change VIP backend or update both consoles’
  `OPENVOX_GUI_DATABASE_URL` host to the new primary.

---

## 7. Acceptance tests

```bash
# 1. Both consoles same classify API
curl -sk "https://openvox.pdxc-it.corp.int-x.ai:4567/api/enc/classify/CERTNAME/yaml"
curl -sk "https://openvox.atlc-it.corp.int-x.ai:4567/api/enc/classify/CERTNAME/yaml"
# identical YAML

# 2. Both /enc UIs show same groups/nodes/classes

# 3. Compiler ENC matches console
# /etc/sysconfig/openvox-enc on compiler:
# OPENVOX_GUI_API_BASE=https://openvox.pdxc…:4567,https://openvox.atlc…:4567
set -a; . /etc/sysconfig/openvox-enc; set +a
/usr/local/bin/enc.py CERTNAME
# same YAML

# 4. Peer ovdb (if Spock on)
sudo -u postgres $PSQL -d openvox_gui -c 'SELECT count(*) FROM enc_nodes;'
```

---

## 8. Productization notes (install-time vs Clustered UI)

### Reality check

| Step | Can console `install.sh` do alone? |
|------|-------------------------------------|
| `CREATE ROLE` / `CREATE DATABASE` on ovdb | **No** without superuser DSN + network to :5432 |
| `pg_hba` / firewall on ovdb | **No** (infra / Puppet profile) |
| Spock node/sub mesh | **No** (DBA / existing Spock playbook) |
| Write `OPENVOX_GUI_DATABASE_URL` + `SECRET_KEY` | **Yes** |
| `alembic upgrade head` | **Yes** if URL works |
| Refuse dual-console + SQLite | **Yes** (already in Cluster UI) |
| Test classify equality both consoles | **Yes** |

So “fully automatic on install with zero DB admin” is only possible if
**infra already provisioned** the empty `openvox_gui` DB (or a one-time
bootstrap secret is supplied).

### Preference 1 — Install-time (recommended long-term)

**Infra / Puppet profile on ovdb** (this is the right place for “user
doesn’t deal with it”):

- Role `openvox_gui`, database `openvox_gui`, grants, hba snippets,
  firewall 5432 from console nets, Spock for `openvox_gui` after schema
  bootstrap — owned by control-repo profiles (same as PuppetDB).

**Console `install.sh` / install.conf:**

```bash
# install.conf.example additions (product)
# OPENVOX_GUI_DATABASE_URL=postgresql+asyncpg://openvox_gui:…@ovdb-pg-vip:5432/openvox_gui
# OPENVOX_GUI_SECRET_KEY=…   # must match peer console
# CONFIGURE_SHARED_DB=true   # run alembic + connectivity check; fail install if unreachable when clustered
```

Install behavior when URL is Postgres:

1. Probe connect with asyncpg.  
2. Run alembic.  
3. Do **not** invent SQLite.  
4. Print “peer console must use the same URL and SECRET_KEY”.  
5. Optional: if second console, health-check peer `/api/enc/classify/…` parity later.

Ship helper script (console-side only):

- `scripts/bootstrap-gui-db-check.sh` — verify DSN, print server version, list tables.  
- Never `CREATE DATABASE` unless `OPENVOX_GUI_DB_BOOTSTRAP_SUPERUSER_URL` is explicitly set (escape hatch).

### Preference 2 — Clustered mode in GUI

When operator selects **Settings → Cluster → Clustered**:

1. **Require** Postgres URL (reject SQLite) — already intended.  
2. Wizard fields: DB URL, confirm password, shared SECRET_KEY, console FQDNs.  
3. Actions the app **can** take with app credentials:  
   - save URL to `.env` / cluster secrets table  
   - alembic upgrade  
   - optional “import from local sqlite” once  
4. Actions the app **must not** claim to do without superuser:  
   - create role/DB on ovdb  
   - edit pg_hba  
   - build Spock mesh  
5. UI copy: “Database must already exist on ovdb (profile X). This wizard
   only attaches both consoles to it.”

Optional advanced: “Bootstrap DSN (superuser)” one-shot create DB — only
if security review accepts storing superuser use once.

### Preference 3 — Control-repo first (best ops fit)

Add to ovdb role/profile documentation:

```text
profiles::openvoxdb::gui_database   # or similar
  → database openvox_gui, role, hba, firewall
profiles::openvoxdb::gui_spock      # after first schema, repset + subs
```

Consoles get Hiera:

```yaml
openvox_gui::database_url: 'postgresql+asyncpg://…@ovdb-pg-vip:5432/openvox_gui'
```

Then install/Clustered only **consume** Hiera/env.

---

## 9. Order of operations (checklist)

| # | Where | Action |
|---|--------|--------|
| 1 | All ovdb | Role `openvox_gui` |
| 2 | All ovdb | Database `openvox_gui` empty |
| 3 | All ovdb | pg_hba + firewall for consoles |
| 4 | Consoles | Connect test to primary/VIP |
| 5 | One console | Point `.env` at Postgres, restart, alembic |
| 6 | One console | Load ENC data |
| 7 | Second console | Same `.env` + SECRET_KEY |
| 8 | All ovdb | Spock extension + nodes in `openvox_gui` |
| 9 | Primary | `repset_add_all_tables` |
| 10 | All peers | Subscriptions; verify counts |
| 11 | Compilers | `OPENVOX_GUI_API_BASE` both consoles; enc.py |
| 12 | Accept | Dual curl classify + compiler enc.py identical |

---

## 10. Common mistakes

| Mistake | Result |
|---------|--------|
| SQLite URL “identical” on two hosts | Two files, two ENCs |
| Tablespace instead of database | Wrong object; no shared app DB |
| Expect puppetdb Spock to copy GUI | Never happens |
| CREATE DATABASE only on ovdb1 then Spock without empty DB on peers | Sub create fails |
| GUI role can CONNECT to puppetdb | Security / support mess |
| Compilers pointed at Postgres VIP | Wrong layer; use HTTPS classify |
| Different SECRET_KEY on consoles | Encrypted secrets unreadable cross-site |

---

## 11. Summary for stakeholders

**Goal:** two geo consoles, one classification source of truth, compilers
and agents always see the same ENC.

**Mechanism:** database **`openvox_gui`** on the ovdb Postgres estate,
replicated with **Spock** (separate from `puppetdb`), consoles share one
DSN/VIP, compilers use **console HTTP API** (not SQL).

**Not:** a PostgreSQL tablespace, not Postgres on the GUI host long-term,
not automatic replication of a new database from PuppetDB’s Spock config alone.
