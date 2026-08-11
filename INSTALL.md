# Installation Guide

**OpenVox GUI Version 3.11.0-alpha.25**

This guide will walk you through installing OpenVox GUI on your server. Don't worry if you're new to this - we'll explain everything step by step!

## Table of Contents

1. [Before You Start](#before-you-start)
2. [Quick Installation (Recommended)](#quick-installation-recommended)
3. [Step-by-Step Installation](#step-by-step-installation)
4. [After Installation](#after-installation)
5. [Troubleshooting Installation](#troubleshooting-installation)
6. [Advanced Installation Options](#advanced-installation-options)
7. [Advanced Installations (Extra Large / Clustered Estates)](#advanced-installations-extra-large--clustered-estates)

---

## Before You Start

### What You Need

> **Important:** OpenVox GUI must be installed directly **on your OpenVox Server**. It requires local access to configuration files, SSL certificates, and system services to function. Remote installation on a separate host is not currently supported.

Think of these as the ingredients before you start cooking:

1. **Your OpenVox Server** — This is where you'll install OpenVox GUI
   - Red Hat 8 or newer, CentOS 8 or newer, Ubuntu 20.04 or newer
   - At least 2GB of memory (RAM)
   - About 1GB of free disk space
   - A working OpenVox Server and OpenVoxDB already installed and running on this machine

2. **Administrator Access**
   - You need to be able to run commands with `sudo` (administrator privileges)
   - You'll need to know the root password or have sudo access

### Checking Your Prerequisites

Let's make sure your server is ready. Run these commands:

```bash
# Check your operating system version
cat /etc/os-release

# Check Python is installed (need version 3.10 or newer)
python3 --version

# Check you have sudo access
sudo echo "I have sudo access!"

# Check you can reach your OpenVox Server (replace openvox.example.com with your server)
ping -c 2 openvox.example.com
```

If all these commands work without errors, you're ready to install!

### Network Requirements (Firewalls and Proxies)

The installer needs to download packages from the internet. If your server is behind a **corporate firewall or HTTP proxy**, you'll need to ensure the following endpoints are accessible.

#### Required Endpoints

| Endpoint | Port | Purpose |
|----------|------|---------|
| `pypi.org` | 443 | Python package index |
| `files.pythonhosted.org` | 443 | Python package downloads |
| `registry.npmjs.org` | 443 | Node.js package registry |
| `github.com` | 443 | Repository clone (if using git) |
| `raw.githubusercontent.com` | 443 | GitHub raw file access |
| `objects.githubusercontent.com` | 443 | GitHub release assets |

> **For enterprise environments:** Request these endpoints be allowlisted in your proxy or firewall before running the installer.

#### Proxy Configuration

**Most users do not use an HTTP proxy** and can skip this section entirely.
The installer defaults to direct connections (no proxy).

Only follow these steps if your server is behind a corporate proxy that
intercepts or requires outbound HTTP/HTTPS traffic.

If you do need a proxy, configure it **before** running the installer:

```bash
# Set proxy environment variables (adjust URL to your proxy)
export HTTP_PROXY="http://username:password@proxy.example.com:3128"
export HTTPS_PROXY="http://username:password@proxy.example.com:3128"
export http_proxy="$HTTP_PROXY"
export https_proxy="$HTTPS_PROXY"

# Optional: Skip proxy for local addresses
export NO_PROXY="localhost,127.0.0.1,.example.com"
export no_proxy="$NO_PROXY"
```

> **Important:** The proxy URL must include the scheme (`http://`). A URL like `proxy:3128` will fail — it must be `http://proxy:3128`.

**Common proxy error:**
```
ERROR: Could not install packages due to an OSError: Please check proxy URL.
It is malformed and could be missing the host.
```

This means your `HTTP_PROXY` or `HTTPS_PROXY` variable is missing the `http://` prefix. Fix it with:

```bash
# Wrong (missing scheme):
export HTTPS_PROXY="proxy.example.com:3128"

# Correct (with scheme):
export HTTPS_PROXY="http://proxy.example.com:3128"
```

#### Verifying Connectivity

Test that you can reach the required endpoints:

```bash
# Test PyPI access (Python packages)
curl -I https://pypi.org/simple/

# Test npm registry (Node.js packages)
curl -I https://registry.npmjs.org/

# Test GitHub access
curl -I https://github.com
```

If any of these fail with connection errors, work with your network team to allowlist the endpoints listed above.

---

## Quick Installation (Recommended)

This is the easiest way to install. The installer will ask you questions and use sensible defaults.

### Step 1: Download the Code

```bash
# Go to your home directory
cd ~

# Download OpenVox GUI from GitHub
git clone https://github.com/cvquesty/openvox-gui.git

# Go into the directory
cd openvox-gui
```

### Step 2: Run the Installer

```bash
# Run the installation script
sudo ./install.sh
```

### Step 3: Answer the Questions

The installer will ask you some questions. Here's what each one means:

1. **Install directory [/opt/openvox-gui]:** Where to install the software
   - Just press Enter to accept the default (recommended)

2. **Service user [puppet]:** Which Linux user will run the service
   - Just press Enter to use "puppet" (recommended)

3. **Application port [4567]:** Which network port to use
   - Just press Enter for 4567 (recommended)

4. **Enable SSL on port 4567? [false]:** Whether the GUI serves HTTPS directly
   - Type `y` to enable SSL using Puppet certs (or custom certs)
   - Just press Enter to keep HTTP (default)

5. **OpenVox Server hostname:** The name of your OpenVox server
   - Type the full name like `openvox.yourcompany.com`

6. **Admin password:** Password for the web interface
   - Type a secure password (or let it generate one for you)

7. **Configure local agent package mirror? [Y/n]:** *(3.6.0+)*
   - Sets up the OpenVox Agent Installer feature so you can bootstrap
     fresh agents with `curl -k --noproxy <server> https://<server>:8140/packages/install.bash | sudo bash`
   - Drops a static-content mount into puppetserver's `conf.d/` so the
     install scripts are served on port 8140
   - Installs a systemd timer for nightly mirror sync
   - Sets up automatic puppet-CA trust on agent hosts at install time
     so subsequent `apt-get update` / `dnf upgrade` work without
     `--insecure` / `Verify-Peer=false` flags
   - See [docs/INSTALLER.md](docs/INSTALLER.md) for the full feature guide

8. **Run initial sync now? [y/N]:** *(only if you said yes to #7)*
   - Downloads ~1-2 GB of OpenVox packages from voxpupuli.org and takes
     15-45 minutes
   - Default is **no** -- the systemd timer will populate the mirror
     overnight, or you can click "Sync now" later from the Installer page

### Step 4: Wait for Installation

The installer will show progress like this:

```
▸ Installing OpenVox GUI
  [1/11] Creating service user...           ✔
  [2/11] Creating directories...            ✔
  [3/11] Copying files...                   ✔
  ...
  [10/11] Agent Package Mirror...           ✔
  [11/11] Initial Setup & Launch...         ✔
```

This usually takes 2-5 minutes (longer if you opted to run the initial
agent-package sync).

### Step 5: Access the Web Interface

Once installation completes, you'll see:

```
═══════════════════════════════════════════════════════
  Installation Complete!
═══════════════════════════════════════════════════════
  
  Access URL:  https://your-server:4567
  Username:    admin
  Password:    (check /opt/openvox-gui/config/.credentials)
```

Open your web browser and go to the URL shown. You're done!

---

## Step-by-Step Installation

If you want more control or the quick installation didn't work, follow these detailed steps.

### Step 1: Prepare Your System

```bash
# Update your system packages
sudo yum update -y        # For Red Hat/CentOS
# OR
sudo apt update && sudo apt upgrade -y   # For Ubuntu/Debian

# Install required packages
sudo yum install -y python3 python3-pip git   # For Red Hat/CentOS
# OR
sudo apt install -y python3 python3-pip git    # For Ubuntu/Debian
```

### Step 2: Create a Service User

It's good practice to run services as a dedicated user:

```bash
# Create a user called 'openvox' (skip if using existing 'puppet' user)
sudo useradd -r -s /bin/false openvox
```

### Step 3: Download OpenVox GUI

```bash
# Create the installation directory
sudo mkdir -p /opt/openvox-gui

# Download the code
cd /opt
sudo git clone https://github.com/cvquesty/openvox-gui.git openvox-gui
```

### Step 4: Create a Configuration File

Instead of answering questions interactively, create a configuration file:

```bash
# Copy the example configuration
cd /opt/openvox-gui
sudo cp install.conf.example install.conf

# Edit the configuration
sudo nano install.conf   # or use vi, vim, or your favorite editor
```

Here's what to put in the file:

```bash
# Basic configuration for OpenVox GUI
INSTALL_DIR="/opt/openvox-gui"
SERVICE_USER="puppet"
APP_PORT="4567"

# Your OpenVox infrastructure
PUPPET_SERVER_HOST="openvox.yourcompany.com"    # Change this!
PUPPETDB_HOST="openvox.yourcompany.com"         # Usually same as OpenVox Server
# Dedicated console (GUI not on the CA): set the CA VIP. Do NOT install
# openvox-server / puppetserver on the console — the GUI uses the CA HTTP API.
# PUPPET_CA_HOST="ovca.example.com"

# Authentication
AUTH_BACKEND="local"
ADMIN_USERNAME="admin"
ADMIN_PASSWORD="YourSecurePassword123!"        # Change this!

# System settings
CONFIGURE_FIREWALL="true"    # Open the port in the firewall
CONFIGURE_SELINUX="true"      # Configure SELinux (Red Hat/CentOS)
```

### Step 5: Run the Installer with Your Configuration

```bash
# Run the installer using your configuration file
sudo ./install.sh --config install.conf
```

The installer will use your settings and won't ask any questions.

### Step 6: Verify the Installation

```bash
# Check the service is running
sudo systemctl status openvox-gui

# Check you can reach the web interface
curl -k https://localhost:4567/health
```

You should see `{"status":"ok","version":"3.11.0-alpha.25"}` if everything is working.

---

## After Installation

### First Login

1. Open your web browser
2. Go to `https://your-server-name:4567` (replace with your actual server name)
3. You might see a certificate warning - this is normal, click "Advanced" and "Proceed"
4. Log in with:
   - Username: `admin`
   - Password: The one you set, or check `/opt/openvox-gui/config/.credentials`

### The `ovox` CLI (Installed Automatically)

`ovox` is a **first-class subsystem** of OpenVox GUI (not an add-on). It is installed automatically:

- Real binary: `/opt/openvox-gui/venv/bin/ovox`
- Symlinked for convenience (Puppet/OpenVox convention): `/usr/local/bin/ovox`

It is available for both local server use and remote administration against any OpenVox GUI instance.

```bash
ovox --help
ovox login
ovox status
ovox infra health
ovox token generate --user bolt --name "Bolt service token" --expires 0
```

Full documentation: [ovox/README.md](ovox/README.md)

### Important First Steps

1. **Change the default password immediately:**
   - Click your username in the top-right corner
   - Go to Settings → Users
   - Change the admin password

2. **Add more users if needed:**
   - Go to **Settings** → **User Manager** to create users via the web interface
   - Choose **LDAP** or **Local** as the authentication source for each user
   - Or use the CLI:
     ```bash
     sudo /opt/openvox-gui/venv/bin/python /opt/openvox-gui/scripts/manage_users.py add john --role operator
     ```

3. **Set up LDAP authentication** (optional):
   - Go to **Settings** → **Auth Settings** to connect to your LDAP/Active Directory server
   - See the [LDAP / Active Directory Guide](docs/LDAP.md) for detailed setup instructions

4. **Configure your firewall** (if not done automatically):
   ```bash
   # For Red Hat/CentOS:
   sudo firewall-cmd --permanent --add-port=4567/tcp
   sudo firewall-cmd --reload
   
   # For Ubuntu (if using UFW):
   sudo ufw allow 4567/tcp
   ```

5. **Configure SSL Certificates** (if using HTTPS):
   - Go to **Settings** → **Application Configuration** → **SSL Configuration**
   - The **SSL Certificate Wizard** guides you through the entire process:
     - **Organization Certificate**: upload cert files from your IT/security team
       with drag-and-drop. The wizard validates files, checks key-cert match,
       and installs them automatically.
     - **Let's Encrypt**: renew certs via built-in certbot integration.
     - **Puppet Certificates**: one-click reuse of OpenVox Server's own certs.
   - The page shows real-time certificate health (expiry, key type, chain status)
   - For enterprise environments, use **Configure Puppet CA** to set up an
     intermediate CA that chains to your corporate PKI.

6. **Enable full Metrics data (highly recommended)**:
   - By default many Metrics pages (Run Performance, PuppetDB Health,
     OpenVox Server Health) will be empty or very limited.
   - You must configure Puppet Server authorization and metrics reporting.
   - **See the dedicated guide**: [docs/METRICS.md](docs/METRICS.md)
   - This involves three files:
     - `puppetserver.conf` (http-client metrics)
     - `metrics.conf` (JMX)
     - `auth.conf` (allow the GUI's mTLS client to reach `/metrics` and `/status`)
   - After changes: `sudo systemctl restart puppetserver puppetdb openvox-gui`
   - You can edit these files from **Settings → Application Configuration** in the GUI.

### Starting and Stopping the Service

```bash
# Stop the service
sudo systemctl stop openvox-gui

# Start the service
sudo systemctl start openvox-gui

# Restart the service
sudo systemctl restart openvox-gui

# Check the status
sudo systemctl status openvox-gui

# View the logs
sudo journalctl -u openvox-gui -f
```

---

## Troubleshooting Installation

### Common Problems and Solutions

#### Problem: "Permission denied" when running install.sh

**Solution:** Make sure you're using sudo:
```bash
sudo ./install.sh   # Correct
./install.sh        # Wrong - needs sudo
```

#### Problem: "Python 3.8+ is required"

**Solution:** Install or update Python:
```bash
# Red Hat/CentOS 8:
sudo yum install -y python38

# Ubuntu 20.04 already has Python 3.8
# For older Ubuntu:
sudo apt install -y python3.8
```

#### Problem: "Cannot connect to OpenVoxDB"

**Solution:** Check your network and certificates:
```bash
# Can you reach OpenVoxDB?
ping openvoxdb.yourcompany.com

# Is OpenVoxDB port open?
telnet openvoxdb.yourcompany.com 8081

# Do you have the right SSL certificates?
ls -la /etc/puppetlabs/puppet/ssl/certs/
```

#### Problem: "Port 4567 is already in use"

**Solution:** Either stop the other service or use a different port:
```bash
# See what's using port 4567
sudo ss -tlnp | grep 4567

# Use a different port in your configuration
APP_PORT="8567"   # Or any free port
```

#### Problem: "Could not install packages due to an OSError: Please check proxy URL"

**Solution:** Your proxy environment variable is malformed. It must include `http://`:

```bash
# Check current proxy settings
env | grep -i proxy

# Fix: Add http:// prefix if missing
export HTTP_PROXY="http://your-proxy:3128"
export HTTPS_PROXY="http://your-proxy:3128"
export http_proxy="$HTTP_PROXY"
export https_proxy="$HTTPS_PROXY"

# Then re-run the installer
sudo -E ./install.sh   # -E preserves environment variables
```

**Note on "Proxy: none detected"**

During installation you may see messages like "No proxy configured" or
nothing at all about proxies. This is **normal** when you are not behind
a proxy. The installer deliberately stays quiet in the no-proxy case.
"Proxy: none detected" is an old message that has been removed in favor
of silence for direct-connection installs.
```

See [Network Requirements](#network-requirements-firewalls-and-proxies) for full proxy configuration details.

#### Problem: Web interface shows "This site can't be reached"

**Solution:** Check if the service is running and the firewall is open:
```bash
# Is the service running?
sudo systemctl status openvox-gui

# Is the firewall blocking it?
sudo firewall-cmd --list-ports    # Red Hat/CentOS
sudo ufw status                    # Ubuntu

# Check the logs for errors
sudo journalctl -u openvox-gui -n 50
```

### Getting More Help

If you're still stuck:

1. Check the detailed logs:
   ```bash
   sudo journalctl -u openvox-gui -n 100 --no-pager
   ```

2. Look for error messages during installation:
   ```bash
   sudo ./install.sh 2>&1 | tee install.log
   # Then examine install.log for errors
   ```

3. Visit our [Troubleshooting Guide](TROUBLESHOOTING.md)

4. Ask for help on [GitHub Issues](https://github.com/cvquesty/openvox-gui/issues)

---

## Advanced Installation Options

### Unattended Installation

Install without any prompts using all defaults:

```bash
sudo ./install.sh --unattended
```

This will:
- Install to `/opt/openvox-gui`
- Use port 4567
- Auto-detect your OpenVox server
- Generate a random admin password (saved to `/opt/openvox-gui/config/.credentials`)

### Custom Installation Directory

Install to a different location:

```bash
sudo ./install.sh --install-dir /srv/openvox-gui
```

### Behind a Reverse Proxy (nginx/Apache)

If you want to run OpenVox GUI behind nginx or Apache:

**Maintenance pages (automatic during install)**: The installer now automatically enables the holistic maintenance program. Branded static "Under Maintenance" pages (Formal/Casual themes) are copied to `/opt/openvox-gui/maintenance/`. If Apache is configured with the recommended `RewriteCond` on `/opt/openvox-gui/data/maintenance.flag` + `Alias` to the HTML (see `maintenance/apache-maintenance.conf` and `maintenance/README.md`), web users will see the nice branded page instead of errors while files are laid down and the service (re)starts. The flag is automatically raised early and removed via trap on exit. Use `ovox maintenance status/enable/disable` for manual control or rich details. See `maintenance/README.md` for the full program, Apache setup, and troubleshooting.

If you want to run OpenVox GUI behind nginx or Apache:

1. Configure OpenVox GUI to listen only on localhost (example for IPv4):
   ```bash
   APP_HOST="127.0.0.1"    # Only accessible locally (use ::1 for IPv6 localhost)
   APP_PORT="4567"
   ```

   For dual-stack on the backend (recommended in most cases):
   ```bash
   APP_HOST="::"
   ```

2. Configure nginx to proxy requests (dual-stack listener example):
   ```nginx
   server {
       listen 443 ssl;
       listen [::]:443 ssl;
       server_name openvox.yourcompany.com;
       
       ssl_certificate /path/to/cert.pem;
       ssl_certificate_key /path/to/key.pem;
       
       location / {
           proxy_pass http://localhost:4567;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
       }
   }
   ```

### High-Performance Installation

For large deployments (100+ nodes), use more workers:

```bash
# In your install.conf:
UVICORN_WORKERS="8"    # For a 4-CPU server
```

### Development Installation

For development/testing without authentication:

```bash
# WARNING: No password required - anyone can access!
AUTH_BACKEND="none"
APP_DEBUG="true"
UVICORN_WORKERS="1"
```

**⚠️ Never use AUTH_BACKEND="none" in production!**

### Uninstalling

To completely remove OpenVox GUI:

```bash
# This will remove everything
sudo ./install.sh --uninstall

# To keep data but remove the service:
sudo ./install.sh --uninstall --keep-data
```

---

## Next Steps

Now that you have OpenVox GUI installed:

1. **Read the User Guide** to learn how to use all the features
2. **Configure Your Settings** in the web interface under Settings
3. **Set Up Regular Backups** of `/opt/openvox-gui/data/`
4. **Check for Updates** regularly - see the [Update Guide](UPDATE.md)

---

## Advanced Installations (Extra Large / Clustered Estates)

> **Most sites stop here.** The standard install places OpenVox GUI on a single OpenVox Server host. That model is intentional, well-supported, and sufficient for the large majority of environments (roughly **90%+** of deployments).
>
> This section is for **extra large** estates—many catalog compilers, multi-node OpenVoxDB, site-loss resilience, or multi–data-center designs—where OpenVox GUI’s **clustered** features become useful. It describes **capabilities, design philosophy, and workflow**, not a full multi-DC build runbook.

### Philosophy of operation

| Principle | What it means |
|-----------|----------------|
| **Singleton first** | Ship and operate a single-server GUI by default. Operators should not see multi-host knobs until they choose them. |
| **Opt-in clustered mode** | A explicit **Settings → Cluster** switch turns on multi-server awareness. Until then, the product behaves as a classic one-box console. |
| **GUI is not the control plane fabric** | Compilers, OpenVoxDB mesh, and CA HA are **infrastructure** concerns. OpenVox GUI observes, configures, deploys, and classifies—it does not replace Pacemaker, Spock, or your load balancers. |
| **FQDN over VIP for member health** | When checking individual machines, probe **each host’s FQDN** (compiler :8140, OpenVoxDB :8081, CA members :8140). VIPs answer “is the service reachable?”; FQDNs answer “is **this** member healthy?” |
| **Same moment, same code** | In multi-compiler estates, code must not go live on one compiler minutes before another. Clustered **stage → activate** is about aligning that cutover. |
| **Classification segments roles** | Compilers and OpenVoxDB hosts are fleet members too. ENC groups such as **Puppet Compiler** and **PuppetDB** keep roles visible and manageable without inventing a second inventory system. |

### Basic design (conceptual)

```text
                         Agents / operators
                                |
              +-----------------+------------------+
              |                                    |
     Compiler VIP (HAProxy)              OpenVoxDB VIP (HAProxy)
              |                                    |
     +--------+--------+                  +--------+--------+
     |                 |                  |                 |
  compiler1 …     compilerN           ovdb1 …           ovdbN
     |                 |                  |                 |
     +-------- OpenVox GUI (operator console) --------+
                       |
              Settings → Cluster (opt-in)
                       |
         health by FQDN · stage/activate · ENC groups
```

**Typical extra-large building blocks** (you already design these outside the GUI installer):

- **Multiple catalog compilers** behind a TCP load balancer (pass-through TLS).
- **Multiple OpenVoxDB / PostgreSQL hosts** with multi-master or multi-site data strategy, fronted by a VIP for clients.
- **CA high availability** (shared CA data, fencing, floating VIP)—GUI may report Pacemaker/DRBD **primary** and VIP placement when `pcs` (or Bolt to a CA node) is available.
- **One OpenVox GUI** installation (still co-located with local access to Puppet paths today), configured for **clustered** mode so operators can see and drive the multi-node estate.

OpenVox GUI does **not** currently replace a dedicated multi-site architecture engagement. Use this product surface to **operate** a design you already own.

### Expected sizing (guidance, not a quote)

These ranges are **planning heuristics**. Real capacity depends on agent count, catalog complexity, report retention, compile concurrency, and geography.

| Scale band | Rough agent order | Compilers (typical) | OpenVoxDB / PG | Notes |
|------------|-------------------|---------------------|----------------|-------|
| Small / standard | up to low thousands | 1 (GUI co-located) | 1 | Default OpenVox GUI install |
| Medium | thousands–tens of thousands | 2+ behind LB | 1–2 | Cluster mode optional |
| **Extra large** | tens–hundreds of thousands | N behind VIP(s), often multi-site | Multi-node mesh / multi-site | Cluster mode recommended in GUI; architecture review strongly advised |
| Multi-DC / site-loss | as above + geo | Compilers per site + global DNS policy | Multi-site DB + promote story | Beyond “turn on a switch”—design before tooling |

For OpenVox GUI itself on the console host: more **UVICORN_WORKERS** (see High-Performance Installation above) helps the web tier; it does not replace compiler or database capacity.

### Capabilities of a clustered environment (what the GUI can do)

When **Settings → Cluster** is set to **clustered**, OpenVox GUI can:

1. **Record estate topology**  
   Compiler FQDNs, OpenVoxDB application host FQDNs, optional CA members and CA VIPs, and code-deploy targets.

2. **Health by member, not only VIP**  
   - Compilers: Puppet Server status APIs on each FQDN (`:8140`).  
   - OpenVoxDB: status, services, version meta, and a lightweight query probe on each FQDN (`:8081`).  
   - CA: status/services (and certificate endpoint) on CA members and optional VIPs.  
   - **CA HA snapshot** (when available): Pacemaker online/offline, resource map, **which node is Promoted (primary)**, VIP placement, optional DRBD text—via local `pcs` or Bolt to a configured CA host.

3. **Code deployment for many servers**  
   - Configure multiple deploy targets (usually compilers).  
   - **Stage** code into a staging codedir on all targets.  
   - **Activate** staged code to the live codedir so cutover is coordinated across the set (Bolt when inventory exists).  
   - Single-host “Deploy Now” remains for classic r10k on the local box.

4. **Classification segmentation**  
   Seeded ENC groups such as **Puppet Compiler** and **PuppetDB**, with configured FQDNs attached, so infrastructure roles are first-class in **Classification and Code → Classification**.

5. **What stays out of scope for this document**  
   Full multi-DC bootstrap, DRBD/Pacemaker recipes, Spock mesh procedures, and VIP/SAN design deep-dives are **not** reproduced here. Those are infrastructure projects; the GUI assumes that foundation exists or is being built under separate design work.

### Basic operator workflow (clustered GUI)

This is the **console workflow**, not a green-field build checklist.

1. **Install OpenVox GUI** the normal way on the host that has appropriate local access (see earlier sections).  
2. **Operate single-server** until compilers, DB, and CA topology are real and healthy.  
3. Open **Settings → Cluster**, switch **Deployment mode** to **Clustered**, and enter:
   - Compiler FQDNs  
   - OpenVoxDB node FQDNs  
   - CA member FQDNs (and optional CA VIPs)  
   - Optional explicit code-deploy targets  
4. Save—optionally seeding **Puppet Compiler** / **PuppetDB** ENC groups.  
5. Use **Settings → Services** to review local units **and** per-FQDN member health / HA primary.  
6. Use **Code Deployment** for local deploy, or **Stage** then **Activate** when multiple targets must cut over together.  
7. Use **Classification** to manage group membership and classes for infrastructure roles.

If Cluster mode is left at **Single server**, multi-host panels and stage/activate stay out of the way.

### When to call for design help

Extra large and multi-site OpenVox estates mix capacity planning, HA fencing, certificate SANs/VIPs, database multi-master policy, and change management. The GUI features above make day-2 operation safer **after** that design is solid.

For architecture review, multi-site OpenVox, or a formal “extra large installation” engagement—beyond what community docs and this product alone provide—contact:

**S & S Consulting Group (SSCG)**  
Specialists in Puppet and OpenVox platform engineering  

| | |
|--|--|
| **Web** | [ssconsultinggroup.net](https://ssconsultinggroup.net) |
| **Email** | [info@ssconsultinggroup.net](mailto:info@ssconsultinggroup.net) |
| **Phone** | [912-549-0272](tel:+19125490272) |

A more detailed advanced installation example may be published in a later OpenVox GUI release; until then, treat multi-DC build procedures as a separate engagement, not as something the installer automates.

### Migration stance (extra large / new cluster)

Typical path for an existing singleton (or smaller) production estate:

1. **Stand up** the new multi-server OpenVox + GUI (3.11+ clustered) environment separately.  
2. **Migrate agents and roles** onto that estate (compilers, OpenVoxDB, CA policy as designed).  
3. **Do not** require a big-bang “upgrade the old production box to clustered 3.11 in place.”  
4. After migration, **repurpose the former production OpenVox host(s)** as a **development / lab instance** (lower risk experiments, GUI alpha trains, training).

That keeps production stable on a known 3.10.x line until agents are moved, then gives you a permanent internal machine for ongoing OpenVox GUI and platform development.

---

**Need help with a standard install?** Check the [Troubleshooting Guide](TROUBLESHOOTING.md) or visit our [GitHub page](https://github.com/cvquesty/openvox-gui).

**Need help with an extra large or multi-site design?** Contact **SSCG** using the details above.

---

<div align="center">

<sub>This document was created with the assistance of AI (Grok, xAI). All technical content has been reviewed and verified by human contributors.</sub>

</div>
