"""OF13 initial/boundary condition field templates: U, p, k, omega, nut."""

from __future__ import annotations
from textwrap import dedent
from of13_factory.physics_config import PhysicsConfig


def render_U(physics: PhysicsConfig) -> str:
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


def render_p(physics: PhysicsConfig) -> str:
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


def render_k(physics: PhysicsConfig) -> str:
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


def render_omega(physics: PhysicsConfig) -> str:
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


def render_nut(physics: PhysicsConfig) -> str:
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


def render_physicalProperties(physics: PhysicsConfig) -> str:
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


def render_momentumTransport(physics: PhysicsConfig) -> str:
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
