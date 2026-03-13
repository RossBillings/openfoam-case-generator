"""
CaseBuilder: orchestrates the full STEP/IGES → OF13 case pipeline.

Requires OpenFOAM Foundation v13 sourced in the environment:
    source /opt/openfoam13/etc/bashrc
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from of13_factory.geometry import step_iges_to_stl, get_stl_bounding_box
from of13_factory.mesh_config import MeshConfig
from of13_factory.physics_config import PhysicsConfig
from of13_factory.templates import (
    controlDict,
    fvSchemes,
    fvSolution,
    blockMeshDict,
    snappyHexMeshDict,
    fields,
    decomposeParDict,
)


class CaseBuilder:
    """
    Builds a complete, foamRun-ready OF13 case directory from STEP/IGES input.

    Parameters
    ----------
    case_name      : str           — name of the case directory to create
    output_dir     : str           — parent directory where case_name/ is written
    mesh_config    : MeshConfig
    physics_config : PhysicsConfig
    of_source      : str           — path to OF13 bashrc
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

        Returns dict: case_path, cell_count, mesh_quality, ready_to_run, foamRun_cmd.
        """
        self._setup_dirs()

        geo = Path(self.mesh.geometry_path)
        stl_name = geo.stem + ".stl"
        stl_path = self.case_dir / "constant" / "triSurface" / stl_name

        print(f"[of13_factory] Converting {geo.name} → {stl_name} ...")
        step_iges_to_stl(geo, stl_path, self.mesh.linear_deflection)
        print(f"[of13_factory] STL written: {stl_path}")

        bbox = get_stl_bounding_box(stl_path)
        print(f"[of13_factory] Bounding box: {bbox}")

        self._write_dicts(bbox, stl_name)
        print("[of13_factory] Case dict files written.")

        return self._run_mesh_pipeline(stl_name)

    def _setup_dirs(self) -> None:
        for d in ["0", "constant/triSurface", "system"]:
            (self.case_dir / d).mkdir(parents=True, exist_ok=True)

    def _write_dicts(self, bbox, stl_name: str) -> None:
        m, p = self.mesh, self.physics
        writes = {
            "system/controlDict":           controlDict.render(p),
            "system/fvSchemes":             fvSchemes.render(p),
            "system/fvSolution":            fvSolution.render(p),
            "system/blockMeshDict":         blockMeshDict.render(bbox, m),
            "system/snappyHexMeshDict":     snappyHexMeshDict.render(m, stl_name),
            "system/decomposeParDict":      decomposeParDict.render(m.n_cores),
            "0/U":                          fields.render_U(p),
            "0/p":                          fields.render_p(p),
            "0/k":                          fields.render_k(p),
            "0/omega":                      fields.render_omega(p),
            "0/nut":                        fields.render_nut(p),
            "constant/physicalProperties":  fields.render_physicalProperties(p),
            "constant/momentumTransport":   fields.render_momentumTransport(p),
        }
        for rel_path, content in writes.items():
            (self.case_dir / rel_path).write_text(content)

    def _of_run(self, cmd: str) -> subprocess.CompletedProcess:
        full_cmd = f"bash -c 'source {self.of_source} && cd {self.case_dir} && {cmd}'"
        return subprocess.run(full_cmd, shell=True, capture_output=True, text=True)

    def _run_mesh_pipeline(self, stl_name: str) -> dict:
        steps = [
            ("blockMesh",            "blockMesh"),
            ("surfaceFeatureExtract", "surfaceFeatureExtract"),
            ("snappyHexMesh",        "snappyHexMesh -overwrite"),
            ("checkMesh",            "checkMesh -latestTime"),
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

        check_log = logs["checkMesh"]
        cell_count = self._parse_cell_count(check_log)
        mesh_ok = "Mesh OK" in check_log

        return {
            "case_path":    str(self.case_dir),
            "cell_count":   cell_count,
            "mesh_quality": "OK" if mesh_ok else "WARNINGS — review checkMesh log",
            "ready_to_run": mesh_ok,
            "foamRun_cmd":  f"cd {self.case_dir} && foamRun",
            "logs":         logs,
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
