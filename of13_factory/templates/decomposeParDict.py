"""OF13 decomposeParDict template."""

from __future__ import annotations
from textwrap import dedent


def render(n_cores: int) -> str:
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
