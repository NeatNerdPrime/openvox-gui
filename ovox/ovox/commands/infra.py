"""
`ovox infra` command group — Infrastructure health and tuning.

This group provides tools to monitor and tune the core OpenVox
infrastructure components (Puppet Server / OpenVox Server and
PuppetDB / OpenVoxDB).

Inspired by Puppet Enterprise's `puppet infrastructure tune` but
designed for the open source OpenVox stack.
"""

from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.json import JSON
from rich.panel import Panel

from ..client import OvoxAPIError, get_client

console = Console()

app = typer.Typer(
    help="OpenVox infrastructure health, recommendations, and automated tuning",
    no_args_is_help=True,
)


@app.command("health")
def health(
    ctx: typer.Context,
    component: Optional[str] = typer.Option(
        None,
        "--component",
        "-c",
        help="Limit to a specific component (puppetserver, puppetdb, all)",
    ),
    json_output: bool = typer.Option(False, "--json", "-j"),
):
    """
    Check the health of OpenVox infrastructure components.

    Reports systemd status for puppetserver, puppetdb, puppet agent,
    and the OpenVox GUI service itself.
    """
    client = get_client(
        base_url=ctx.obj.get("url") if ctx.obj else None,
        token=ctx.obj.get("token") if ctx.obj else None,
        verify_ssl=ctx.obj.get("verify_ssl", True) if ctx.obj else True,
    )

    try:
        # Prefer dedicated infra health (cluster-aware). Fall back to config/services.
        try:
            payload = client.get("/api/infra/health")
        except OvoxAPIError:
            payload = client.get("/api/config/services")
    except OvoxAPIError as exc:
        console.print(f"[red]Failed to fetch service health:[/red] {exc}")
        raise typer.Exit(1)

    if json_output or (ctx.obj and ctx.obj.get("output") == "json"):
        import json
        console.print(JSON(json.dumps(payload, indent=2)))
        return

    # Normalize list of service rows from either API shape
    if isinstance(payload, list):
        services = payload
        mode = "single"
        overall = None
    else:
        services = (
            payload.get("services")
            or payload.get("components")
            or []
        )
        mode = payload.get("deployment_mode") or "single"
        overall = payload.get("status")

    title = "OpenVox Infrastructure Health"
    if mode == "clustered":
        title += " (clustered)"
    if overall:
        title += f" — {overall}"

    table = Table(title=title)
    table.add_column("Role", style="cyan")
    table.add_column("Kind", style="dim")
    table.add_column("Host", style="white")
    table.add_column("Status", style="green")
    table.add_column("Details", style="dim")

    # Prefer components (richer) over flat services
    if isinstance(payload, dict) and payload.get("components"):
        row_src = payload["components"]
    else:
        row_src = services if isinstance(services, list) else []

    for svc in row_src:
        if not isinstance(svc, dict):
            continue
        name = svc.get("service") or svc.get("component") or svc.get("name") or "unknown"
        role = str(svc.get("role") or name.split(":")[0] if ":" in str(name) else name)
        kind = str(svc.get("kind") or ("vip" if "vip" in role else "member"))
        status = str(svc.get("status") or "unknown")
        host = str(svc.get("host") or "")
        if ":" in str(name) and not host:
            host = str(name).split(":", 1)[-1]

        details_parts = []
        if svc.get("source"):
            details_parts.append(str(svc["source"]))
        if svc.get("memory") and str(svc["memory"]) not in ("", "0"):
            details_parts.append(f"mem={svc['memory']}")
        if svc.get("since"):
            details_parts.append(str(svc["since"])[:19])
        if svc.get("error"):
            details_parts.append(f"error: {svc['error']}")
        if svc.get("detail") and not svc.get("error"):
            details_parts.append(str(svc["detail"])[:80])

        details = " | ".join(details_parts) if details_parts else ""

        blob = f"{name} {role} {host} {kind}".lower()
        if component and component.lower() not in blob:
            continue

        st_l = status.lower()
        color = "green" if st_l in ("active", "running", "ok") else (
            "yellow" if st_l in ("degraded", "unknown") else "red"
        )
        table.add_row(
            role,
            kind,
            host[:48],
            f"[{color}]{status}[/{color}]",
            str(details)[:60],
        )

    if not table.rows:
        console.print("[yellow]No matching components found.[/yellow]")
        if isinstance(payload, dict) and payload.get("warnings"):
            for w in payload["warnings"]:
                console.print(f"[dim]warning: {w}[/dim]")
    else:
        console.print(table)

    if isinstance(payload, dict):
        summary = payload.get("summary") or {}
        if summary:
            console.print()
            console.print(
                f"[dim]compilers {summary.get('compilers_healthy', '?')}/"
                f"{summary.get('compilers_total', '?')}"
                f" (+vip {summary.get('compiler_vips_healthy', '?')}/"
                f"{summary.get('compiler_vips_total', '?')}) · "
                f"puppetdb {summary.get('puppetdb_healthy', '?')}/"
                f"{summary.get('puppetdb_total', '?')}"
                f" (+vip {summary.get('puppetdb_vips_healthy', '?')}/"
                f"{summary.get('puppetdb_vips_total', '?')}) · "
                f"ca {summary.get('ca_healthy', '?')}/"
                f"{summary.get('ca_total', '?')}"
                f" (+vip {summary.get('ca_vips_healthy', '?')}/"
                f"{summary.get('ca_vips_total', '?')})[/dim]"
            )
        inv = payload.get("inventory") or {}
        if inv and not inv.get("compilers") and inv.get("compiler_vips"):
            console.print(
                "[yellow]Hint:[/yellow] only compiler VIPs are configured — "
                "add member FQDNs (ovcompiler1, ovcompiler2, …) in "
                "Settings → Cluster → compilers."
            )
        for w in payload.get("warnings") or []:
            console.print(f"[yellow]warning:[/yellow] {w}")

    console.print()
    console.print(Panel.fit(
        "Run [bold]ovox infra settings show[/bold] to see current tuning values.\n"
        "Run [bold]ovox infra recommend[/bold] for tuning suggestions.\n"
        "[dim]Health lists each estate member and each VIP from cluster "
        "config + OPENVOX_GUI_* hosts. Fill compilers/puppetdb_nodes/ca_nodes "
        "with real FQDNs (VIPs go in ca_vips / infra_vips / .env).[/dim]",
        title="Next Steps",
        border_style="blue"
    ))


