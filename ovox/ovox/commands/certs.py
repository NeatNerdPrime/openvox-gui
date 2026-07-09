"""
`ovox certs` command group — Certificate Authority operations.

Maps directly to the /api/certificates endpoints that the web GUI uses.
"""

from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.json import JSON

from ..client import OvoxAPIError, get_client

console = Console()

app = typer.Typer(
    help="Certificate authority management (sign, revoke, audit, clean). "
         "`ovox certs list` shows only pending CSRs by default (like `puppetserver ca list`).",
    no_args_is_help=True,
)


def _format_cert_table(certs: list, title: str) -> Table:
    table = Table(title=title)
    table.add_column("Certname", style="cyan", no_wrap=True)
    table.add_column("Status", style="green")
    table.add_column("Fingerprint (short)", style="dim")
    table.add_column("Expiry", style="yellow")

    for c in certs:
        name = c.get("certname") or c.get("name") or "?"
        status = c.get("status") or "signed"
        fp = c.get("fingerprint") or c.get("sha256") or ""
        if fp and len(fp) > 16:
            fp = fp[:8] + "…" + fp[-8:]
        expiry = c.get("not_after") or c.get("expires") or "-"
        table.add_row(str(name), str(status), fp, str(expiry)[:10])
    return table


@app.command("list")
def list_certs(
    ctx: typer.Context,
    all: bool = typer.Option(
        False,
        "--all",
        help="Show all certificates (signed + pending + revoked). "
             "Without this flag, only unsigned/pending CSRs are shown, "
             "matching the default behavior of `puppetserver ca list`.",
    ),
    status: Optional[str] = typer.Option(
        None,
        "--status",
        "-s",
        help="Explicit status filter (pending|signed|revoked). Rarely needed.",
    ),
    json_output: bool = typer.Option(False, "--json", "-j"),
):
    """
    List certificates known to the Puppet CA.

    By default this shows only **pending** (unsigned) certificate requests —
    exactly what `puppetserver ca list` shows without --all.
    Use --all to see the full picture (signed, pending, and revoked).
    """
    client = get_client(
        base_url=ctx.obj.get("url") if ctx.obj else None,
        token=ctx.obj.get("token") if ctx.obj else None,
        verify_ssl=ctx.obj.get("verify_ssl", True) if ctx.obj else True,
    )
    try:
        certs = client.get_certificates(status=status, all=all)
    except OvoxAPIError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)

    if json_output or (ctx.obj and ctx.obj.get("output") == "json"):
        import json
        console.print(JSON(json.dumps(certs, indent=2)))
        return

    if not certs:
        if all or status:
            console.print("[yellow]No certificates found for that filter.[/yellow]")
        else:
            console.print("[green]No pending certificate requests.[/green]")
        return

    title = "All Certificates" if all else ("Pending Certificates" if not status else f"Certificates ({status})")
    console.print(_format_cert_table(certs, title))


@app.command("sign")
def sign_cert(
    ctx: typer.Context,
    certname: str = typer.Argument(..., help="Certname to sign (must be in pending state)"),
):
    """Sign a pending certificate request."""
    client = get_client(
        base_url=ctx.obj.get("url") if ctx.obj else None,
        token=ctx.obj.get("token") if ctx.obj else None,
        verify_ssl=ctx.obj.get("verify_ssl", True) if ctx.obj else True,
    )
    try:
        res = client.sign_certificate(certname)
        console.print(f"[green]✓[/green] Signed certificate for [bold]{certname}[/bold]")
        if isinstance(res, dict) and res.get("message"):
            console.print(res["message"])
    except OvoxAPIError as exc:
        console.print(f"[red]Sign failed:[/red] {exc}")
        raise typer.Exit(1)


@app.command("revoke")
def revoke_cert(
    ctx: typer.Context,
    certname: str = typer.Argument(..., help="Certname to revoke"),
    clean: bool = typer.Option(False, "--clean", help="Also remove the cert from the CA (puppetserver ca clean)"),
):
    """Revoke (and optionally clean) a certificate."""
    client = get_client(
        base_url=ctx.obj.get("url") if ctx.obj else None,
        token=ctx.obj.get("token") if ctx.obj else None,
        verify_ssl=ctx.obj.get("verify_ssl", True) if ctx.obj else True,
    )
    try:
        res = client.revoke_certificate(certname, clean=clean)
        action = "Revoked and cleaned" if clean else "Revoked"
        console.print(f"[green]✓[/green] {action} [bold]{certname}[/bold]")
        if isinstance(res, dict) and res.get("message"):
            console.print(res["message"])
    except OvoxAPIError as exc:
        console.print(f"[red]Revoke failed:[/red] {exc}")
        raise typer.Exit(1)


@app.command("pending")
def pending(ctx: typer.Context, json_output: bool = typer.Option(False, "--json", "-j")):
    """Show only pending (unsigned) certificate requests.

    This is now the default behavior of `ovox certs list`.
    The command is kept for muscle memory and scripting convenience.
    """
    list_certs(ctx, all=False, json_output=json_output)


