"""
of13_factory
============
Python API for generating validated OpenFOAM v13 case directories
from STEP/IGES geometry files (Creo/CATIA output).

Target physics: Incompressible external aerodynamics (UAV/aircraft)
Solver module:  incompressibleFluid (foamRun)
Mesh engine:    snappyHexMesh

Install deps:
    pip install pythonocc-core jinja2 numpy

OF13 must be sourced in the environment before CaseBuilder.build() is called:
    source /opt/openfoam13/etc/bashrc

Usage:
    from of13_factory import CaseBuilder, MeshConfig, PhysicsConfig

    mesh = MeshConfig(
        geometry_path="uav.step",
        domain_scale=20.0,
        refinement_levels=(3, 5),
        n_bl_layers=5,
    )
    physics = PhysicsConfig(
        velocity=(30.0, 0.0, 0.0),
        nu=1.5e-5,
        turbulence_model="kOmegaSST",
    )
    builder = CaseBuilder("IstariOneUAV1", "/foam_run", mesh, physics)
    result = builder.build()
    print(result)
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from textwrap import dedent
from typing import Optional, Tuple

# ---------------------------------------------------------------------------
# Geometry conversion: STEP/IGES → STL via pythonocc-core
# ---------------------------------------------------------------------------

def _step_iges_to_stl(src: Path, stl_out: Path, linear_deflection: float = 0.01) -> None:
    """
    Convert a STEP or IGES file to a watertight binary STL using
    pythonocc-core (OpenCASCADE). Runs fully headless — no GUI required.

    linear_deflection: tessellation chord tolerance in model units (metres).
    Smaller = finer surface mesh = larger STL. 0.01 is a good starting point
    for a ~1m UAV; scale down for smaller geometry.
    """
    try:
        from OCC.Core.STEPControl import STEPControl_Reader
        from OCC.Core.IGESControl import IGESControl_Reader
        from OCC.Core.IFSelect import IFSelect_RetDone
        from OCC.Core.BRep import BRep_Builder
        from OCC.Core.TopoDS import TopoDS_Compound
        from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh
        from OCC.Core.StlAPI import StlAPI_Writer
        from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_Sewing
    except ImportError as e:
        raise ImportError(
            "pythonocc-core is required for STEP/IGES conversion.\n"
            "Install: conda install -c conda-forge pythonocc-core\n"
            f"Original error: {e}"
        )

    ext = src.suffix.lower()
    if ext in (".step", ".stp"):
        reader = STEPControl_Reader()
    elif ext in (".iges", ".igs"):
        reader = IGESControl_Reader()
    else:
        raise ValueError(f"Unsupported geometry format: {ext}. Expected .step/.stp/.iges/.igs")

    status = reader.ReadFile(str(src))
    if status != IFSelect_RetDone:
        raise RuntimeError(f"Failed to read geometry file: {src}")

    reader.TransferRoots()
    n_shapes = reader.NbShapes()
    if n_shapes == 0:
        raise RuntimeError(f"No shapes found in geometry file: {src}")

    # Sew all bodies into one solid (handles multi-body STEP assemblies from Creo/CATIA)
    sewer = BRepBuilderAPI_Sewing(1e-4)
    for i in range(1, n_shapes + 1):
        sewer.Add(reader.Shape(i))
    sewer.Perform()
    shape = sewer.SewedShape()

    # Tessellate the B-Rep surface into triangles
    mesh = BRepMesh_IncrementalMesh(shape, linear_deflection, False, 0.5, True)
    mesh.Perform()
    if not mesh.IsDone():
        raise RuntimeError("BRepMesh tessellation failed — check geometry for open surfaces")

    # Write binary STL
    writer = StlAPI_Writer()
    writer.SetASCIIMode(False)
    ok = writer.Write(shape, str(stl_out))
    if not ok:
        raise RuntimeError(f"STL write failed to: {stl_out}")


def _get_stl_bounding_box(stl_path: Path) -> Tuple[float, float, float, float, float, float]:
    """
    Return (xmin, xmax, ymin, ymax, zmin, zmax) by scanning STL vertices.
    Works on ASCII or binary STL without external deps.
    """
    import struct
    coords = []
    with open(stl_path, "rb") as f:
        header = f.read(80)
        is_binary = b"solid" not in header[:5]
        if is_binary:
            f.seek(80)
            n_tri = struct.unpack("<I", f.read(4))[0]
            for _ in range(n_tri):
                f.read(12)  # normal
                for _ in range(3):
                    coords.append(struct.unpack("<fff", f.read(12)))
                f.read(2)   # attrib
        else:
            f.seek(0)
            for line in f.read().decode("utf-8", errors="ignore").splitlines():
                line = line.strip()
                if line.startswith("vertex"):
                    parts = line.split()
                    coords.append((float(parts[1]), float(parts[2]), float(parts[3])))

    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    zs = [c[2] for c in coords]
    return min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)


# ---------------------------------------------------------------------------
# Configuration dataclasses
# ---------------------------------------------------------------------------

@dataclass
class MeshConfig:
    """
    Mesh generation parameters for snappyHexMesh external aero cases.

    geometry_path:      Path to STEP or IGES file (Creo/CATIA export)
    domain_scale:       Background box half-width as multiple of bounding box
                        longest dimension. 20 = good for external aero.
    upstream_scale:     Domain extent upstream (body lengths)
    downstream_scale:   Domain extent downstream (body lengths)
    refinement_levels:  (min, max) snappyHexMesh surface refinement levels
    n_bl_layers:        Number of boundary layer prism layers
    bl_expansion_ratio: Growth rate of BL layers
    linear_deflection:  OCC tessellation tolerance (metres). Lower = finer STL.
    max_cells:          Approximate cell budget (snappyHexMesh maxLocalCells)
    n_cores:            Parallel cores for decomposePar + mesh
    """
    geometry_path: str
    domain_scale: float = 20.0
    upstream_scale: float = 10.0
    downstream_scale: float = 20.0
    refinement_levels: Tuple[int, int] = (3, 5)
    n_bl_layers: int = 5
    bl_expansion_ratio: float = 1.2
    linear_deflection: float = 0.01
    max_cells: int = 5_000_000
    n_cores: int = 4


@dataclass
class PhysicsConfig:
    """
    Physics parameters for incompressible external aerodynamics.

    velocity:           Freestream velocity vector (m/s). AoA encoded here.
    nu:                 Kinematic viscosity (m²/s). Air at 20°C = 1.5e-5.
    turbulence_model:   OF13 momentumTransport model name.
    turbulence_intensity: Freestream Tu (fraction). 0.001 = clean tunnel.
    turbulent_length_scale: Integral length scale (m). ~1% of ref length.
    steady_state:       True = SIMPLE, False = PIMPLE transient.
    end_time:           Simulation end time (iterations for steady, s for transient).
    write_interval:     Write output every N steps/seconds.
    """
    velocity: Tuple[float, float, float] = (30.0, 0.0, 0.0)
    nu: float = 1.5e-5
    turbulence_model: str = "kOmegaSST"
    turbulence_intensity: float = 0.001
    turbulent_length_scale: float = 0.05
    steady_state: bool = True
    end_time: float = 1000.0
    write_interval: float = 100.0

    @property
    def U_mag(self) -> float:
        return math.sqrt(sum(v**2 for v in self.velocity))

    @property
    def k_inlet(self) -> float:
        """Turbulent kinetic energy from intensity: k = 1.5*(U*Tu)^2"""
        return 1.5 * (self.U_mag * self.turbulence_intensity) ** 2

    @property
    def omega_inlet(self) -> float:
        """Specific dissipation: omega = sqrt(k) / (Cmu^0.25 * L)"""
        Cmu = 0.09
        return math.sqrt(self.k_inlet) / (Cmu**0.25 * self.turbulent_length_scale)

    @property
    def nut_inlet(self) -> float:
        """Turbulent viscosity: nut = k / omega"""
        return self.k_inlet / max(self.omega_inlet, 1e-10)


# ---------------------------------------------------------------------------
# OF13 dict templates (Jinja2-free — f-strings for zero extra deps)
# These are validated against OpenFOAM Foundation v13 tutorials.
# ---------------------------------------------------------------------------

def _render_controlDict(physics: PhysicsConfig) -> str:
    algorithm = "SIMPLE" if physics.steady_state else "PIMPLE"
    return dedent(f"""\
        FoamFile
        {{
            version     2.0;
            format      ascii;
            class       dictionary;
            object      controlDict;
        }}

        application     foamRun;

        libs            ("libincompressibleTurbulenceModels.so");

        solver          incompressibleFluid;

        startFrom       startTime;
        startTime       0;
        stopAt          endTime;
        endTime         {physics.end_time:.6g};
        deltaT          1;

        writeControl    timeStep;
        writeInterval   {int(physics.write_interval)};
        purgeWrite      3;
        writeFormat     ascii;
        writePrecision  8;
        writeCompression off;
        timeFormat      general;
        timePrecision   6;
        runTimeModifiable true;

        functions
        {{
            forces
            {{
                type            forces;
                libs            ("libforces.so");
                writeControl    timeStep;
                writeInterval   {int(physics.write_interval)};
                patches         (body);
                rho             rhoInf;
                rhoInf          1.225;
                CofR            (0 0 0);
            }}
            residuals
            {{
                type            solverInfo;
                libs            ("libutilityFunctionObjects.so");
                fields          (U p k omega);
            }}
        }}
    """)


def _render_fvSchemes(physics: PhysicsConfig) -> str:
    div_scheme = "bounded Gauss linearUpwind grad(U)" if physics.steady_state else "Gauss linearUpwind grad(U)"
    return dedent(f"""\
        FoamFile
        {{
            version     2.0;
            format      ascii;
            class       dictionary;
            object      fvSchemes;
        }}

        ddtSchemes      {{ default         steadyState; }}
        gradSchemes     {{ default         Gauss linear; }}
        divSchemes
        {{
            default                             none;
            div(phi,U)                          {div_scheme};
            div(phi,k)                          bounded Gauss upwind;
            div(phi,omega)                      bounded Gauss upwind;
            div((nuEff*dev2(T(grad(U)))))       Gauss linear;
        }}
        laplacianSchemes {{ default         Gauss linear corrected; }}
        interpolationSchemes {{ default     linear; }}
        snGradSchemes    {{ default         corrected; }}
    """)


def _render_fvSolution(physics: PhysicsConfig) -> str:
    return dedent(f"""\
        FoamFile
        {{
            version     2.0;
            format      ascii;
            class       dictionary;
            object      fvSolution;
        }}

        solvers
        {{
            p
            {{
                solver          GAMG;
                smoother        GaussSeidel;
                tolerance       1e-7;
                relTol          0.01;
            }}
            "(U|k|omega)"
            {{
                solver          smoothSolver;
                smoother        symGaussSeidel;
                tolerance       1e-8;
                relTol          0.1;
            }}
        }}

        SIMPLE
        {{
            nNonOrthogonalCorrectors 0;
            consistent      yes;
            residualControl
            {{
                p               1e-4;
                U               1e-4;
                "(k|omega)"     1e-4;
            }}
        }}

        relaxationFactors
        {{
            equations
            {{
                U               0.9;
                k               0.7;
                omega           0.7;
            }}
        }}
    """)


def _render_U(physics: PhysicsConfig) -> str:
    Ux, Uy, Uz = physics.velocity
    return dedent(f"""\
        FoamFile
        {{
            version     2.0;
            format      ascii;
            class       volVectorField;
            object      U;
        }}

        dimensions      [0 1 -1 0 0 0 0];
        internalField   uniform ({Ux} {Uy} {Uz});

        boundaryField
        {{
            inlet
            {{
                type            fixedValue;
                value           uniform ({Ux} {Uy} {Uz});
            }}
            outlet
            {{
                type            inletOutlet;
                inletValue      uniform (0 0 0);
                value           uniform ({Ux} {Uy} {Uz});
            }}
            body
            {{
                type            noSlip;
            }}
            "(top|bottom|sides)"
            {{
                type            slip;
            }}
        }}
    """)


def _render_p(physics: PhysicsConfig) -> str:
    return dedent("""\
        FoamFile
        {
            version     2.0;
            format      ascii;
            class       volScalarField;
            object      p;
        }

        dimensions      [0 2 -2 0 0 0 0];
        internalField   uniform 0;

        boundaryField
        {
            inlet
            {
                type            zeroGradient;
            }
            outlet
            {
                type            fixedValue;
                value           uniform 0;
            }
            body
            {
                type            zeroGradient;
            }
            "(top|bottom|sides)"
            {
                type            slip;
            }
        }
    """)


def _render_k(physics: PhysicsConfig) -> str:
    k = physics.k_inlet
    return dedent(f"""\
        FoamFile
        {{
            version     2.0;
            format      ascii;
            class       volScalarField;
            object      k;
        }}

        dimensions      [0 2 -2 0 0 0 0];
        internalField   uniform {k:.6e};

        boundaryField
        {{
            inlet           {{ type fixedValue; value uniform {k:.6e}; }}
            outlet          {{ type inletOutlet; inletValue uniform {k:.6e}; value uniform {k:.6e}; }}
            body            {{ type kqRWallFunction; value uniform {k:.6e}; }}
            "(top|bottom|sides)" {{ type slip; }}
        }}
    """)


def _render_omega(physics: PhysicsConfig) -> str:
    om = physics.omega_inlet
    return dedent(f"""\
        FoamFile
        {{
            version     2.0;
            format      ascii;
            class       volScalarField;
            object      omega;
        }}

        dimensions      [0 0 -1 0 0 0 0];
        internalField   uniform {om:.6e};

        boundaryField
        {{
            inlet           {{ type fixedValue; value uniform {om:.6e}; }}
            outlet          {{ type inletOutlet; inletValue uniform {om:.6e}; value uniform {om:.6e}; }}
            body            {{ type omegaWallFunction; value uniform {om:.6e}; }}
            "(top|bottom|sides)" {{ type slip; }}
        }}
    """)


def _render_nut(physics: PhysicsConfig) -> str:
    nut = physics.nut_inlet
    return dedent(f"""\
        FoamFile
        {{
            version     2.0;
            format      ascii;
            class       volScalarField;
            object      nut;
        }}

        dimensions      [0 2 -1 0 0 0 0];
        internalField   uniform {nut:.6e};

        boundaryField
        {{
            inlet           {{ type calculated; value uniform {nut:.6e}; }}
            outlet          {{ type calculated; value uniform {nut:.6e}; }}
            body            {{ type nutUSpaldingWallFunction; value uniform {nut:.6e}; }}
            "(top|bottom|sides)" {{ type slip; }}
        }}
    """)


def _render_physicalProperties(physics: PhysicsConfig) -> str:
    return dedent(f"""\
        FoamFile
        {{
            version     2.0;
            format      ascii;
            class       dictionary;
            object      physicalProperties;
        }}

        viscosityModel  constant;
        nu              {physics.nu:.6e};
    """)


def _render_momentumTransport(physics: PhysicsConfig) -> str:
    return dedent(f"""\
        FoamFile
        {{
            version     2.0;
            format      ascii;
            class       dictionary;
            object      momentumTransport;
        }}

        simulationType  RAS;
        RAS
        {{
            model           {physics.turbulence_model};
            turbulence      on;
            printCoeffs     on;
        }}
    """)


def _render_blockMeshDict(
    bbox: Tuple[float, float, float, float, float, float],
    mesh: MeshConfig,
) -> str:
    xmin, xmax, ymin, ymax, zmin, zmax = bbox
    cx = (xmin + xmax) / 2
    cy = (ymin + ymax) / 2
    cz = (zmin + zmax) / 2
    ref_len = max(xmax - xmin, ymax - ymin, zmax - zmin)

    # Domain extents (body-length scaled)
    x0 = cx - mesh.upstream_scale * ref_len
    x1 = cx + mesh.downstream_scale * ref_len
    half = mesh.domain_scale / 2 * ref_len
    y0, y1 = cy - half, cy + half
    z0, z1 = cz - half, cz + half

    # Background hex resolution: aim for ~50 cells across shortest span
    n = max(10, int(50 * (x1 - x0) / (2 * half)))
    nx, ny, nz = n, max(10, int(n * (y1 - y0) / (x1 - x0))), max(10, int(n * (z1 - z0) / (x1 - x0)))

    return dedent(f"""\
        FoamFile
        {{
            version     2.0;
            format      ascii;
            class       dictionary;
            object      blockMeshDict;
        }}

        scale   1;

        vertices
        (
            ({x0:.4f} {y0:.4f} {z0:.4f})
            ({x1:.4f} {y0:.4f} {z0:.4f})
            ({x1:.4f} {y1:.4f} {z0:.4f})
            ({x0:.4f} {y1:.4f} {z0:.4f})
            ({x0:.4f} {y0:.4f} {z1:.4f})
            ({x1:.4f} {y0:.4f} {z1:.4f})
            ({x1:.4f} {y1:.4f} {z1:.4f})
            ({x0:.4f} {y1:.4f} {z1:.4f})
        );

        blocks
        (
            hex (0 1 2 3 4 5 6 7) ({nx} {ny} {nz}) simpleGrading (1 1 1)
        );

        boundary
        (
            inlet  {{ type patch; faces ((0 4 7 3)); }}
            outlet {{ type patch; faces ((1 2 6 5)); }}
            top    {{ type symmetryPlane; faces ((3 7 6 2)); }}
            bottom {{ type symmetryPlane; faces ((0 1 5 4)); }}
            sides  {{ type symmetryPlane; faces ((0 3 2 1) (4 5 6 7)); }}
        );
    """)


def _render_snappyHexMeshDict(mesh: MeshConfig, stl_name: str) -> str:
    rmin, rmax = mesh.refinement_levels
    return dedent(f"""\
        FoamFile
        {{
            version     2.0;
            format      ascii;
            class       dictionary;
            object      snappyHexMeshDict;
        }}

        castellatedMesh true;
        snap            true;
        addLayers       true;

        geometry
        {{
            {stl_name}
            {{
                type triSurfaceMesh;
                file "{stl_name}";
                regions {{ body {{ name body; }} }}
            }}
        }}

        castellatedMeshControls
        {{
            maxLocalCells       {mesh.max_cells};
            maxGlobalCells      {mesh.max_cells * 2};
            minRefinementCells  10;
            maxLoadUnbalance    0.10;
            nCellsBetweenLevels 3;
            resolveFeatureAngle 30;
            allowFreeStandingZoneFaces true;

            features
            (
                {{ file "{stl_name.replace('.stl', '.eMesh')}"; level {rmin}; }}
            );

            refinementSurfaces
            {{
                {stl_name}
                {{
                    level ({rmin} {rmax});
                    regions {{ body {{ level ({rmin} {rmax}); patchInfo {{ type wall; }} }} }}
                }}
            }}

            refinementRegions {{}}
            locationInMesh (99999 99999 99999);  // far from body — SET THIS to a point in the fluid domain
        }}

        snapControls
        {{
            nSmoothPatch        3;
            tolerance           2.0;
            nSolveIter          30;
            nRelaxIter          5;
            nFeatureSnapIter    10;
            implicitFeatureSnap false;
            explicitFeatureSnap true;
            multiRegionFeatureSnap false;
        }}

        addLayersControls
        {{
            relativeSizes       true;
            layers
            {{
                body {{ nSurfaceLayers {mesh.n_bl_layers}; }}
            }}
            expansionRatio      {mesh.bl_expansion_ratio};
            finalLayerThickness 0.3;
            minThickness        0.1;
            nGrow               0;
            featureAngle        60;
            nRelaxIter          3;
            nSmoothSurfaceNormals 1;
            nSmoothNormals      3;
            nSmoothThickness    10;
            maxFaceThicknessRatio 0.5;
            maxThicknessToMedialRatio 0.3;
            minMedialAxisAngle  90;
            nBufferCellsNoExtrude 0;
            nLayerIter          50;
        }}

        meshQualityControls
        {{
            maxNonOrtho         65;
            maxBoundarySkewness 20;
            maxInternalSkewness 4;
            maxConcave          80;
            minFlatness         0.5;
            minVol              1e-13;
            minTetQuality       -1;
            minArea             -1;
            minTwist            0.02;
            minDeterminant      0.001;
            minFaceWeight       0.05;
            minVolRatio         0.01;
            minTriangleTwist    -1;
            nSmoothScale        4;
            errorReduction      0.75;
        }}

        mergeTolerance      1e-6;
    """)


def _render_decomposeParDict(n_cores: int) -> str:
    return dedent(f"""\
        FoamFile
        {{
            version     2.0;
            format      ascii;
            class       dictionary;
            object      decomposeParDict;
        }}

        numberOfSubdomains  {n_cores};
        method              scotch;
    """)


# ---------------------------------------------------------------------------
# CaseBuilder
# ---------------------------------------------------------------------------

class CaseBuilder:
    """
    Builds a complete, foamRun-ready OF13 case directory from STEP/IGES input.

    Parameters
    ----------
    case_name   : str        — name of the case directory to create
    output_dir  : str        — parent directory where case_name/ is written
    mesh_config : MeshConfig
    physics_config : PhysicsConfig
    of_source   : str        — path to OF13 bashrc; defaults to /opt/openfoam13/etc/bashrc
    """

    def __init__(
        self,
        case_name: str,
        output_dir: str,
        mesh_config: MeshConfig,
        physics_config: PhysicsConfig,
        of_source: str = "/opt/openfoam13/etc/bashrc",
    ):
        self.case_name = case_name
        self.output_dir = Path(output_dir)
        self.mesh = mesh_config
        self.physics = physics_config
        self.of_source = of_source
        self.case_dir = self.output_dir / case_name

    # ------------------------------------------------------------------
    def build(self) -> dict:
        """
        Execute the full build pipeline:
          1. Convert STEP/IGES → STL
          2. Compute bounding box → domain sizing
          3. Write all OF13 dict files
          4. Run blockMesh
          5. Run surfaceFeatureExtract
          6. Run snappyHexMesh
          7. Run checkMesh → capture quality metrics
        Returns dict with case_path, cell_count, mesh_quality, ready_to_run.
        """
        self._setup_dirs()

        # 1. Geometry conversion
        geo = Path(self.mesh.geometry_path)
        stl_name = geo.stem + ".stl"
        stl_path = self.case_dir / "constant" / "triSurface" / stl_name
        print(f"[of13_factory] Converting {geo.name} → {stl_name} ...")
        _step_iges_to_stl(geo, stl_path, self.mesh.linear_deflection)
        print(f"[of13_factory] STL written: {stl_path}")

        # 2. Bounding box
        bbox = _get_stl_bounding_box(stl_path)
        print(f"[of13_factory] Bounding box: {bbox}")

        # 3. Write dict files
        self._write_dicts(bbox, stl_name)
        print("[of13_factory] Case dict files written.")

        # 4–7. Run OF13 mesh utilities
        result = self._run_mesh_pipeline(stl_name)
        return result

    # ------------------------------------------------------------------
    def _setup_dirs(self):
        """Create the case directory skeleton."""
        for d in ["0", "constant/triSurface", "system"]:
            (self.case_dir / d).mkdir(parents=True, exist_ok=True)

    def _write_dicts(self, bbox, stl_name: str):
        m, p = self.mesh, self.physics
        writes = {
            "system/controlDict":       _render_controlDict(p),
            "system/fvSchemes":         _render_fvSchemes(p),
            "system/fvSolution":        _render_fvSolution(p),
            "system/blockMeshDict":     _render_blockMeshDict(bbox, m),
            "system/snappyHexMeshDict": _render_snappyHexMeshDict(m, stl_name),
            "system/decomposeParDict":  _render_decomposeParDict(m.n_cores),
            "0/U":                      _render_U(p),
            "0/p":                      _render_p(p),
            "0/k":                      _render_k(p),
            "0/omega":                  _render_omega(p),
            "0/nut":                    _render_nut(p),
            "constant/physicalProperties":  _render_physicalProperties(p),
            "constant/momentumTransport":   _render_momentumTransport(p),
        }
        for rel_path, content in writes.items():
            dest = self.case_dir / rel_path
            dest.write_text(content)

    def _of_run(self, cmd: str) -> subprocess.CompletedProcess:
        """Run an OF13 command sourcing the environment first."""
        full_cmd = f"bash -c 'source {self.of_source} && cd {self.case_dir} && {cmd}'"
        return subprocess.run(
            full_cmd, shell=True, capture_output=True, text=True
        )

    def _run_mesh_pipeline(self, stl_name: str) -> dict:
        steps = [
            ("blockMesh",               "blockMesh"),
            ("surfaceFeatureExtract",    "surfaceFeatureExtract"),
            ("snappyHexMesh",           f"snappyHexMesh -overwrite"),
            ("checkMesh",               "checkMesh -latestTime"),
        ]
        logs = {}
        for label, cmd in steps:
            print(f"[of13_factory] Running {label} ...")
            proc = self._of_run(cmd)
            logs[label] = proc.stdout + proc.stderr
            if proc.returncode != 0:
                raise RuntimeError(
                    f"{label} failed (rc={proc.returncode}):\n{logs[label][-2000:]}"
                )

        # Parse checkMesh output for key metrics
        check_log = logs["checkMesh"]
        cell_count = self._parse_cell_count(check_log)
        mesh_ok = "Mesh OK" in check_log

        return {
            "case_path":     str(self.case_dir),
            "cell_count":    cell_count,
            "mesh_quality":  "OK" if mesh_ok else "WARNINGS — review checkMesh log",
            "ready_to_run":  mesh_ok,
            "foamRun_cmd":   f"cd {self.case_dir} && foamRun",
            "logs":          logs,
        }

    @staticmethod
    def _parse_cell_count(log: str) -> Optional[int]:
        for line in log.splitlines():
            if "cells:" in line.lower():
                parts = line.split()
                for p in parts:
                    if p.isdigit():
                        return int(p)
        return None
