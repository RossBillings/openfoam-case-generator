"""
of13_factory usage example
--------------------------
Prerequisites inside Multipass VM:
    conda install -c conda-forge pythonocc-core
    source /opt/openfoam13/etc/bashrc

This script:
  1. Takes a STEP file from Creo/CATIA
  2. Converts it to a watertight STL via OpenCASCADE
  3. Sizes the domain from the bounding box automatically
  4. Writes all validated OF13 dicts
  5. Runs blockMesh → surfaceFeatureExtract → snappyHexMesh → checkMesh
  6. Returns a ready-to-run case directory
"""

from of13_factory import CaseBuilder, MeshConfig, PhysicsConfig

# ------------------------------------------------------------------
# 1. Geometry: STEP from Creo/CATIA
# ------------------------------------------------------------------
mesh = MeshConfig(
    geometry_path="/home/ubuntu/models/ShadowHawk_SH200.step",

    # Domain sizing (multiples of bounding box longest dim)
    upstream_scale=10.0,        # 10 body lengths upstream
    downstream_scale=20.0,      # 20 body lengths downstream (wake capture)
    domain_scale=10.0,          # 10 body lengths cross-section half-width

    # snappyHexMesh surface refinement
    refinement_levels=(3, 5),   # min=3, max=5 on body surface
    n_bl_layers=5,              # prism layers on body wall
    bl_expansion_ratio=1.2,

    # OCC tessellation: 5mm chord tolerance for ~1m UAV
    linear_deflection=0.005,

    max_cells=5_000_000,
    n_cores=4,
)

# ------------------------------------------------------------------
# 2. Physics: clean freestream at 30 m/s, kOmegaSST, RANS steady
# ------------------------------------------------------------------
physics = PhysicsConfig(
    velocity=(30.0, 0.0, 0.0),     # 0° AoA; encode AoA as: (U*cos(a), U*sin(a), 0)
    nu=1.5e-5,                      # air at 20°C
    turbulence_model="kOmegaSST",
    turbulence_intensity=0.001,     # 0.1% — clean freestream
    turbulent_length_scale=0.01,    # 1cm — appropriate for UAV scale
    steady_state=True,
    end_time=2000.0,                # SIMPLE iterations
    write_interval=200.0,
)

# ------------------------------------------------------------------
# 3. Build the case
# ------------------------------------------------------------------
builder = CaseBuilder(
    case_name="ShadowHawk_SH200_30ms",
    output_dir="/home/ubuntu/OpenFOAM/ubuntu-13/run",
    mesh_config=mesh,
    physics_config=physics,
    of_source="/opt/openfoam13/etc/bashrc",
)

result = builder.build()

# ------------------------------------------------------------------
# 4. Inspect result
# ------------------------------------------------------------------
print("\n=== OF13 Case Build Result ===")
print(f"  Case path   : {result['case_path']}")
print(f"  Cell count  : {result['cell_count']:,}")
print(f"  Mesh quality: {result['mesh_quality']}")
print(f"  Ready to run: {result['ready_to_run']}")
print(f"\nTo run:\n  {result['foamRun_cmd']}")

# ------------------------------------------------------------------
# 5. AoA sweep example (as a Python API)
# ------------------------------------------------------------------
import math

def build_aoa_sweep(step_file: str, run_dir: str, velocities_ms: list, aoa_deg_list: list):
    """
    Generate a matrix of OF13 cases over velocity × AoA combinations.
    Each case is independently ready to foamRun.
    Returns list of result dicts.
    """
    results = []
    for U in velocities_ms:
        for aoa in aoa_deg_list:
            aoa_rad = math.radians(aoa)
            Ux = U * math.cos(aoa_rad)
            Uz = U * math.sin(aoa_rad)   # pitch-up in XZ plane

            m = MeshConfig(geometry_path=step_file, n_cores=4)
            p = PhysicsConfig(
                velocity=(Ux, 0.0, Uz),
                nu=1.5e-5,
            )
            b = CaseBuilder(
                case_name=f"sweep_U{int(U)}_AoA{aoa}",
                output_dir=run_dir,
                mesh_config=m,
                physics_config=p,
            )
            results.append(b.build())

    return results

# Example: 5 velocities × 5 AoA angles = 25 cases
# results = build_aoa_sweep(
#     step_file="/models/uav.step",
#     run_dir="/foam_run",
#     velocities_ms=[20, 25, 30, 35, 40],
#     aoa_deg_list=[-4, -2, 0, 2, 4],
# )
