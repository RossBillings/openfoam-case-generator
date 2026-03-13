# openfoam-case-generator

Python API for generating validated [OpenFOAM Foundation v13](https://openfoam.org) case
directories from STEP/IGES geometry files (Creo/CATIA output).

**Target physics:** Incompressible external aerodynamics (UAV/aircraft)
**Solver:** `foamRun` + `incompressibleFluid` module
**Mesher:** `snappyHexMesh` with auto-sized background box
**Turbulence:** `kOmegaSST` (configurable)

## Setup

```bash
uv venv .venv --python 3.11
uv pip install -e ".[dev]" --python .venv/bin/python
```

OpenFOAM Foundation v13 must be sourced in the environment before running
`CaseBuilder.build()` (mesh commands run as subprocesses):

```bash
source /opt/openfoam13/etc/bashrc
```

## Usage

```python
from of13_factory import CaseBuilder, MeshConfig, PhysicsConfig

mesh = MeshConfig(
    geometry_path="path/to/your_uav.stp",
    upstream_scale=10.0,      # 10x body length upstream
    downstream_scale=20.0,    # 20x body length downstream
    domain_scale=10.0,        # 10x body length laterally
    refinement_levels=(3, 5), # snappyHexMesh min/max refinement
    n_bl_layers=5,
    linear_deflection=0.005,  # STL tessellation tolerance (meters)
    n_cores=4,
)
physics = PhysicsConfig(
    velocity=(30.0, 0.0, 0.0),  # m/s; encode AoA via vector direction
    nu=1.5e-5,                   # kinematic viscosity (air at ~20°C)
    turbulence_model="kOmegaSST",
    turbulence_intensity=0.001,
    turbulent_length_scale=0.01,
    steady_state=True,
    end_time=2000.0,
    write_interval=200.0,
)
builder = CaseBuilder(
    case_name="my_uav_30ms",
    output_dir="/home/ubuntu/OpenFOAM/ubuntu-13/run",
    mesh_config=mesh,
    physics_config=physics,
    of_source="/opt/openfoam13/etc/bashrc",
)
result = builder.build()
print(result["foamRun_cmd"])  # command to launch the solver
```

### What `build()` does

1. Converts `.stp`/`.igs` → binary STL via cadquery/OCC
2. Computes the STL bounding box → auto-sizes the background blockMesh domain
3. Writes all OF13 dicts (`controlDict`, `fvSchemes`, `fvSolution`, `blockMeshDict`, `snappyHexMeshDict`, field BCs, `physicalProperties`, `momentumTransport`)
4. Runs the mesh pipeline as subprocesses: `blockMesh` → `surfaceFeatureExtract` → `snappyHexMesh` → `checkMesh`

Returns a dict with `case_path`, `cell_count`, `mesh_quality`, `ready_to_run`, and `foamRun_cmd`.

### Required manual step

Before running the solver, set `locationInMesh` in `constant/snappyHexMeshDict` to a point **inside the fluid domain** (outside the UAV body). The generated file uses `(99999 99999 99999)` as a placeholder.

### Key parameters to tune

| Parameter | Guidance |
|---|---|
| `linear_deflection` | Smaller = finer STL; `0.005` m is good for a ~2 m UAV |
| `refinement_levels` | `(3, 5)` is moderate; raise the max for better surface resolution |
| `n_bl_layers` | `5` is conservative; increase for better near-wall y+ |
| `velocity` | Encode angle of attack via the vector, e.g. `(29.9, 0.0, 1.05)` ≈ 2° AoA |

## Package structure

```
of13_factory/
├── __init__.py           CaseBuilder, MeshConfig, PhysicsConfig exports
├── builder.py            CaseBuilder orchestrator
├── geometry.py           STEP/IGES → STL via cadquery (OCC)
├── mesh_config.py        MeshConfig dataclass
├── physics_config.py     PhysicsConfig dataclass + derived properties
└── templates/
    ├── controlDict.py    foamRun / incompressibleFluid
    ├── fvSchemes.py      SIMPLE/PIMPLE schemes
    ├── fvSolution.py     GAMG + SIMPLE solvers
    ├── blockMeshDict.py  auto-sized background box
    ├── snappyHexMeshDict.py
    ├── fields.py         U, p, k, omega, nut, physicalProperties, momentumTransport
    └── decomposeParDict.py
tests/
└── test_geometry.py
sample_code/              original monolithic reference scripts
```

## Tests

```bash
.venv/bin/python -m pytest
```
