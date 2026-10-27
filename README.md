# BlenderForge

> **Local-first, extensible research and production system for Blender capability discovery, REA-assisted reverse engineering, safe experimentation, and verified skill synthesis.**

BlenderForge transforms Blender into an evidence-driven, autonomous production and research environment. Instead of assuming API compatibility or hallucinating operator semantics, BlenderForge introspects installed Blender runtimes, integrates with local reverse engineering engines (REA), conducts controlled experiments in disposable workspaces, benchmarks workflows, and compiles verified skills into a searchable local library.

---

## Key Capabilities

1. **Blender Runtime Introspection**:
   - Discovers operators (`bpy.ops`), RNA properties, descriptions, enums, units, read-only status, modifiers, constraints, shader nodes, and Geometry Nodes directly from the running Blender engine without triggering mutations.
   - Version difference reports (`blenderforge inventory diff`) between different Blender builds or releases.

2. **Reverse Engineer Anything (REA) Integration**:
   - Integrates directly with the locally available `rea-agents` engine (REA v6.7.0, 153 CLI commands, 207 MCP tools).
   - Deep structural and static analysis of third-party add-ons, Python scripts, and MCP implementations.
   - Normalizes reverse-engineered findings into structured evidence records linked to testable hypotheses.

3. **Provider-Neutral MCP Adapter System**:
   - Connects to multiple external MCP servers over stdio, SSE/HTTP, or mock transports.
   - Classifies operations by side effects (`READ-ONLY` vs `MUTATION`).
   - Automatically detects overlapping tool capabilities without assuming identical semantics.
   - Exposes BlenderForge itself as an MCP server (`blenderforge mcp serve`).

4. **Isolated Experiment Runner & Multi-Objective Pareto Comparison**:
   - Executes candidate modeling strategies in isolated disposable workspaces.
   - Captures runtime duration, peak memory, vertex/edge/face counts, non-manifold edges, output hashes, and visual preview artifacts.
   - Compares candidates using Pareto-frontier trade-offs (e.g. procedural Geometry Nodes vs destructive mesh operators vs modifier stacks).

5. **Deterministic Evaluation & Benchmark Suite**:
   - Deterministic topological and manifold checks (watertight boundary analysis, loose vertices, 2-manifold edge integrity).
   - Dimensional tolerance validation.
   - 3D-printing and manufacturing validation (build volume envelope, minimum feature size, positive volume).
   - 9-task locked capability benchmark suite preventing regressions.

6. **Evidence-Gated Skill Compiler & FTS5 Registry**:
   - Formats reusable procedural skills with code hashes, preconditions, and evidence records.
   - Strictly enforces machine-verifiable benchmark evidence before promoting any skill from `experimental` to `validated` or `stable`.
   - Full-text retrieval via SQLite FTS5 with BM25 ranking.

---

## Operating Security Modes

BlenderForge enforces strict deny-by-default execution boundaries in code:

| Mode | Purpose | Permitted Actions |
| :--- | :--- | :--- |
| **`inspect`** *(Default)* | Read-only discovery and inventory | Non-mutating operators, metadata queries, REA code analysis. Mutations blocked. |
| **`experiment`** | Bounded candidate evaluation | Isolated disposable workspaces (`.blenderforge/workspaces/<id>`). |
| **`develop`** | Controlled development | Designated project copy modifications. |
| **`production`** | Deliverables & final outputs | User-authorized scene edits and exports. |
| **`privileged`** | High-impact actions | External network, file deletion, package management (explicit authorization required). |

---

## Environment & Requirements

- **Blender**: 5.2.2 LTS (or 4.x / 5.x) located at `C:\Program Files\Blender Foundation\Blender 5.2\blender.exe` (or on system `PATH`).
- **Python**: 3.12+ (managed by `uv`).
- **REA (Reverse Engineer Anything)**: `rea-agents` v6.7.0 via `npx` (Node.js 22+).
- **SQLite**: Local metadata storage with FTS5 enabled.

---

## CLI Quick Reference

```bash
# 1. Environment & Diagnostics
blenderforge doctor
blenderforge status

# 2. REA Integration
blenderforge rea status
blenderforge rea analyze path/to/addon.py --objective "Inspect operator registration"

# 3. Blender Introspection & Capabilities
blenderforge discover api
blenderforge inventory show
blenderforge inventory diff <inv_id_1> <inv_id_2>

# 4. MCP Servers & Discovery
blenderforge discover mcp
blenderforge adapters list
blenderforge adapters inspect blender-mock

# 5. Deterministic Benchmark Suite
blenderforge benchmark run
blenderforge benchmark report

# 6. Verified Skill Library
blenderforge skills list
blenderforge skills inspect modeling.bevel_cube.v1
blenderforge skills promote modeling.bevel_cube.v1 --status validated

# 7. Start BlenderForge MCP Server
blenderforge mcp serve
```

---

## Running Tests

Execute all 33 unit, integration, adapter, and safety tests with pytest:

```bash
uv run pytest tests/ -v
```

---

## Repository Structure

```
BlenderForge/
├── .agents/skills/blenderforge/SKILL.md # Antigravity IDE agent skill definition
├── blender_scripts/
│   └── introspect.py                   # In-Blender runtime introspection script
├── benchmarks/                         # Benchmark task definitions & fixtures
├── src/blenderforge/
│   ├── adapters/                       # MCP server adapters & registry
│   ├── discovery/                      # Blender API discovery, diffing & REA bridge
│   ├── evaluation/                     # Deterministic validators & benchmark runner
│   ├── execution/                      # Sandboxing, security boundaries, secret redaction
│   ├── experiments/                    # Isolated experiment runner & Pareto comparator
│   ├── orchestrator/                   # Unified planner & 12-step execution loop
│   ├── skills/                         # Skill compiler, models & FTS5 registry
│   ├── storage/                        # SQLite storage & schema migrations
│   ├── cli.py                          # Click & Rich CLI interface
│   ├── config.py                       # Configuration & path discovery
│   └── mcp_server.py                   # BlenderForge standard MCP stdio server
└── tests/
    ├── adapters/                       # Adapter & policy tests
    ├── integration/                    # Real Blender background execution tests
    ├── safety/                         # Sandbox, path traversal & secret redaction tests
    └── unit/                           # Storage, CLI, validators, skills & planner tests
```
