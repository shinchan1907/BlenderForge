"""Tests for deterministic validation functions."""

from pathlib import Path
from blenderforge.evaluation.validators import (
    validate_3d_printability,
    validate_dimensions,
    validate_image_artifact,
    validate_mesh_topology,
)


def test_validate_mesh_topology_valid():
    rep = validate_mesh_topology(
        vertex_count=8,
        edge_count=12,
        face_count=6,
        non_manifold_edges=0,
        loose_vertices=0,
    )
    assert rep.passed is True
    assert rep.score == 1.0
    assert len(rep.issues) == 0


def test_validate_mesh_topology_non_manifold():
    rep = validate_mesh_topology(
        vertex_count=10,
        edge_count=15,
        face_count=8,
        non_manifold_edges=3,
        require_manifold=True,
    )
    assert rep.passed is False
    assert any(iss.check == "non_manifold_edges" for iss in rep.issues)


def test_validate_dimensions():
    # Within tolerance
    rep1 = validate_dimensions((2.0001, 2.0002, 2.0), (2.0, 2.0, 2.0), tolerance=1e-3)
    assert rep1.passed is True

    # Exceeding tolerance
    rep2 = validate_dimensions((2.1, 2.0, 2.0), (2.0, 2.0, 2.0), tolerance=1e-3)
    assert rep2.passed is False


def test_validate_3d_printability():
    # Valid print volume
    rep = validate_3d_printability(
        is_manifold=True,
        bounding_box=(50.0, 50.0, 50.0),
        volume=125000.0,
    )
    assert rep.passed is True

    # Inverted or non-manifold
    rep_bad = validate_3d_printability(
        is_manifold=False,
        bounding_box=(50.0, 50.0, 50.0),
        volume=0.0,
    )
    assert rep_bad.passed is False