@app.command("trusted-facts")
def trusted_facts(
    ctx: typer.Context,
    certname: Optional[str] = typer.Option(
        None,
        "--certname",
        "-c",
        help="Filter to a single certname (exact match)",
    ),
    key: Optional[str] = typer.Option(
        None,
        "--key",
        "-k",
        help="Filter to nodes that have this extension (e.g. pp_role)",
    ),
    value: Optional[str] = typer.Option(
        None,
        "--value",
        "-v",
        help="Filter by extension value (case-insensitive exact match; "
             "pairs best with --key)",
    ),
    all_certs: bool = typer.Option(
        False,
        "--all",
        help="Include signed certificates that have no Puppet extensions",
    ),
    summary_only: bool = typer.Option(
        False,
        "--summary",
        help="Show only the fleet value summary (counts per extension key)",
    ),
    json_output: bool = typer.Option(False, "--json", "-j"),
):
    """
    List Puppet trusted facts from signed CA certificates.

    Trusted facts are certificate extension requests (pp_role, pp_environment,
    pp_datacenter, …) baked into agent PEMs at sign time. Catalog compilation
    exposes them as ``$trusted['extensions']``. Agents cannot forge or change
    them after the cert is signed.

    Examples:

      ovox certs trusted-facts

      ovox certs trusted-facts --key pp_role

      ovox certs trusted-facts -k pp_role -v webserver

      ovox certs trusted-facts --certname web01.example.com

      ovox certs trusted-facts --summary

      ovox certs trusted-facts --json
    """
    client = get_client(
        base_url=ctx.obj.get("url") if ctx.obj else None,
        token=ctx.obj.get("token") if ctx.obj else None,
        verify_ssl=ctx.obj.get("verify_ssl", True) if ctx.obj else True,
    )
    try:
        data = client.get_trusted_facts(
            certname=certname,
            key=key,
            value=value,
            only_with_extensions=not all_certs,
        )
    except OvoxAPIError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)

    if json_output or (ctx.obj and ctx.obj.get("output") == "json"):
        import json
        console.print(JSON(json.dumps(data, indent=2)))
        return

    nodes = data.get("nodes") or []
    summary = data.get("summary") or {}
    ext_keys = data.get("extension_keys") or []

    console.print(
        f"[bold]Trusted Facts[/bold]  "
        f"signed={data.get('total_signed', 0)}  "
        f"with_extensions={data.get('with_extensions', 0)}  "
        f"without={data.get('without_extensions', 0)}  "
        f"shown={data.get('filtered_count', len(nodes))}"
    )
    sources = data.get("oid_mapping_sources") or []
    if sources:
        console.print(f"[dim]OID mapping: {', '.join(str(s) for s in sources)}[/dim]")

    if summary:
        console.print()
        sum_table = Table(title="Fleet summary", show_lines=False)
        sum_table.add_column("Key", style="cyan")
        sum_table.add_column("Value", style="green")
        sum_table.add_column("Count", justify="right")
        for k in sorted(summary.keys()):
            counts = summary[k] or {}
            for val, n in counts.items():
                sum_table.add_row(k, str(val) if val != "" else "(empty)", str(n))
        console.print(sum_table)

    if summary_only:
        if not summary:
            console.print("[yellow]No trusted-fact extensions found on signed certificates.[/yellow]")
        return

    console.print()
    if not nodes:
        console.print(
            "[yellow]No matching nodes.[/yellow] "
            "Agents only receive trusted facts when CSR extension_requests "
            "(e.g. pp_role) are set before the certificate is signed."
        )
        return

    # Dynamic columns: preferred order first, then remaining keys
    preferred = [
        "pp_role", "pp_environment", "pp_datacenter", "pp_zone",
        "pp_region", "pp_application", "pp_apptier", "pp_cluster",
        "pp_provisioner",
    ]
    cols = [c for c in preferred if c in ext_keys]
    cols += sorted(c for c in ext_keys if c not in preferred)
    # Cap columns for terminal readability
    cols = cols[:10]

    table = Table(title="Nodes with trusted facts", show_lines=False)
    table.add_column("Certname", style="cyan", no_wrap=True)
    for c in cols:
        table.add_column(c, style="green", overflow="fold")
    if not cols:
        table.add_column("Extensions", style="dim")

    for n in nodes:
        cn = n.get("certname") or "?"
        exts = n.get("extensions") or {}
        if cols:
            row = [str(cn)] + [str(exts.get(c, "—") or "—") for c in cols]
        else:
            row = [str(cn), str(exts) if exts else "—"]
        table.add_row(*row)

    console.print(table)
    if len(ext_keys) > len(cols):
        console.print(
            f"[dim]… {len(ext_keys) - len(cols)} more extension key(s) omitted "
            f"(use --json for full data)[/dim]"
        )


# Alias for shorter muscle memory
@app.command("trusted")
def trusted_alias(
    ctx: typer.Context,
    certname: Optional[str] = typer.Option(None, "--certname", "-c"),
    key: Optional[str] = typer.Option(None, "--key", "-k"),
    value: Optional[str] = typer.Option(None, "--value", "-v"),
    all_certs: bool = typer.Option(False, "--all"),
    summary_only: bool = typer.Option(False, "--summary"),
    json_output: bool = typer.Option(False, "--json", "-j"),
):
    """Alias for ``ovox certs trusted-facts``."""
    trusted_facts(
        ctx,
        certname=certname,
        key=key,
        value=value,
        all_certs=all_certs,
        summary_only=summary_only,
        json_output=json_output,
    )