@app.command("recommend")
def recommend(
    ctx: typer.Context,
    server: bool = typer.Option(False, "--server", help="Only show recommendations for OpenVox Server / Puppet Server"),
    db: bool = typer.Option(False, "--db", "--puppetdb", help="Only show recommendations for OpenVoxDB / PuppetDB"),
    json_output: bool = typer.Option(False, "--json", "-j"),
):
    """
    Show tuning recommendations without applying any changes.

    By default shows recommendations for both server and database.
    Use --server or --db to limit the scope.
    """
    component = None
    if server:
        component = "server"
    elif db:
        component = "db"

    client = get_client(
        base_url=ctx.obj.get("url") if ctx.obj else None,
        token=ctx.obj.get("token") if ctx.obj else None,
        verify_ssl=ctx.obj.get("verify_ssl", True) if ctx.obj else True,
    )

    try:
        data = client.get("/api/infra/tune/recommendations", params={"component": component} if component else {})
    except OvoxAPIError:
        data = _local_tune_recommendations(client, component)

    if json_output or (ctx.obj and ctx.obj.get("output") == "json"):
        import json
        console.print(JSON(json.dumps(data, indent=2)))
        return

    _render_tune_recommendations(data, component)


@app.command("tune")
def tune(
    ctx: typer.Context,
    server: bool = typer.Option(False, "--server", help="Only tune OpenVox Server / Puppet Server"),
    db: bool = typer.Option(False, "--db", "--puppetdb", help="Only tune OpenVoxDB / PuppetDB"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be done without making changes"),
    json_output: bool = typer.Option(False, "--json", "-j"),
):
    """
    Apply recommended tuning settings for OpenVox Server and/or OpenVoxDB.

    This will:
      1. Create timestamped backups of the relevant configuration files
      2. Apply the recommended changes
      3. Restart the affected service(s) automatically

    Use --dry-run to preview changes without applying them.
    """
    component = None
    if server:
        component = "server"
    elif db:
        component = "db"

    client = get_client(
        base_url=ctx.obj.get("url") if ctx.obj else None,
        token=ctx.obj.get("token") if ctx.obj else None,
        verify_ssl=ctx.obj.get("verify_ssl", True) if ctx.obj else True,
    )

    try:
        data = client.get("/api/infra/tune/recommendations", params={"component": component} if component else {})
    except OvoxAPIError:
        data = _local_tune_recommendations(client, component)

    if json_output or (ctx.obj and ctx.obj.get("output") == "json"):
        import json
        console.print(JSON(json.dumps(data, indent=2)))
        return

    _render_tune_recommendations(data, component)

    if dry_run:
        console.print("\n[yellow]Dry run — no changes will be made.[/yellow]")
        return

    if not typer.confirm("\nApply these recommendations? This will back up configs and restart services.", default=False):
        console.print("[yellow]Aborted.[/yellow]")
        raise typer.Exit(0)

    _apply_tuning(client, data, component, dry_run=False)


# Convenience alias so users can do "ovox infra set ..." directly
@app.command("set", help="Shortcut for 'settings set' (direct configuration changes)")
def infra_set_alias(
    ctx: typer.Context,
    key: str = typer.Argument(...),
    value: str = typer.Argument(...),
    dry_run: bool = typer.Option(False, "--dry-run"),
    yes: bool = typer.Option(False, "--yes", "-y"),
):
    """Direct alias for `ovox infra settings set`."""
    settings_set(ctx, key, value, dry_run=dry_run, yes=yes)


# ─────────────────────────────────────────────────────────────────────────────
# Settings subcommand group (read + write)
# ─────────────────────────────────────────────────────────────────────────────

settings_app = typer.Typer(
    help="View and directly modify infrastructure tuning settings (including JVM)"
)
app.add_typer(settings_app, name="settings")


@settings_app.command("show")
def settings_show(
    ctx: typer.Context,
    server: bool = typer.Option(False, "--server", help="Show settings for OpenVox Server / Puppet Server"),
    db: bool = typer.Option(False, "--db", "--puppetdb", help="Show settings for OpenVoxDB / PuppetDB"),
    json_output: bool = typer.Option(False, "--json", "-j"),
):
    """
    Display current key infrastructure tuning settings (including JVM configuration).

    This is the primary way to inspect what is actually configured right now.
    """
    client = get_client(
        base_url=ctx.obj.get("url") if ctx.obj else None,
        token=ctx.obj.get("token") if ctx.obj else None,
        verify_ssl=ctx.obj.get("verify_ssl", True) if ctx.obj else True,
    )

    try:
        data = client.get("/api/infra/settings", params={"component": "server" if server else ("db" if db else None)})
    except OvoxAPIError as exc:
        console.print(f"[red]Failed to fetch settings:[/red] {exc}")
        raise typer.Exit(1)

    if json_output or (ctx.obj and ctx.obj.get("output") == "json"):
        import json
        console.print(JSON(json.dumps(data, indent=2)))
        return

    def _jvm_field(jvm: dict, *keys, default="—"):
        jvm = jvm or {}
        for k in keys:
            v = jvm.get(k)
            if v not in (None, "", "None", "null"):
                return v
        return default

    def _val(v, default="—"):
        if v in (None, "", "None", "null"):
            return default
        return v

    mode = data.get("deployment_mode") or ""
    if mode:
        console.print(f"[dim]deployment_mode={mode}[/dim]")
    if data.get("note"):
        console.print(f"[dim]{data['note']}[/dim]")

    if server or not db:
        ps = data.get("puppetserver", {}) or {}
        jvm = ps.get("jvm", {}) or {}
        src = ps.get("source") or "local"
        host = ps.get("source_host") or ""
        title = "Puppet Server Settings"
        if host:
            title += f" (@ {host})"
        elif src:
            title += f" ({src})"
        console.print(Panel.fit(
            f"[bold]Puppet Server[/bold]\n"
            f"  JRuby max active instances : {_val(ps.get('jruby_max_active_instances'))}\n"
            f"  JVM heap (min)             : {_jvm_field(jvm, 'heap_min', 'xms')}\n"
            f"  JVM heap (max)             : {_jvm_field(jvm, 'heap_max', 'xmx')}\n"
            f"  Reserved Code Cache        : {_jvm_field(jvm, 'reserved_code_cache')}\n"
            f"  Source                     : {src}"
            + (f" / {host}" if host else ""),
            title=title,
            border_style="cyan",
        ))

    if db or not server:
        pdb = data.get("puppetdb", {}) or {}
        pools = pdb.get("pools", {}) or {}
        jvm = pdb.get("jvm", {}) or {}
        src = pdb.get("source") or "local"
        host = pdb.get("source_host") or ""
        title = "OpenVoxDB / PuppetDB Settings"
        if host:
            title += f" (@ {host})"
        console.print(Panel.fit(
            f"[bold]OpenVoxDB[/bold]\n"
            f"  Read pool max connections  : {_val(pools.get('read'))}\n"
            f"  Write pool max connections : {_val(pools.get('write'))}\n"
            f"  JVM heap (min)             : {_jvm_field(jvm, 'heap_min', 'xms')}\n"
            f"  JVM heap (max)             : {_jvm_field(jvm, 'heap_max', 'xmx')}\n"
            f"  Source                     : {src}"
            + (f" / {host}" if host else ""),
            title=title,
            border_style="magenta",
        ))

    for w in data.get("warnings") or []:
        console.print(f"[yellow]warning:[/yellow] {w}")

    remote = data.get("remote") or {}
    tried = remote.get("tried") or {}
    if tried:
        console.print(
            f"[dim]Bolt tried compilers={tried.get('compilers') or []} "
            f"puppetdb={tried.get('puppetdb_nodes') or []}[/dim]"
        )


@settings_app.command("set")
def settings_set(
    ctx: typer.Context,
    key: str = typer.Argument(..., help="Setting to change, e.g. server.jruby.max_active_instances or db.read_pool.max_connections"),
    value: str = typer.Argument(..., help="New value"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would change without applying"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
):
    """
    Directly set a specific infrastructure setting.

    Examples:
      ovox infra settings set server.jruby.max_active_instances 6
      ovox infra settings set server.jvm.heap 8g
      ovox infra settings set db.read_pool.max_connections 80
    """
    # Parse key into component + setting
    if key.startswith("server."):
        component = "server"
        setting = key[len("server."):]
    elif key.startswith("db."):
        component = "db"
        setting = key[len("db."):]
    else:
        console.print("[red]Key must start with 'server.' or 'db.'[/red]")
        raise typer.Exit(1)

    client = get_client(
        base_url=ctx.obj.get("url") if ctx.obj else None,
        token=ctx.obj.get("token") if ctx.obj else None,
        verify_ssl=ctx.obj.get("verify_ssl", True) if ctx.obj else True,
    )

    # Try to fetch current value for nice diff
    current = "unknown"
    try:
        data = client.get("/api/infra/settings")
        if component == "server" and "puppetserver" in data:
            ps = data["puppetserver"]
            if "max_active" in setting:
                current = ps.get("jruby_max_active_instances", "unknown")
            elif "heap" in setting:
                current = ps.get("jvm", {}).get("heap_max", "unknown")
            elif "code_cache" in setting:
                current = ps.get("jvm", {}).get("reserved_code_cache", "unknown")
        elif component == "db" and "puppetdb" in data:
            pdb = data["puppetdb"]
            if "read" in setting:
                current = pdb.get("pools", {}).get("read", "unknown")
            elif "write" in setting:
                current = pdb.get("pools", {}).get("write", "unknown")
    except Exception:
        pass

    if dry_run:
        console.print(Panel.fit(
            f"[yellow]DRY RUN[/yellow]\n\n"
            f"Would change:\n"
            f"  {component}.{setting}\n"
            f"    Current   : {current}\n"
            f"    New value : {value}",
            title="Dry Run - No changes will be made",
            border_style="yellow"
        ))
        return

    if not yes:
        if not typer.confirm(
            f"Set {component}.{setting} = {value}?\n"
            f"  Current: {current}\n"
            f"  New    : {value}\n\n"
            "This will back up configs and restart the service.",
            default=False
        ):
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit(0)

    try:
        result = client.post("/api/infra/settings/set", json={
            "component": component,
            "setting": setting,
            "value": value
        })
        console.print(f"[green]✓[/green] Applied {component}.{setting} = {value}")
        if isinstance(result, dict):
            if result.get("backup_dir"):
                console.print(f"  Backup: {result['backup_dir']}")
            if result.get("restarted"):
                console.print("  [green]Service restarted automatically[/green]")
    except OvoxAPIError as exc:
        console.print(f"[red]Failed to set setting:[/red] {exc}")
        raise typer.Exit(1)


def _local_tune_recommendations(client, component: Optional[str]) -> dict:
    """Generate basic recommendations using data we already have."""
    try:
        nodes = client.get("/api/nodes/")
        node_count = len(nodes) if isinstance(nodes, list) else 0
    except Exception:
        node_count = 0

    # Very rough heuristics (will be replaced by better backend logic later)
    recommendations = {
        "node_count": node_count,
        "recommendations": [],
        "current": {},
    }

    # Example puppetserver tuning
    if not component or component == "puppetserver":
        jruby_count = max(1, min(4, node_count // 50 + 1))
        recommendations["recommendations"].append({
            "component": "puppetserver",
            "setting": "jruby_max_active_instances",
            "current": "auto / unknown",
            "recommended": jruby_count,
            "reason": f"Based on ~{node_count} nodes. Rule of thumb: 1 JRuby per 50 nodes, capped reasonably."
        })

    # Placeholder for puppetdb
    if not component or component == "puppetdb":
        recommendations["recommendations"].append({
            "component": "puppetdb",
            "setting": "read_pool_max_connections",
            "current": "unknown",
            "recommended": max(10, min(50, node_count // 20)),
            "reason": "Increase connection pool with fleet size."
        })

    return recommendations


def _render_tune_recommendations(data: dict, component: Optional[str]):
    """Pretty-print the tuning recommendations."""
    console.print(Panel.fit(
        f"[bold]Fleet size detected:[/bold] {data.get('node_count', 'unknown')} nodes",
        border_style="blue"
    ))

    recs = data.get("recommendations", [])
    if not recs:
        console.print("[green]No specific tuning recommendations at this time.[/green]")
        return

    # Sort for readability: server first, then db; within each, alphabetical by setting
    def sort_key(r):
        comp_order = {"puppetserver": 0, "server": 0, "puppetdb": 1, "db": 1}
        return (comp_order.get(r.get("component", ""), 99), r.get("setting", ""))

    recs = sorted(recs, key=sort_key)

    table = Table(
        title="Tuning Recommendations",
        show_lines=True,        # horizontal separators between rows
        expand=True,            # use available terminal width nicely
        padding=(0, 1),         # decent horizontal breathing room
    )

    table.add_column("Component", style="cyan", no_wrap=True, min_width=12)
    table.add_column("Setting", style="magenta", overflow="fold")      # word-wrap long setting names
    table.add_column("Current", style="yellow", no_wrap=True)
    table.add_column("Recommended", style="green bold", no_wrap=True)
    table.add_column("Reason", style="dim", overflow="fold")           # word-wrap long reasons

    for r in recs:
        if component and r.get("component") != component:
            continue
        table.add_row(
            r.get("component", ""),
            r.get("setting", ""),
            str(r.get("current", "unknown")),
            str(r.get("recommended", "")),
            r.get("reason", "")           # no artificial truncation
        )

    console.print(table)
    console.print("\n[bold]Run [cyan]ovox infra tune --server[/cyan] or [cyan]--db[/cyan] to apply.[/bold]")


def _apply_tuning(client, data: dict, component: Optional[str], dry_run: bool):
    """Apply the recommended changes (backend does backup + restart)."""
    recs = data.get("recommendations", [])

    if dry_run:
        console.print("[yellow]Dry run — no changes made.[/yellow]")
        return

    # Group changes by component for cleaner API calls
    changes_by_comp = {}
    for r in recs:
        if component and r.get("component") != component:
            continue
        comp = r.get("component", "unknown")
        changes_by_comp.setdefault(comp, []).append({
            "setting": r.get("setting"),
            "value": r.get("recommended")
        })

    for comp, changes in changes_by_comp.items():
        try:
            result = client.post("/api/infra/tune/apply", json={
                "component": comp,
                "changes": changes
            })
            console.print(f"[green]✓[/green] Submitted tuning for {comp}")
            if isinstance(result, dict):
                if result.get("backup_note"):
                    console.print(f"  {result['backup_note']}")
                if result.get("restarted"):
                    console.print(f"  [green]Service restarted automatically[/green]")
        except OvoxAPIError as exc:
            console.print(f"[red]Failed[/red] to apply changes for {comp}: {exc}")
