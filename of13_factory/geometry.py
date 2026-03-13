"""
Geometry conversion: STEP/IGES → watertight binary STL.

Uses cadquery (pip-installable) as the OCC backend instead of pythonocc-core.
cadquery wraps the same OpenCASCADE geometry kernel and runs fully headless.

Install: uv pip install cadquery
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Tuple


def step_iges_to_stl(
    src: Path,
    stl_out: Path,
    linear_deflection: float = 0.01,
) -> None:
    """
    Convert a STEP or IGES file to a watertight binary STL.

    linear_deflection: tessellation chord tolerance in model units (metres).
    Smaller = finer surface mesh = larger STL. 0.01 is a good starting point
    for a ~1m UAV; scale down for smaller geometry.
    """
    try:
        import cadquery as cq
        from cadquery import exporters
    except ImportError as e:
        raise ImportError(
            "cadquery is required for STEP/IGES conversion.\n"
            "Install: uv pip install cadquery\n"
            f"Original error: {e}"
        )

    ext = src.suffix.lower()
    if ext in (".step", ".stp"):
        shape = cq.importers.importStep(str(src))
    elif ext in (".iges", ".igs"):
        # cadquery doesn't expose a top-level importIges; use the OCC backend directly
        from cadquery.occ_impl.importers import importShape as _occ_import
        from OCC.Core.IGESControl import IGESControl_Reader
        from OCC.Core.IFSelect import IFSelect_RetDone

        reader = IGESControl_Reader()
        status = reader.ReadFile(str(src))
        if status != IFSelect_RetDone:
            raise RuntimeError(f"Failed to read IGES file: {src}")
        reader.TransferRoots()
        occ_shape = reader.OneShape()
        shape = cq.Workplane().newObject([cq.Shape(occ_shape)])
    else:
        raise ValueError(
            f"Unsupported geometry format: {ext}. Expected .step/.stp/.iges/.igs"
        )

    stl_out.parent.mkdir(parents=True, exist_ok=True)
    exporters.export(shape, str(stl_out), tolerance=linear_deflection)


def get_stl_bounding_box(
    stl_path: Path,
) -> Tuple[float, float, float, float, float, float]:
    """
    Return (xmin, xmax, ymin, ymax, zmin, zmax) by scanning STL vertices.
    Works on ASCII or binary STL without external deps.
    """
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
                f.read(2)  # attrib
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
