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
    geometry_path="ShadowHawk_SH200.step",
    upstream_scale=10.0,
    downstream_scale=20.0,
    domain_scale=10.0,
    refinement_levels=(3, 5),
    n_bl_layers=5,
    linear_deflection=0.005,
    n_cores=4,
)
physics = PhysicsConfig(
    velocity=(30.0, 0.0, 0.0),
    nu=1.5e-5,
    turbulence_model="kOmegaSST",
    turbulence_intensity=0.001,
    turbulent_length_scale=0.01,
    steady_state=True,
    end_time=2000.0,
    write_interval=200.0,
)
builder = CaseBuilder(
    case_name="ShadowHawk_SH200_30ms",
    output_dir="/home/ubuntu/OpenFOAM/ubuntu-13/run",
    mesh_config=mesh,
    physics_config=physics,
    of_source="/opt/openfoam13/etc/bashrc",
)
result = builder.build()
print(result["foamRun_cmd"])
```

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
