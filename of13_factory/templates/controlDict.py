"""OF13 Foundation controlDict template (foamRun + incompressibleFluid)."""

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
