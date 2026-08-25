# Estate health — clustered OpenVox (VIPs stay)

Run this on **each console** after install and whenever Play, Nodes, or
Overview disagree.

```bash
sudo /opt/openvox-gui/scripts/estate-health-check.sh
sudo /opt/openvox-gui/scripts/cluster-preflight.sh
```

On **each ovdb member** (not the VIP name):

```bash
sudo /opt/openvox-gui/scripts/ensure-puppetdb-spock.sh
```

Reads use the OpenVoxDB DNS RR (`ovdb.example.com`). **Compiler writes**
use a single primary (n1 first, n2 failover, `command_broadcast = false`).
Spock on database **puppetdb** copies n1 → n2/n3/n4. That mesh does not
copy database **openvox_gui**. Do not treat four-way DNS RR as a write
fan-out. Full setup: [CLUSTERED_SHARED_DB.txt](CLUSTERED_SHARED_DB.txt).

| VIP | Role | Hide on Nodes? |
|-----|------|----------------|
| `ovdb.example.com` | OpenVoxDB read/write RR (`.78` per site → `.76`/`.77` members) | Yes (DNS only) |
| `ovca.example.com` | CA | Yes (DNS only) |
| `ovcompilers.<site>-it.…` | HAProxy VM + agent | **No** |

GUI `OPENVOX_GUI_PUPPETDB_HOST=ovdb.example.com` is the clustered **read**
end state, only when every A record’s `/pdb/query/v4/nodes` count
matches (preflight). Compilers stay on `server_urls` n1, n2.

Do **not** put `ovdb.example.com` in `/etc/hosts`. Members may be in hosts;
the VIP FQDN must come from DNS.

## Bolt (Play button)

Play is `bolt@` from **this console** → SSH → `sudo` on the target.
Root `puppet agent -tv` on the target does not prove Play.

1. `profiles::base::bolt_user` on **every** agent (authorized_keys =
   **both** console public keys).
2. This console: `/etc/puppetlabs/bolt/id_bolt`, inventory
   `host-key-check: false` (see `bolt-plugin/inventory.yaml.example`)
   **or** seed keys:

   ```bash
   sudo /opt/openvox-gui/scripts/seed-bolt-known-hosts.sh
   ```

3. ENC plugin: `openvox_enc` under `/etc/puppetlabs/bolt/modules/`,
   inventory `_plugin: openvox_enc`, GUI up on `:4567`.

   ```bash
   sudo -u bolt -H /opt/puppetlabs/bolt/bin/bolt inventory show \
     -i /opt/openvox-gui/data/bolt-inventory.estate.yaml \
     --project /etc/puppetlabs/bolt --format json
   curl -sk https://127.0.0.1:4567/api/enc/inventory/bolt | head
   ```

`HOST_KEY_ERROR` = missing `known_hosts` or `host-key-check: true`.
Not Puppet. Not “write a different ovdb.”

## OpenVoxDB consistency (stay on the VIP)

`/nodes` (what the GUI shows) follows **catalogs**, not SQL
`INSERT` into `certnames`. Compiler `puppetdb.conf` should be:

```ini
server_urls = https://ovdb1.site-a.example.com:8081,https://ovdb2.site-a.example.com:8081
command_broadcast = false
```

Spock must copy `catalogs` / `factsets` / `certnames` (`default`) and
`edges` (`pdb_nopk`). `repl_user` needs
`pg_replication_origin_*` EXECUTE (`ensure-puppetdb-spock.sh`).
Never `sub_resync_table` on `certnames`.

Until preflight is green, Overview **status** can still differ by
which `.78` stored the last **report**. Membership should already
match. Put `reports` in `default` when the table has a PK; otherwise
a new agent run against the site VIP is enough once apply works.

Do **not** point `OPENVOX_GUI_PUPPETDB_HOST` at `ovdb1.*` except as a
temporary read while you repair Spock. Putting it back on
`ovdb.example.com` is the clustered end state.

## What “healthy” looks like

- `estate-health-check.sh` **PASS** on **both** consoles
- `/nodes` count **equal** on every ovdb member and both site VIPs
  (see [CLUSTERED_SHARED_DB.txt](CLUSTERED_SHARED_DB.txt))
- Play on an ATLC name from the **PDXC** console succeeds (and the reverse)
- `bolt inventory show` lists ENC groups or estate targets without `_error`
