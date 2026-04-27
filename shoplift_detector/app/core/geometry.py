"""Geometry primitives for shelf-ROI interaction detection.

Kept intentionally dependency-free (no numpy/cv2) so it can be imported
anywhere without dragging heavy vision deps — the hot path in ai_service
already owns those imports.
"""

from __future__ import annotations

Point = tuple[float, float]
Polygon = list[Point] | list[list[float]]


def point_in_polygon(point: Point, polygon: Polygon) -> bool:
    """Ray-casting point-in-polygon test.

    Returns True if the point lies strictly inside the polygon. Edges are
    ambiguous and may test either way — acceptable for ROI detection where
    sub-pixel precision on the boundary does not matter.

    A polygon with fewer than 3 vertices is always outside.
    """
    x, y = point[0], point[1]
    n = len(polygon)
    if n < 3:
        return False

    inside = False
    px, py = polygon[-1][0], polygon[-1][1]
    for vertex in polygon:
        cx, cy = vertex[0], vertex[1]
        if (cy > y) != (py > y):
            # Guard against zero-length vertical spans; 1e-9 matches the
            # precision we get from normalized-to-pixel conversion and
            # avoids ZeroDivisionError on collinear horizontal edges.
            denom = (py - cy) if (py - cy) != 0 else 1e-9
            x_intersect = (px - cx) * (y - cy) / denom + cx
            if x < x_intersect:
                inside = not inside
        px, py = cx, cy
    return inside


def denormalize_polygon(
    polygon: Polygon,
    frame_width: int,
    frame_height: int,
) -> list[Point]:
    """Convert a normalized 0..1 polygon to frame-pixel coordinates.

    Shelf zones are stored normalized so they survive resolution changes;
    the detector works in pixel space, so every frame we rescale.
    """
    return [
        (p[0] * frame_width, p[1] * frame_height)
        for p in polygon
    ]
