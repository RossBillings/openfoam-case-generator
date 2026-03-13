# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Environment

Python 3.11 via `uv` with a `.venv` at the repo root. cadquery (pip-installable OCC wrapper) replaces pythonocc-core.

```bash
# Activate
source .venv/bin/activate

# Install / sync deps
uv pip install -e ".[dev]" --python .venv/bin/python
```

OpenFOAM Foundation v13 must be sourced for `CaseBuilder.build()` to run mesh commands (blockMesh, snappyHexMesh, etc.):
```bash
source /opt/openfoam13/etc/bashrc   # inside Multipass Ubuntu VM
```
The Python package itself and all tests run on macOS without OF13.

## Common commands

```bash
# Run all tests
.venv/bin/python -m pytest

# Run a single test
.venv/bin/python -m pytest tests/test_geometry.py::test_bounding_box_binary_stl -v

# Smoke-test imports
.venv/bin/python -c "from of13_factory import CaseBuilder, MeshConfig, PhysicsConfig; print('OK')"
```

## Architecture

The package converts STEP/IGES geometry into a ready-to-run OF13 case directory. The flow is:

```
STEP/IGES → cadquery → binary STL → bounding box → blockMeshDict sizing
                                                  → snappyHexMeshDict
                                                  → field BCs (U, p, k, omega, nut)
                                                  → subprocess: blockMesh → surfaceFeatureExtract → snappyHexMesh → checkMesh
```

**Entry point:** `CaseBuilder.build()` in `builder.py` — orchestrates geometry conversion, dict writing, and OF13 subprocess calls. Returns `{case_path, cell_count, mesh_quality, ready_to_run, foamRun_cmd}`.

**Config layer:** Two dataclasses drive everything:
- `MeshConfig` — geometry path, domain scaling, snappyHexMesh refinement levels, BL layers, cell budget, core count
- `PhysicsConfig` — velocity vector (AoA encoded here), nu, turbulence model, steady/transient flag; derived properties `k_inlet`, `omega_inlet`, `nut_inlet` compute inlet turbulence quantities

**Templates:** Each file in `of13_factory/templates/` is a single `render(...)` function returning an f-string OF13 dict. No Jinja2. All templates are version-locked to OF13 Foundation syntax (not ESI/OpenCFD, not pre-v11). `fields.py` also renders `physicalProperties` and `momentumTransport`.

**Geometry:** `geometry.py::step_iges_to_stl()` uses `cadquery.importers.importStep()` + `cadquery.exporters.export()`. IGES falls back to the raw OCC reader via cadquery's internals. `get_stl_bounding_box()` is pure Python (no deps) and handles both binary and ASCII STL.

**Domain sizing:** `blockMeshDict.render()` auto-sizes the background box from the STL bounding box using `upstream_scale`, `downstream_scale`, and `domain_scale` as body-length multiples. Background hex resolution targets ~50 cells across the shortest span.

**Key OF13-specific choices:**
- Solver: `foamRun` + `solver incompressibleFluid` (not `simpleFoam`)
- Turbulence dict: `constant/momentumTransport` (not `turbulenceProperties`)
- Physical properties: `constant/physicalProperties` with `viscosityModel constant`
- `snappyHexMeshDict` uses `locationInMesh (99999 99999 99999)` as a placeholder — must be set to a point in the fluid domain before running
