"""OF13 Foundation fvSchemes template."""

from __future__ import annotations
from textwrap import dedent
from of13_factory.physics_config import PhysicsConfig


def render(physics: PhysicsConfig) -> str:
    div_scheme = (
        "bounded Gauss linearUpwind grad(U)"
        if physics.steady_state
        else "Gauss linearUpwind grad(U)"
    )
    ddt = "steadyState" if physics.steady_state else "Euler"
    return dedent(f"""\
        FoamFile
        {{
            version     2.0;
            format      ascii;
            class       dictionary;
            object      fvSchemes;
        }}

        ddtSchemes      {{ default         {ddt}; }}
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
