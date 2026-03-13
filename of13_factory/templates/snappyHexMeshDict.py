"""OF13 Foundation snappyHexMeshDict template."""

from __future__ import annotations
from textwrap import dedent
from of13_factory.mesh_config import MeshConfig


def render(mesh: MeshConfig, stl_name: str) -> str:
    rmin, rmax = mesh.refinement_levels
    emesh_name = stl_name.replace(".stl", ".eMesh")
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
                {{ file "{emesh_name}"; level {rmin}; }}
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
