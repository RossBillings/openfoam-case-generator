"""OF13 Foundation blockMeshDict template — auto-sized from STL bounding box."""

from __future__ import annotations
from textwrap import dedent
from typing import Tuple
from of13_factory.mesh_config import MeshConfig


def render(
    bbox: Tuple[float, float, float, float, float, float],
    mesh: MeshConfig,
) -> str:
    xmin, xmax, ymin, ymax, zmin, zmax = bbox
    cx = (xmin + xmax) / 2
    cy = (ymin + ymax) / 2
    cz = (zmin + zmax) / 2
    ref_len = max(xmax - xmin, ymax - ymin, zmax - zmin)

    x0 = cx - mesh.upstream_scale * ref_len
    x1 = cx + mesh.downstream_scale * ref_len
    half = mesh.domain_scale / 2 * ref_len
    y0, y1 = cy - half, cy + half
    z0, z1 = cz - half, cz + half

    # Background hex resolution: aim for ~50 cells across shortest span
    n = max(10, int(50 * (x1 - x0) / (2 * half)))
    nx = n
    ny = max(10, int(n * (y1 - y0) / (x1 - x0)))
    nz = max(10, int(n * (z1 - z0) / (x1 - x0)))

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
