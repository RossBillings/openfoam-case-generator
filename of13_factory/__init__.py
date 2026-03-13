"""
of13_factory
============
Python API for generating validated OpenFOAM Foundation v13 case directories
from STEP/IGES geometry files (Creo/CATIA output).

Target physics: Incompressible external aerodynamics (UAV/aircraft)
Solver module:  incompressibleFluid (foamRun)
Mesh engine:    snappyHexMesh

Usage:
    from of13_factory import CaseBuilder, MeshConfig, PhysicsConfig

    mesh = MeshConfig(geometry_path="uav.step", domain_scale=20.0)
    physics = PhysicsConfig(velocity=(30.0, 0.0, 0.0))
    builder = CaseBuilder("my_case", "/foam_run", mesh, physics)
    result = builder.build()
"""

from of13_factory.builder import CaseBuilder
from of13_factory.mesh_config import MeshConfig
from of13_factory.physics_config import PhysicsConfig

__all__ = ["CaseBuilder", "MeshConfig", "PhysicsConfig"]
__version__ = "0.1.0"
