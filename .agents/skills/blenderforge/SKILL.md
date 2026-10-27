---
name: blenderforge
description: Local-first research and production system for Blender capability discovery, REA-assisted reverse engineering, safe experimentation, and verified skill synthesis.
---

# BlenderForge Agent Skill

BlenderForge provides an evidence-driven, local-first bridge to Blender and the local reverse-engineering tool ecosystem (including REA).

## When to Use BlenderForge

Use BlenderForge when:
- Inspecting runtime capabilities, operators, modifiers, and Geometry Nodes of the installed Blender instance.
- Analyzing Blender add-on source code, MCP server implementations, or binary plugins using REA (Reverse Engineer Anything).
- Running controlled, isolated experiments across alternative modeling or rendering workflows without risking original projects.
- Synthesizing, validating, and retrieving reproducible Blender skills.
- Performing deterministic manifold, topology, and 3D-printing validation.
- Executing verifiable Blender tasks with automated regression testing.

## Operational Security Modes

BlenderForge strictly enforces operating security boundaries:
1. **`inspect` (Default)**: Read-only runtime discovery and inventory. State-changing mutations and destructive operators are blocked in code.
2. **`experiment`**: Isolated testing inside disposable workspaces (`.blenderforge/workspaces/<id>`).
3. **`develop`**: Controlled development against designated project copies.
4. **`production`**: User-authorized modifications and deliverables.
5. **`privileged`**: File deletions, package installation, network operations. Requires explicit approval.

## CLI Quick Reference

```bash
# Environment diagnostics and ecosystem status
blenderforge doctor
blenderforge status

# Runtime Blender API introspection (non-destructive)
blenderforge discover api
blenderforge inventory show
blenderforge inventory diff <inv_id_1> <inv_id_2>

# Reverse Engineer Anything (REA) integration
blenderforge rea status
blenderforge rea analyze <path/to/script_or_addon.py>

# MCP adapter discovery and overlap analysis
blenderforge discover mcp
blenderforge adapters list
blenderforge adapters inspect <server_id>

# Run isolated workflow experiments
blenderforge experiment run <manifest.yaml>

# Run deterministic benchmark suite
blenderforge benchmark run
blenderforge benchmark report

# Skill registry (FTS5 search)
blenderforge skills list
blenderforge skills inspect <skill_id>
blenderforge skills promote <skill_id> --status validated

# Start BlenderForge MCP server over stdio
blenderforge mcp serve
```

## Using REA with BlenderForge

When investigating an external Blender add-on or tool implementation:
1. Run `blenderforge rea status` to verify REA's engine readiness (version 6.7.0).
2. Run `blenderforge rea analyze <path>` to extract concrete structural evidence and call patterns.
3. Formulate candidate workflow strategies in an experiment manifest.
4. Execute via `blenderforge experiment run` to compare metrics (Pareto frontier on runtime, memory, and geometry counts).
5. Only promote findings to validated skills when backed by reproducible benchmark results.

## Model Context Protocol (MCP) Configuration

To expose BlenderForge as an MCP server to Antigravity or other MCP clients, add this entry to `mcp_config.json`:

```json
{
  "mcpServers": {
    "blenderforge": {
      "command": "uv",
      "args": ["run", "--directory", "E:\\BlenderForge", "blenderforge", "mcp", "serve"]
    }
  }
}
```
*(Preserve all other MCP entries; do not overwrite existing servers.)*
