"""OF13 Foundation fvSolution template (SIMPLE/PIMPLE)."""

from __future__ import annotations
from textwrap import dedent
from of13_factory.physics_config import PhysicsConfig


def render(physics: PhysicsConfig) -> str:
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
