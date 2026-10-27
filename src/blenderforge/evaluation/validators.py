"""Deterministic validators for mesh topology, scene structure, shaders, and printability."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field


class ValidationIssue(BaseModel):
    severity: str = "error"  # "error", "warning", "info"
    check: str
    message: str
    details: Optional[Dict[str, Any]] = None


class ValidationReport(BaseModel):
    passed: bool
    score: float = 1.0  # 0.0 to 1.0
    issues: List[ValidationIssue] = Field(default_factory=list)
    metrics: Dict[str, Any] = Field(default_factory=dict)


def validate_mesh_topology(
    vertex_count: int,
    edge_count: int,
    face_count: int,
    non_manifold_edges: int = 0,
    loose_vertices: int = 0,
    require_manifold: bool = True,
    expected_vertex_range: Optional[Tuple[int, int]] = None,
) -> ValidationReport:
    """Validate mesh connectivity, manifoldness, and topology limits."""
    issues: List[ValidationIssue] = []

    if vertex_count <= 0 or face_count <= 0:
        issues.append(ValidationIssue(
            severity="error",
            check="mesh_empty",
            message=f"Mesh has no geometry: {vertex_count} vertices, {face_count} faces."
        ))

    if require_manifold and non_manifold_edges > 0:
        issues.append(ValidationIssue(
            severity="error",
            check="non_manifold_edges",
            message=f"Mesh contains {non_manifold_edges} non-manifold edges. Model is not 2-manifold.",
            details={"non_manifold_count": non_manifold_edges}
        ))

    if loose_vertices > 0:
        issues.append(ValidationIssue(
            severity="warning",
            check="loose_vertices",
            message=f"Mesh contains {loose_vertices} loose disconnected vertices."
        ))

    if expected_vertex_range:
        min_v, max_v = expected_vertex_range
        if not (min_v <= vertex_count <= max_v):
            issues.append(ValidationIssue(
                severity="error",
                check="vertex_count_out_of_bounds",
                message=f"Vertex count {vertex_count} outside expected range [{min_v}, {max_v}]."
            ))

    passed = not any(iss.severity == "error" for iss in issues)
    score = 1.0 if passed else max(0.0, 1.0 - (len(issues) * 0.25))

    return ValidationReport(
        passed=passed,
        score=score,
        issues=issues,
        metrics={
            "vertices": vertex_count,
            "edges": edge_count,
            "faces": face_count,
            "non_manifold_edges": non_manifold_edges,
            "loose_vertices": loose_vertices,
        }
    )


def validate_dimensions(
    actual_dimensions: Tuple[float, float, float],
    expected_dimensions: Tuple[float, float, float],
    tolerance: float = 1e-3
) -> ValidationReport:
    """Verify dimensional accuracy against target measurements."""
    issues: List[ValidationIssue] = []
    axes = ["x", "y", "z"]

    for i in range(3):
        diff = abs(actual_dimensions[i] - expected_dimensions[i])
        if diff > tolerance:
            issues.append(ValidationIssue(
                severity="error",
                check=f"dimension_{axes[i]}",
                message=f"Dimension {axes[i]} diff {diff:.5f} exceeds tolerance {tolerance:.5f} (actual {actual_dimensions[i]}, expected {expected_dimensions[i]})."
            ))

    passed = len(issues) == 0
    return ValidationReport(
        passed=passed,
        score=1.0 if passed else 0.0,
        issues=issues,
        metrics={"actual": list(actual_dimensions), "expected": list(expected_dimensions)}
    )


def validate_3d_printability(
    is_manifold: bool,
    bounding_box: Tuple[float, float, float],
    volume: float,
    min_feature_size: float = 0.5,
    max_print_volume: Tuple[float, float, float] = (250.0, 250.0, 250.0)
) -> ValidationReport:
    """
    Validate geometry against manufacturing and 3D printing constraints.
    Units assumed in millimeters.
    """
    issues: List[ValidationIssue] = []

    if not is_manifold:
        issues.append(ValidationIssue(
            severity="error",
            check="watertight_manifold",
            message="Geometry is not watertight/manifold. Slicers cannot compute infill."
        ))

    if volume <= 0.0:
        issues.append(ValidationIssue(
            severity="error",
            check="zero_or_negative_volume",
            message=f"Mesh volume is non-positive: {volume:.4f} mm3. Surface normals may be inverted."
        ))

    for i, axis in enumerate(["X", "Y", "Z"]):
        if bounding_box[i] > max_print_volume[i]:
            issues.append(ValidationIssue(
                severity="error",
                check=f"print_bed_exceeded_{axis}",
                message=f"Dimension {axis} ({bounding_box[i]:.2f} mm) exceeds printer build volume ({max_print_volume[i]:.2f} mm)."
            ))
        elif bounding_box[i] < min_feature_size:
            issues.append(ValidationIssue(
                severity="warning",
                check=f"thin_wall_{axis}",
                message=f"Dimension {axis} ({bounding_box[i]:.2f} mm) is below recommended minimum feature size ({min_feature_size:.2f} mm)."
            ))

    passed = not any(iss.severity == "error" for iss in issues)
    return ValidationReport(
        passed=passed,
        score=1.0 if passed else 0.0,
        issues=issues,
        metrics={
            "bounding_box_mm": list(bounding_box),
            "volume_mm3": volume,
            "is_manifold": is_manifold
        }
    )


def validate_image_artifact(image_path: Path, min_size_bytes: int = 1000) -> ValidationReport:
    """Verify render image file validity, magic bytes, and dimensions."""
    issues: List[ValidationIssue] = []

    if not image_path.exists():
        issues.append(ValidationIssue(
            severity="error",
            check="file_exists",
            message=f"Render file not found at {image_path}."
        ))
        return ValidationReport(passed=False, score=0.0, issues=issues)

    size = image_path.stat().st_size
    if size < min_size_bytes:
        issues.append(ValidationIssue(
            severity="error",
            check="file_size",
            message=f"Render file size ({size} bytes) below minimum threshold ({min_size_bytes} bytes)."
        ))

    # Verify PNG header
    with open(image_path, "rb") as f:
        header = f.read(8)
        if image_path.suffix.lower() == ".png" and header != b"\x89PNG\r\n\x1a\n":
            issues.append(ValidationIssue(
                severity="error",
                check="png_magic_bytes",
                message="File extension is .png but PNG magic header is missing or corrupt."
            ))

    passed = not any(iss.severity == "error" for iss in issues)
    return ValidationReport(
        passed=passed,
        score=1.0 if passed else 0.0,
        issues=issues,
        metrics={"file_size_bytes": size, "path": str(image_path)}
    )
