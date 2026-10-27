# ⚒️ BlenderForge

<div align="center">

[![Python](https://img.shields.io/badge/Python-3.12%2B-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Blender](https://img.shields.io/badge/Blender-5.2%20LTS-orange.svg?logo=blender&logoColor=white)](https://www.blender.org/)
[![MCP Protocol](https://img.shields.io/badge/MCP-SDK%202.3-purple.svg)](https://modelcontextprotocol.io/)
[![REA Support](https://img.shields.io/badge/REA-v6.7.0%20Ready-magenta.svg)](https://rea.tools/)
[![Tests](https://img.shields.io/badge/Tests-33%2F33%20Passed-brightgreen.svg)]()
[![Benchmarks](https://img.shields.io/badge/Benchmarks-100%25%20Verified-success.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**A local-first, extensible research and production system for Blender capability discovery, REA-assisted reverse engineering, safe experimentation, and verified skill synthesis.**

[Key Features](#-key-features) • [Architecture](#-system-architecture) • [Quick Start](#-quick-start) • [REA Integration](#-rea-reverse-engineer-anything-integration) • [Security Modes](#-operating-security-modes) • [Benchmarks](#-deterministic-benchmarks) • [MCP Server](#-mcp-server)

</div>

---

## 🌟 Overview

**BlenderForge** bridges autonomous coding agents and Blender through **verifiable runtime evidence**. Instead of hallucinating API calls, outdated operator signatures, or unvetted scripts, BlenderForge:

1. **Introspects** the installed Blender build dynamically without side effects.
2. **Reverse Engineers** add-ons, scripts, and MCP implementations using **REA** (Reverse Engineer Anything).
3. **Conducts Isolated Experiments** in disposable workspaces and evaluates candidate workflows across a Pareto frontier (speed vs. polycount vs. memory).
4. **Validates** geometry deterministically (2-manifold checks, dimensions, 3D printing feasibility).
5. **Synthesizes & Retains** machine-verifiable procedural skills in a searchable SQLite FTS5 registry.

---

## 🏛 System Architecture

```
                                  ┌────────────────────────┐
                                  │    User / Agent CLI    │
                                  │ (Antigravity IDE / MCP)│
                                  └───────────┬────────────┘
                                              │
                                              ▼
                        ┌───────────────────────────────────────────┐
                        │      Unified Plan-Execute-Verify Loop     │
                        │    (blenderforge.orchestrator.planner)    │
                        └─────┬───────────────────┬───────────┬─────┘
                              │                   │           │
         ┌────────────────────┘                   │           └────────────────────┐
         ▼                                        ▼                                ▼
┌──────────────────┐                    ┌──────────────────┐             ┌──────────────────┐
│  Skill Registry  │                    │ Experiment Engine│             │    REA Bridge    │
│  (SQLite + FTS5) │                    │(Disposable Wspace│             │(Code Analysis /  │
│  100% Verified   │                    │  Pareto Frontier)│             │  Reconstruction) │
└──────────────────┘                    └─────────┬────────┘             └──────────────────┘
                                                  │
                                                  ▼
                                    ┌────────────────────────────┐
                                    │      Blender Runtime       │
                                    │    5.2 LTS (Background)    │
                                    │ (857 Ops, 274 Geo Nodes)   │
                                    └─────────────┬──────────────┘
                                                  │
                                                  ▼
                                    ┌────────────────────────────┐
                                    │  Deterministic Validators  │
                                    │ (Topology, 3D Print, Stl)  │
                                    └────────────────────────────┘
```

---

## 🚀 Key Features

- **🔍 Non-Destructive API Introspection**: Automatically inventories 857 operators across 14 categories, 83 modifiers, 29 constraints, 274 Geometry Node types, and 102 Shader Node types without scene mutation.
- **🧬 Version Diff Engine**: Compare capabilities between Blender versions (`blenderforge inventory diff`).
- **🛡️ Deny-by-Default Security Modes**: Enforced in code. Read-only `inspect` mode blocks all scene or filesystem mutations.
- **🔬 Multi-Candidate Experimentation**: Compares alternative approaches (e.g. BMesh vs `bpy.ops` vs Geometry Nodes vs Modifier stack) across runtime, memory, and geometry metrics.
- **📐 Deterministic Validators**: Verifies 2-manifold edges, watertightness, dimensional bounds, and STL export validity.
- **🧠 Evidence-Gated Skill Promotion**: Skills remain `experimental` until backed by machine-verifiable benchmark evidence.
- **🔌 Standard MCP Server**: Serves BlenderForge discovery and evaluation tools directly to any MCP client over stdio.

---

## 📦 Installation & Setup

### Prerequisites

- **Blender 4.x or 5.x** (Auto-detected from standard locations or `BLENDER_PATH`).
- **Python 3.12+** (managed via `uv` or system Python).
- **Node.js 20+ & npm** (optional, enables REA v6.7.0).

### Install via uv

```bash
git clone https://github.com/shinchan1907/BlenderForge.git
cd BlenderForge

# Sync dependencies and create environment
uv sync
```

---

## 💻 CLI Quick Reference

```bash
# Diagnostic & Ecosystem Health
uv run blenderforge doctor
uv run blenderforge status

# Runtime Blender API Introspection
uv run blenderforge discover api
uv run blenderforge inventory show
uv run blenderforge inventory diff <inv_1> <inv_2>

# REA (Reverse Engineer Anything) Investigation
uv run blenderforge rea status
uv run blenderforge rea analyze path/to/script_or_addon.py

# Multi-Server MCP Discovery & Overlap Detection
uv run blenderforge discover mcp
uv run blenderforge adapters list
uv run blenderforge adapters inspect blender-mock

# Deterministic Benchmark Suite (9 Locked Tasks)
uv run blenderforge benchmark run
uv run blenderforge benchmark report

# Verified Skill Library (FTS5 Keyword Search)
uv run blenderforge skills list
uv run blenderforge skills inspect modeling.bevel_cube.v1
uv run blenderforge skills promote <skill_id> --status validated

# Launch BlenderForge as an MCP Server
uv run blenderforge mcp serve
```

---

## 🔬 REA (Reverse Engineer Anything) Integration

BlenderForge directly bridges to **REA (`rea-agents` v6.7.0)**:
- **153 CLI commands** and **207 MCP tools**.
- Static JavaScript / Python / Web bundle analysis and architectural reconstruction.
- Inspects external add-ons, extracts operator registrations, and normalizes findings into structured `REAFinding` objects for targeted experiment generation.

```bash
uv run blenderforge rea analyze blender_scripts/introspect.py --objective "Inspect operator traversal"
```

---

## 🛡️ Operating Security Modes

BlenderForge strictly enforces boundaries in code (not prompt-only instructions):

| Mode | Purpose | Allowed Operations |
| :--- | :--- | :--- |
| **`inspect`** *(Default)* | Read-only discovery | Introspection, metadata query, REA code analysis. Mutations blocked. |
| **`experiment`** | Isolated candidate tests | Disposable sandboxes (`.blenderforge/workspaces/<id>`). |
| **`develop`** | Controlled development | Designated project copy modifications. |
| **`production`** | Deliverables & exports | User-authorized scene edits and exports. |
| **`privileged`** | High-impact actions | External network, file deletion, package installs. Requires confirmation. |

---

## 📊 Deterministic Benchmarks

Run locked benchmarks to verify environment capabilities and eliminate silent regressions:

```bash
uv run blenderforge benchmark run
```

### Verified Benchmark Suite (100.0% Pass Rate)

| Task ID | Component | Status | Score | Details |
| :--- | :--- | :---: | :---: | :--- |
| `bench_01_blender_detection` | Runtime Detection | **PASSED** | 1.00 | Blender 5.2.2 LTS resolved |
| `bench_02_mesh_creation` | Mesh Topology | **PASSED** | 1.00 | 8 verts, 12 edges, 6 faces, 0 non-manifold edges |
| `bench_03_modifier_stack` | Modifier Evaluation | **PASSED** | 1.00 | Evaluated depsgraph: 26 vertices, 48 edges |
| `bench_04_material_nodes` | Shader Node Graph | **PASSED** | 1.00 | Principled BSDF node creation & link verification |
| `bench_05_geometry_nodes` | Geometry Nodes | **PASSED** | 1.00 | Procedural node tree construction |
| `bench_06_render_preview` | Render Artifact | **PASSED** | 1.00 | Valid PNG render with camera & lighting |
| `bench_07_export_roundtrip` | 3D Printing STL | **PASSED** | 1.00 | Watertight manifold 20mm calibration cube |
| `bench_08_safety_boundary` | Policy Enforcement | **PASSED** | 1.00 | Deny-by-default mutation rejection in inspect mode |
| `bench_09_rea_discovery` | REA Engine | **PASSED** | 1.00 | REA 6.7.0 confirmed (153 commands, 207 MCP tools) |

---

## 🔌 MCP Server Configuration

To connect BlenderForge to **Antigravity IDE**, **Claude Desktop**, or any MCP-compatible agent, add to your `mcp_config.json`:

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

---

## 🧪 Testing

BlenderForge includes 33 comprehensive unit, integration, safety, and adapter tests:

```bash
uv run pytest tests/ -v
```

---

## 📜 License

Licensed under the [MIT License](LICENSE).
