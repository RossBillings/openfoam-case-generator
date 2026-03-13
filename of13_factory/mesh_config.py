from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


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
