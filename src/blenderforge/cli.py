"""Command Line Interface for BlenderForge."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import click
import yaml
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from blenderforge.adapters.models import ServerConfig, TransportType
from blenderforge.adapters.registry import AdapterRegistry
from blenderforge.config import OperatingMode, load_config
from blenderforge.discovery.blender_api import BlenderDiscoveryEngine
from blenderforge.discovery.diff import compare_inventories, format_diff_markdown
from blenderforge.discovery.graph import CapabilityGraph, CapabilityNode, NodeType
from blenderforge.discovery.rea_bridge import REABridge
from blenderforge.evaluation.benchmark_runner import BenchmarkRunner
from blenderforge.evaluation.validators import validate_mesh_topology
from blenderforge.experiments.models import CandidateStrategy, ExperimentManifest
from blenderforge.experiments.runner import ExperimentRunner
from blenderforge.skills.compiler import SkillCompiler
from blenderforge.skills.models import SkillStatus
from blenderforge.skills.registry import SkillRegistry
from blenderforge.storage.db import DatabaseManager

console = Console()
err_console = Console(stderr=True)


@click.group()
@click.option("--mode", type=click.Choice([m.value for m in OperatingMode]), default=OperatingMode.INSPECT.value, help="Operating security mode.")
@click.option("--config", "config_path", type=click.Path(dir_okay=False, path_type=Path), default=None, help="Path to config file.")
@click.option("--json", "json_output", is_flag=True, default=False, help="Output machine-readable JSON.")
@click.pass_context
def cli(ctx: click.Context, mode: str, config_path: Optional[Path], json_output: bool) -> None:
    """BlenderForge: Local-first research and production system for Blender."""
    ctx.ensure_object(dict)
    cfg = load_config(config_path, mode_override=OperatingMode(mode))
    db = DatabaseManager(cfg.db_path)
    ctx.obj["config"] = cfg
    ctx.obj["db"] = db
    ctx.obj["json"] = json_output


# Command: doctor
@cli.command("doctor")
@click.pass_context
def doctor_cmd(ctx: click.Context) -> None:
    """Inspect environment, Blender executable, and storage readiness."""
    cfg = ctx.obj["config"]
    db: DatabaseManager = ctx.obj["db"]
    json_output = ctx.obj["json"]

    blender_exe = cfg.resolve_blender_executable()
    blender_info = {}
    if blender_exe:
        try:
            res = subprocess.run(
                [str(blender_exe), "--background", "--python-expr", "import bpy, sys; print(f'BLENDER_VERSION={bpy.app.version_string}'); print(f'PY_VERSION={sys.version.split()[0]}')"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False
            )
            v_line = [line for line in res.stdout.splitlines() if line.startswith("BLENDER_VERSION=")]
            p_line = [line for line in res.stdout.splitlines() if line.startswith("PY_VERSION=")]
            blender_info["version"] = v_line[0].split("=", 1)[1] if v_line else "Unknown"
            blender_info["python"] = p_line[0].split("=", 1)[1] if p_line else "Unknown"
            blender_info["available"] = True
            blender_info["path"] = str(blender_exe)
        except Exception as e:
            blender_info["available"] = False
            blender_info["error"] = str(e)
            blender_info["path"] = str(blender_exe)
    else:
        blender_info["available"] = False
        blender_info["error"] = "Blender executable not found in PATH or standard locations."

    # Test DB status
    db_ok = False
    try:
        with db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT count(*) FROM schema_migrations")
            db_ok = cur.fetchone()[0] > 0
    except Exception:
        db_ok = False

    rea = REABridge(db)
    rea_avail = rea.is_available()
    rea_ver = rea.get_version() if rea_avail else None

    result = {
        "operating_mode": cfg.operating_mode.value,
        "python_runtime": sys.version.split()[0],
        "blender": blender_info,
        "rea": {
            "available": rea_avail,
            "version": rea_ver
        },
        "database": {
            "path": str(cfg.db_path),
            "initialized": db_ok
        },
        "directories": {
            "workspaces": str(cfg.workspaces_dir),
            "artifacts": str(cfg.artifacts_dir),
        }
    }

    db.log_audit(
        mode=cfg.operating_mode.value,
        action="doctor",
        actor="cli",
        status="success" if (blender_info.get("available") and db_ok) else "warning",
        details=result
    )

    if json_output:
        click.echo(json.dumps(result, indent=2))
        return

    table = Table(title="BlenderForge Diagnostic Report", show_header=True, header_style="bold cyan")
    table.add_column("Component", style="bold")
    table.add_column("Status")
    table.add_column("Details")

    table.add_row(
        "Operating Mode",
        f"[green]{cfg.operating_mode.value.upper()}[/green]",
        f"Default security boundary ({cfg.operating_mode.value})"
    )
    table.add_row(
        "Host Python",
        "[green]READY[/green]",
        f"Python {sys.version.split()[0]} on {sys.platform}"
    )

    if blender_info.get("available"):
        table.add_row(
            "Blender Executable",
            "[green]FOUND[/green]",
            f"{blender_info['version']} (Python {blender_info['python']}) at {blender_info['path']}"
        )
    else:
        table.add_row(
            "Blender Executable",
            "[yellow]NOT DETECTED[/yellow]",
            blender_info.get("error", "Executable not located")
        )

    table.add_row(
        "REA Reverse Engineering",
        "[green]AVAILABLE[/green]" if rea_avail else "[yellow]UNAVAILABLE[/yellow]",
        f"REA {rea_ver}" if rea_avail else "npx / rea-agents not reachable"
    )
    table.add_row(
        "Database & Storage",
        "[green]INITIALIZED[/green]" if db_ok else "[red]ERROR[/red]",
        f"SQLite at {cfg.db_path}"
    )
    table.add_row(
        "Workspaces",
        "[green]READY[/green]",
        str(cfg.workspaces_dir)
    )

    console.print(table)


# Command: status
@cli.command("status")
@click.pass_context
def status_cmd(ctx: click.Context) -> None:
    """Display comprehensive status of local Blender environment, REA, and tool ecosystem."""
    cfg = ctx.obj["config"]
    db: DatabaseManager = ctx.obj["db"]
    json_output = ctx.obj["json"]

    blender_exe = cfg.resolve_blender_executable()
    rea = REABridge(db)
    rea_avail = rea.is_available()
    rea_ver = rea.get_version() if rea_avail else None

    # Count database items
    with db.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM api_inventories")
        inv_count = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM capability_nodes")
        node_count = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM mcp_servers")
        srv_count = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM skills")
        skill_count = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM benchmark_runs")
        bench_count = cur.fetchone()[0]

    status_data = {
        "operating_mode": cfg.operating_mode.value,
        "blender": {
            "available": blender_exe is not None,
            "path": str(blender_exe) if blender_exe else None,
        },
        "rea": {
            "available": rea_avail,
            "version": rea_ver,
        },
        "storage": {
            "inventories_recorded": inv_count,
            "capability_nodes": node_count,
            "configured_mcp_servers": srv_count,
            "skills_registered": skill_count,
            "benchmarks_executed": bench_count,
        }
    }

    if json_output:
        click.echo(json.dumps(status_data, indent=2))
        return

    console.print(Panel(
        f"[bold cyan]Blender:[/bold cyan] {str(blender_exe) if blender_exe else '[red]Not detected[/red]'}\n"
        f"[bold magenta]REA Engine:[/bold magenta] {'REA ' + rea_ver if rea_avail else '[yellow]Not detected[/yellow]'}\n"
        f"[bold yellow]Mode:[/bold yellow] {cfg.operating_mode.value.upper()}\n"
        f"[bold green]Capability Nodes:[/bold green] {node_count} nodes in SQLite graph\n"
        f"[bold blue]Registered Skills:[/bold blue] {skill_count} skills in registry\n"
        f"[bold]Benchmark Runs:[/bold] {bench_count} recorded",
        title="BlenderForge Ecosystem Status",
        border_style="green"
    ))


# Group: rea
@cli.group("rea")
def rea_group() -> None:
    """Reverse Engineer Anything (REA) tools and bridge."""
    pass


@rea_group.command("status")
@click.pass_context
def rea_status_cmd(ctx: click.Context) -> None:
    """Check REA installation, doctor report, and provider capabilities."""
    db: DatabaseManager = ctx.obj["db"]
    json_output = ctx.obj["json"]

    bridge = REABridge(db)
    avail = bridge.is_available()
    ver = bridge.get_version() if avail else None
    caps = bridge.list_capabilities() if avail else {}
    doc = bridge.run_doctor() if avail else {}

    res = {
        "available": avail,
        "version": ver,
        "capabilities": caps,
        "doctor": doc
    }

    if json_output:
        click.echo(json.dumps(res, indent=2))
        return

    if not avail:
        console.print("[yellow]REA is not available. Ensure 'npx' is on PATH and 'rea-agents' is accessible.[/yellow]")
        return

    table = Table(title=f"REA Integration Status (v{ver})", show_header=True, header_style="bold magenta")
    table.add_column("Property", style="bold")
    table.add_column("Value")

    table.add_row("Status", "[green]OPERATIONAL[/green]")
    table.add_row("Version", str(ver))
    table.add_row("CLI Commands", str(caps.get("cli_commands_count", 0)))
    table.add_row("MCP Tools", str(caps.get("mcp_tools_count", 0)))
    table.add_row("Doctor Status", "[green]OK[/green]" if doc.get("healthy") else "[yellow]Provider Engine Needs Setup[/yellow]")

    console.print(table)


@rea_group.command("analyze")
@click.argument("target_path", type=click.Path(exists=True, path_type=Path))
@click.option("--objective", default="Analyze code structure and capabilities", help="Investigation goal.")
@click.pass_context
def rea_analyze_cmd(ctx: click.Context, target_path: Path, objective: str) -> None:
    """Analyze a local file, script, or add-on using REA."""
    db: DatabaseManager = ctx.obj["db"]
    json_output = ctx.obj["json"]

    bridge = REABridge(db)
    finding = bridge.analyze_source_target(target_path, objective)

    if json_output:
        click.echo(json.dumps(finding.model_dump(), indent=2))
        return

    console.print(Panel(
        f"[bold]Finding ID:[/bold] {finding.id}\n"
        f"[bold]Source:[/bold] {finding.source}\n"
        f"[bold]Confidence:[/bold] {finding.confidence * 100:.0f}%\n"
        f"[bold]Safety Classification:[/bold] {finding.safety_classification}\n"
        f"[bold]Suggested Experiment:[/bold] {finding.suggested_experiment}\n\n"
        f"[bold]Evidence Excerpt:[/bold]\n{finding.evidence_excerpt[:500]}...",
        title="REA Reverse-Engineering Finding",
        border_style="magenta"
    ))


# Group: adapters
@cli.group("adapters")
def adapters_group() -> None:
    """Manage and inspect MCP adapters."""
    pass


@adapters_group.command("list")
@click.pass_context
def adapters_list_cmd(ctx: click.Context) -> None:
    """List configured MCP adapters and their status."""
    db: DatabaseManager = ctx.obj["db"]
    json_output = ctx.obj["json"]

    with db.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, name, transport_type, status, last_seen_at FROM mcp_servers")
        rows = cur.fetchall()
        servers = [
            {
                "id": r["id"],
                "name": r["name"],
                "transport": r["transport_type"],
                "status": r["status"],
                "last_seen_at": r["last_seen_at"],
            }
            for r in rows
        ]

    if json_output:
        click.echo(json.dumps(servers, indent=2))
        return

    table = Table(title="Configured MCP Adapters", show_header=True, header_style="bold green")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Transport", style="magenta")
    table.add_column("Status")
    table.add_column("Last Seen")

    for s in servers:
        status_color = "green" if "connected" in s["status"] or "registered" in s["status"] else "red"
        table.add_row(
            s["id"],
            s["name"],
            s["transport"],
            f"[{status_color}]{s['status']}[/{status_color}]",
            s["last_seen_at"]
        )

    if not servers:
        console.print("[dim]No MCP servers registered yet. Run 'blenderforge discover mcp' to discover tools.[/dim]")
    else:
        console.print(table)


@adapters_group.command("inspect")
@click.argument("server_id")
@click.pass_context
def adapters_inspect_cmd(ctx: click.Context, server_id: str) -> None:
    """Inspect discovered tools and schemas for a specific MCP server."""
    db: DatabaseManager = ctx.obj["db"]
    json_output = ctx.obj["json"]

    with db.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name, description, input_schema_json, is_mutation FROM mcp_tools WHERE server_id = ?",
            (server_id,)
        )
        rows = cur.fetchall()
        tools = [
            {
                "id": r["id"],
                "name": r["name"],
                "description": r["description"],
                "schema": json.loads(r["input_schema_json"] or "{}"),
                "is_mutation": bool(r["is_mutation"]),
            }
            for r in rows
        ]

    if json_output:
        click.echo(json.dumps(tools, indent=2))
        return

    if not tools:
        console.print(f"[yellow]No tools discovered for server '{server_id}'. Run 'blenderforge discover mcp' first.[/yellow]")
        return

    table = Table(title=f"Tools for Server: {server_id}", show_header=True, header_style="bold cyan")
    table.add_column("Tool Name", style="bold")
    table.add_column("Side Effects", style="magenta")
    table.add_column("Description")
    table.add_column("Schema Properties")

    for t in tools:
        side_fx = "[red]MUTATION[/red]" if t["is_mutation"] else "[green]READ-ONLY[/green]"
        props = list((t["schema"].get("properties") or {}).keys())
        table.add_row(
            t["name"],
            side_fx,
            t["description"] or "",
            ", ".join(props) if props else "(none)"
        )

    console.print(table)


# Group: discover
@cli.group("discover")
def discover_group() -> None:
    """Discover Blender runtime APIs and MCP server tools."""
    pass


@discover_group.command("api")
@click.pass_context
def discover_api_cmd(ctx: click.Context) -> None:
    """Execute runtime introspection in background Blender process and persist inventory."""
    db: DatabaseManager = ctx.obj["db"]
    cfg = ctx.obj["config"]
    json_output = ctx.obj["json"]

    engine = BlenderDiscoveryEngine(cfg, db)
    try:
        data = engine.run_introspection()
        b_info = data.get("blender", {})
        ver_str = b_info.get("version_string", "unknown")
        sha256 = data.get("sha256", "unknown")

        db.log_audit(
            mode=cfg.operating_mode.value,
            action="discover_api",
            actor="cli",
            status="success",
            details={
                "version": ver_str,
                "sha256": sha256,
                "modifier_count": len(data.get("modifiers", [])),
                "geo_node_count": len(data.get("nodes", {}).get("geometry_nodes", [])),
            }
        )

        if json_output:
            click.echo(json.dumps(data, indent=2))
            return

        table = Table(title=f"Blender API Discovery Summary ({ver_str})", show_header=True, header_style="bold cyan")
        table.add_column("Category", style="bold")
        table.add_column("Count", justify="right", style="green")
        table.add_column("Highlights")

        op_cats = data.get("operators", {})
        total_ops = sum(len(ops) for ops in op_cats.values())
        table.add_row(
            "Operators (bpy.ops)",
            str(total_ops),
            f"{len(op_cats)} categories ({', '.join(list(op_cats.keys())[:5])}...)"
        )
        table.add_row(
            "Modifiers",
            str(len(data.get("modifiers", []))),
            ", ".join([m["name"] for m in data.get("modifiers", [])[:5]]) + "..."
        )
        table.add_row(
            "Constraints",
            str(len(data.get("constraints", []))),
            ", ".join([c["name"] for c in data.get("constraints", [])[:5]]) + "..."
        )
        table.add_row(
            "Geometry Nodes",
            str(len(data.get("nodes", {}).get("geometry_nodes", []))),
            "Procedural geometry building blocks"
        )
        table.add_row(
            "Shader Nodes",
            str(len(data.get("nodes", {}).get("shader_nodes", []))),
            "Material and texture processing nodes"
        )
        table.add_row(
            "Render Engines",
            str(len(data.get("render_engines", []))),
            ", ".join([e["name"] for e in data.get("render_engines", [])])
        )

        console.print(table)
        console.print(f"[dim]Inventory SHA256: {sha256}[/dim]")

    except Exception as e:
        err_console.print(f"[bold red]API Discovery Failed: {e}[/bold red]")
        sys.exit(1)


@discover_group.command("mcp")
@click.pass_context
def discover_mcp_cmd(ctx: click.Context) -> None:
    """Connect to configured MCP servers, discover tools, and analyze overlaps."""
    db: DatabaseManager = ctx.obj["db"]
    cfg = ctx.obj["config"]
    json_output = ctx.obj["json"]

    registry = AdapterRegistry(db)
    graph = CapabilityGraph(db)

    # Register default mock server
    mock_config = ServerConfig(
        id="blender-mock",
        name="Blender Mock Server",
        transport=TransportType.MOCK
    )
    registry.register_server(mock_config)

    # Check for custom mcp servers config file in base_dir
    mcp_file = cfg.base_dir / "mcp_servers.json"
    if mcp_file.exists():
        try:
            mcp_data = json.loads(mcp_file.read_text(encoding="utf-8"))
            for entry in mcp_data.get("servers", []):
                srv_cfg = ServerConfig(**entry)
                registry.register_server(srv_cfg)
        except Exception as e:
            err_console.print(f"[yellow]Warning: Could not parse {mcp_file}: {e}[/yellow]")

    async def _run_discovery():
        discovered = await registry.discover_all()
        overlaps = registry.detect_overlapping_capabilities()
        return discovered, overlaps

    discovered, overlaps = asyncio.run(_run_discovery())

    # Ingest into CapabilityGraph
    for srv_id, tools in discovered.items():
        for t in tools:
            node = CapabilityNode(
                id=t.id,
                node_type=NodeType.MCP_TOOL,
                name=t.name,
                identifier=t.id,
                description=t.description,
                payload={
                    "server_id": srv_id,
                    "is_mutation": t.is_mutation,
                    "schema": t.input_schema,
                }
            )
            graph.add_node(node)

    db.log_audit(
        mode=cfg.operating_mode.value,
        action="discover_mcp",
        actor="cli",
        status="success",
        details={
            "server_count": len(discovered),
            "tool_count": sum(len(ts) for ts in discovered.values()),
            "overlap_count": len(overlaps),
        }
    )

    if json_output:
        out = {
            "servers": {k: [t.model_dump() for t in v] for k, v in discovered.items()},
            "overlaps": overlaps,
        }
        click.echo(json.dumps(out, indent=2))
        return

    console.print(f"[bold green]MCP Discovery Completed successfully![/bold green]")
    for srv_id, tools in discovered.items():
        console.print(f"  [cyan]{srv_id}[/cyan]: Discovered [bold]{len(tools)}[/bold] tools")

    if overlaps:
        console.print(f"\n[bold yellow]Detected {len(overlaps)} Potential Overlaps Across Servers:[/bold yellow]")
        for o in overlaps:
            console.print(f"  - [magenta]{o['tool_a']}[/magenta] <-> [magenta]{o['tool_b']}[/magenta] (Reasons: {', '.join(o['similarity_reasons'])})")


# Group: inventory
@cli.group("inventory")
def inventory_group() -> None:
    """Inspect and compare Blender runtime inventories."""
    pass


@inventory_group.command("show")
@click.option("--id", "inv_id", default=None, help="Inventory ID (defaults to latest).")
@click.pass_context
def inventory_show_cmd(ctx: click.Context, inv_id: Optional[str]) -> None:
    """Display stored inventory metadata and discovered capabilities."""
    db: DatabaseManager = ctx.obj["db"]
    json_output = ctx.obj["json"]

    with db.get_connection() as conn:
        cur = conn.cursor()
        if inv_id:
            cur.execute("SELECT * FROM api_inventories WHERE id = ?", (inv_id,))
        else:
            cur.execute("SELECT * FROM api_inventories ORDER BY created_at DESC LIMIT 1")
        row = cur.fetchone()

    if not row:
        console.print("[yellow]No API inventories found. Run 'blenderforge discover api' first.[/yellow]")
        return

    data = json.loads(row["metadata_json"])

    if json_output:
        click.echo(json.dumps(data, indent=2))
        return

    b_info = data.get("blender", {})
    console.print(Panel(
        f"[bold]Blender Version:[/bold] {b_info.get('version_string')}\n"
        f"[bold]Build Hash:[/bold] {b_info.get('build_hash')}\n"
        f"[bold]Build Date:[/bold] {b_info.get('build_date')}\n"
        f"[bold]Python Runtime:[/bold] {b_info.get('python_version')}\n"
        f"[bold]Platform:[/bold] {b_info.get('build_platform')}\n"
        f"[bold]Raw Hash:[/bold] {row['raw_hash']}\n"
        f"[bold]Recorded At:[/bold] {row['created_at']}",
        title=f"Inventory: {row['id']}",
        border_style="cyan"
    ))


@inventory_group.command("diff")
@click.argument("inv_id1")
@click.argument("inv_id2")
@click.pass_context
def inventory_diff_cmd(ctx: click.Context, inv_id1: str, inv_id2: str) -> None:
    """Generate a version-difference report between two inventories."""
    db: DatabaseManager = ctx.obj["db"]
    json_output = ctx.obj["json"]

    with db.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT metadata_json FROM api_inventories WHERE id = ?", (inv_id1,))
        r1 = cur.fetchone()
        cur.execute("SELECT metadata_json FROM api_inventories WHERE id = ?", (inv_id2,))
        r2 = cur.fetchone()

    if not r1:
        err_console.print(f"[red]Inventory '{inv_id1}' not found.[/red]")
        sys.exit(1)
    if not r2:
        err_console.print(f"[red]Inventory '{inv_id2}' not found.[/red]")
        sys.exit(1)

    diff = compare_inventories(json.loads(r1["metadata_json"]), json.loads(r2["metadata_json"]))

    if json_output:
        click.echo(json.dumps(diff, indent=2))
        return

    md_report = format_diff_markdown(diff)
    console.print(Markdown(md_report))


# Group: experiment
@cli.group("experiment")
def experiment_group() -> None:
    """Run and evaluate isolated workflows and candidates."""
    pass


@experiment_group.command("run")
@click.argument("manifest_file", type=click.Path(exists=True, path_type=Path))
@click.pass_context
def experiment_run_cmd(ctx: click.Context, manifest_file: Path) -> None:
    """Execute an experiment manifest containing candidate strategies."""
    cfg = ctx.obj["config"]
    db: DatabaseManager = ctx.obj["db"]
    json_output = ctx.obj["json"]

    content = manifest_file.read_text(encoding="utf-8")
    data = yaml.safe_load(content) if manifest_file.suffix in (".yaml", ".yml") else json.loads(content)
    manifest = ExperimentManifest(**data)

    runner = ExperimentRunner(cfg, db)
    report = runner.run_experiment(manifest)

    if json_output:
        click.echo(json.dumps(report.model_dump(), indent=2))
        return

    table = Table(title=f"Experiment Results: {manifest.id}", show_header=True, header_style="bold green")
    table.add_column("Strategy", style="bold")
    table.add_column("Status")
    table.add_column("Duration", justify="right")
    table.add_column("Vertices")
    table.add_column("Faces")
    table.add_column("Pareto Optimal?")

    for r in report.results:
        status_col = "[green]SUCCESS[/green]" if r.success else f"[red]{r.failure_classification or 'FAILED'}[/red]"
        is_pareto = "[bold yellow]YES[/bold yellow]" if r.strategy_name in report.pareto_optimal_strategies else "No"
        table.add_row(
            r.strategy_name,
            status_col,
            f"{r.duration_sec:.3f}s",
            str(r.metrics.get("vertices", 0)),
            str(r.metrics.get("faces", 0)),
            is_pareto
        )

    console.print(table)


# Group: benchmark
@cli.group("benchmark")
def benchmark_group() -> None:
    """Execute locked deterministic benchmarks."""
    pass


@benchmark_group.command("run")
@click.pass_context
def benchmark_run_cmd(ctx: click.Context) -> None:
    """Execute full locked benchmark suite and prevent capability regressions."""
    cfg = ctx.obj["config"]
    db: DatabaseManager = ctx.obj["db"]
    json_output = ctx.obj["json"]

    runner = BenchmarkRunner(cfg, db)
    report = runner.run_all()

    if json_output:
        click.echo(json.dumps(report.model_dump(), indent=2))
        return

    table = Table(title=f"{report.suite_name} (Score: {report.overall_score * 100:.1f}%)", show_header=True, header_style="bold cyan")
    table.add_column("Task ID", style="bold")
    table.add_column("Status")
    table.add_column("Score", justify="right")
    table.add_column("Duration", justify="right")
    table.add_column("Details")

    for r in report.results:
        status_col = "[green]PASSED[/green]" if r.passed else f"[red]FAILED ({r.error or 'Check failed'})[/red]"
        table.add_row(
            r.task_id,
            status_col,
            f"{r.score:.2f}",
            f"{r.duration_sec:.2f}s",
            str(r.details) if r.passed else str(r.error)
        )

    console.print(table)


@benchmark_group.command("report")
@click.option("--limit", default=10, help="Number of benchmark runs to display.")
@click.pass_context
def benchmark_report_cmd(ctx: click.Context, limit: int) -> None:
    """Display history of benchmark runs."""
    db: DatabaseManager = ctx.obj["db"]
    json_output = ctx.obj["json"]

    with db.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM benchmark_runs ORDER BY run_at DESC LIMIT ?", (limit,))
        rows = cur.fetchall()
        runs = [
            {
                "id": r["id"],
                "task_id": r["task_id"],
                "blender_version": r["blender_version"],
                "run_at": r["run_at"],
                "passed": bool(r["passed"]),
                "score": r["score"],
                "duration_sec": r["duration_sec"],
            }
            for r in rows
        ]

    if json_output:
        click.echo(json.dumps(runs, indent=2))
        return

    table = Table(title="Benchmark Execution History", show_header=True, header_style="bold cyan")
    table.add_column("Task ID", style="bold")
    table.add_column("Passed?")
    table.add_column("Score")
    table.add_column("Duration")
    table.add_column("Executed At")

    for run in runs:
        pass_col = "[green]YES[/green]" if run["passed"] else "[red]NO[/red]"
        table.add_row(
            run["task_id"],
            pass_col,
            str(run["score"]),
            f"{run['duration_sec']:.2f}s",
            run["run_at"]
        )

    console.print(table)


# Group: skills
@cli.group("skills")
def skills_group() -> None:
    """Manage, inspect, and retrieve verified Blender skills."""
    pass


@skills_group.command("list")
@click.option("--domain", default=None, help="Filter by domain.")
@click.pass_context
def skills_list_cmd(ctx: click.Context, domain: Optional[str]) -> None:
    """List skills in library."""
    db: DatabaseManager = ctx.obj["db"]
    json_output = ctx.obj["json"]

    registry = SkillRegistry(db)
    skills = registry.list_skills(domain=domain)

    if json_output:
        click.echo(json.dumps([s.model_dump() for s in skills], indent=2))
        return

    table = Table(title="Verified Skill Library", show_header=True, header_style="bold magenta")
    table.add_column("Skill ID", style="cyan")
    table.add_column("Name", style="bold")
    table.add_column("Domain")
    table.add_column("Status")
    table.add_column("Version")

    for s in skills:
        status_col = "[green]VALIDATED[/green]" if s.status == SkillStatus.VALIDATED else "[yellow]EXPERIMENTAL[/yellow]" if s.status == SkillStatus.EXPERIMENTAL else s.status.value
        table.add_row(s.id, s.name, s.domain, status_col, s.version)

    if not skills:
        console.print("[dim]No skills in library yet.[/dim]")
    else:
        console.print(table)


@skills_group.command("inspect")
@click.argument("skill_id")
@click.pass_context
def skills_inspect_cmd(ctx: click.Context, skill_id: str) -> None:
    """Inspect complete skill strategy, code, and evidence."""
    db: DatabaseManager = ctx.obj["db"]
    json_output = ctx.obj["json"]

    registry = SkillRegistry(db)
    skill = registry.get_skill(skill_id)

    if not skill:
        err_console.print(f"[red]Skill '{skill_id}' not found.[/red]")
        sys.exit(1)

    if json_output:
        click.echo(json.dumps(skill.model_dump(), indent=2))
        return

    console.print(Panel(
        f"[bold]Name:[/bold] {skill.name}\n"
        f"[bold]Domain:[/bold] {skill.domain}\n"
        f"[bold]Status:[/bold] {skill.status.value.upper()}\n"
        f"[bold]Version:[/bold] {skill.version}\n"
        f"[bold]Code Hash:[/bold] {skill.code_hash}\n\n"
        f"[bold]Strategy:[/bold]\n{skill.strategy}\n\n"
        f"[bold]Code Snippet:[/bold]\n```python\n{skill.code}\n```",
        title=f"Skill: {skill.id}",
        border_style="magenta"
    ))


@skills_group.command("promote")
@click.argument("skill_id")
@click.option("--status", "target_status", type=click.Choice([s.value for s in SkillStatus]), default=SkillStatus.VALIDATED.value)
@click.pass_context
def skills_promote_cmd(ctx: click.Context, skill_id: str, target_status: str) -> None:
    """Promote skill status with machine-verifiable benchmark evidence."""
    db: DatabaseManager = ctx.obj["db"]
    registry = SkillRegistry(db)
    compiler = SkillCompiler(db)

    skill = registry.get_skill(skill_id)
    if not skill:
        err_console.print(f"[red]Skill '{skill_id}' not found.[/red]")
        sys.exit(1)

    # Check for passing benchmark in DB for this skill
    evidence = skill.evidence
    try:
        updated_skill = compiler.promote_skill(skill, SkillStatus(target_status), evidence)
        registry.save_skill(updated_skill)
        console.print(f"[bold green]Skill '{skill_id}' successfully promoted to '{target_status}'.[/bold green]")
    except Exception as e:
        err_console.print(f"[bold red]Promotion rejected: {e}[/bold red]")
        sys.exit(1)


# Group: mcp
@cli.group("mcp")
def mcp_group() -> None:
    """BlenderForge MCP server commands."""
    pass


@mcp_group.command("serve")
def mcp_serve_cmd() -> None:
    """Start BlenderForge MCP server over stdio."""
    from blenderforge.mcp_server import main as mcp_main
    asyncio.run(mcp_main())


# Group: audit
@cli.group("audit")
def audit_group() -> None:
    """Inspect audit log events."""
    pass


@audit_group.command("show")
@click.option("--limit", default=20, help="Number of recent events to show.")
@click.pass_context
def audit_show_cmd(ctx: click.Context, limit: int) -> None:
    """Display immutable audit logs."""
    db: DatabaseManager = ctx.obj["db"]
    json_output = ctx.obj["json"]

    events = db.get_audit_events(limit=limit)

    if json_output:
        click.echo(json.dumps(events, indent=2))
        return

    table = Table(title="BlenderForge Audit Log", show_header=True, header_style="bold magenta")
    table.add_column("ID", justify="right", style="cyan")
    table.add_column("Timestamp", style="dim")
    table.add_column("Mode", style="bold yellow")
    table.add_column("Action", style="green")
    table.add_column("Status")
    table.add_column("Actor")

    for ev in events:
        status_color = "green" if ev["status"] == "success" else "yellow" if ev["status"] == "warning" else "red"
        table.add_row(
            str(ev["id"]),
            ev["timestamp"],
            ev["mode"],
            ev["action"],
            f"[{status_color}]{ev['status']}[/{status_color}]",
            ev["actor"]
        )

    console.print(table)
