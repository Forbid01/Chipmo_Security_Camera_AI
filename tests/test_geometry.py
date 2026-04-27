"""Unit tests for shoplift_detector.app.core.geometry.

Kept algorithmic and dependency-free so they run anywhere — the geometry
module is on the inner loop of the AI service, so correctness here is
load-bearing for every theft detection.
"""

import pytest

from shoplift_detector.app.core.geometry import (
    denormalize_polygon,
    point_in_polygon,
)


class TestPointInPolygon:
    def test_point_inside_square(self):
        square = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
        assert point_in_polygon((5.0, 5.0), square)

    def test_point_outside_square(self):
        square = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
        assert not point_in_polygon((15.0, 5.0), square)
        assert not point_in_polygon((-1.0, 5.0), square)
        assert not point_in_polygon((5.0, 20.0), square)

    def test_point_inside_concave_polygon(self):
        # L-shape: excludes the top-right corner region.
        l_shape = [
            (0.0, 0.0), (10.0, 0.0), (10.0, 5.0),
            (5.0, 5.0), (5.0, 10.0), (0.0, 10.0),
        ]
        assert point_in_polygon((2.0, 2.0), l_shape)
        assert point_in_polygon((2.0, 8.0), l_shape)
        # Point in the L's "notch" — outside the shape.
        assert not point_in_polygon((8.0, 8.0), l_shape)

    def test_degenerate_polygon_rejects_all(self):
        assert not point_in_polygon((5.0, 5.0), [])
        assert not point_in_polygon((5.0, 5.0), [(0.0, 0.0)])
        assert not point_in_polygon((5.0, 5.0), [(0.0, 0.0), (10.0, 10.0)])

    def test_accepts_list_vertices(self):
        # Real usage passes list[list[float]] from JSON, not tuples.
        square = [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]]
        assert point_in_polygon((5.0, 5.0), square)

    def test_collinear_horizontal_edge_no_div_zero(self):
        # Triangle with a horizontal edge at y=0 — used to blow up with a
        # naive ray-cast when denom (py - cy) was exactly zero.
        triangle = [(0.0, 0.0), (10.0, 0.0), (5.0, 5.0)]
        # Point well inside should be detected regardless of the collinear
        # edge handling.
        assert point_in_polygon((5.0, 2.0), triangle)


class TestDenormalizePolygon:
    def test_scales_normalized_to_pixels(self):
        poly = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
        px = denormalize_polygon(poly, frame_width=1920, frame_height=1080)
        assert px == [(0.0, 0.0), (1920.0, 0.0), (1920.0, 1080.0), (0.0, 1080.0)]

    def test_midpoints_scale_proportionally(self):
        poly = [[0.5, 0.25]]
        px = denormalize_polygon(poly, frame_width=400, frame_height=200)
        assert px == [(200.0, 50.0)]


class TestShelfInteractionIntegration:
    """End-to-end: wrist keypoint in normalized shelf zone → detected."""

    def test_wrist_inside_shelf_zone_after_denormalization(self):
        # Beer fridge zone: left third of a 1920x1080 frame.
        zone_norm = [[0.0, 0.3], [0.33, 0.3], [0.33, 0.9], [0.0, 0.9]]
        zone_px = denormalize_polygon(zone_norm, 1920, 1080)

        wrist_in_zone = (200.0, 500.0)  # left side, mid-height → inside
        wrist_outside = (1500.0, 500.0)  # right side → outside

        assert point_in_polygon(wrist_in_zone, zone_px)
        assert not point_in_polygon(wrist_outside, zone_px)

    @pytest.mark.parametrize(
        ("resolution", "wrist"),
        [
            ((1920, 1080), (400.0, 600.0)),
            ((1280, 720), (266.0, 400.0)),   # same relative position
            ((640, 480), (133.0, 266.0)),
        ],
    )
    def test_normalized_zone_works_across_resolutions(self, resolution, wrist):
        # A single normalized zone should catch the same "relative point"
        # regardless of camera resolution — this is the whole point of
        # storing zones in 0..1 coords.
        zone_norm = [[0.1, 0.4], [0.5, 0.4], [0.5, 0.8], [0.1, 0.8]]
        w, h = resolution
        zone_px = denormalize_polygon(zone_norm, w, h)
        assert point_in_polygon(wrist, zone_px)
