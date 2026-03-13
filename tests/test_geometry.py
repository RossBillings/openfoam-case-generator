"""Tests for geometry conversion and STL bounding box parsing."""

from __future__ import annotations

import struct
import tempfile
from pathlib import Path

import pytest

from of13_factory.geometry import get_stl_bounding_box


def _write_binary_stl(path: Path, triangles: list) -> None:
    """Write a minimal binary STL for testing."""
    with open(path, "wb") as f:
        f.write(b"\x00" * 80)  # header (no "solid" to flag as binary)
        f.write(struct.pack("<I", len(triangles)))
        for tri in triangles:
            normal, v1, v2, v3 = tri
            f.write(struct.pack("<fff", *normal))
            f.write(struct.pack("<fff", *v1))
            f.write(struct.pack("<fff", *v2))
            f.write(struct.pack("<fff", *v3))
            f.write(struct.pack("<H", 0))  # attrib


def test_bounding_box_binary_stl():
    with tempfile.TemporaryDirectory() as tmp:
        stl = Path(tmp) / "box.stl"
        # One triangle with known extents
        triangles = [
            ((0, 0, 1), (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.5, 2.0, 3.0)),
        ]
        _write_binary_stl(stl, triangles)
        xmin, xmax, ymin, ymax, zmin, zmax = get_stl_bounding_box(stl)
        assert xmin == pytest.approx(0.0)
        assert xmax == pytest.approx(1.0)
        assert ymin == pytest.approx(0.0)
        assert ymax == pytest.approx(2.0)
        assert zmin == pytest.approx(0.0)
        assert zmax == pytest.approx(3.0)


def test_bounding_box_ascii_stl():
    with tempfile.TemporaryDirectory() as tmp:
        stl = Path(tmp) / "box.stl"
        stl.write_text(
            "solid test\n"
            "  facet normal 0 0 1\n"
            "    outer loop\n"
            "      vertex -1.0 -2.0 0.0\n"
            "      vertex  4.0  0.0 0.0\n"
            "      vertex  0.0  5.0 6.0\n"
            "    endloop\n"
            "  endfacet\n"
            "endsolid test\n"
        )
        xmin, xmax, ymin, ymax, zmin, zmax = get_stl_bounding_box(stl)
        assert xmin == pytest.approx(-1.0)
        assert xmax == pytest.approx(4.0)
        assert ymin == pytest.approx(-2.0)
        assert ymax == pytest.approx(5.0)
        assert zmin == pytest.approx(0.0)
        assert zmax == pytest.approx(6.0)
