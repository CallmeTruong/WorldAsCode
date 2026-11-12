"""Camera-independent metric footprint diagnostics; never infer fidelity from a shot."""

import math

import numpy as np
from PIL import Image, ImageDraw


def convex_hull(points):
    points = sorted(set(tuple(p) for p in points))
    if len(points) < 3:
        return points

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for sequence, chain in ((points, lower), (reversed(points), upper)):
        for p in sequence:
            while len(chain) > 1 and cross(chain[-2], chain[-1], p) <= 0:
                chain.pop()
            chain.append(p)
    return lower[:-1] + upper[:-1]


def metric_footprint_report(geometry, evidence, component_names, metres_per_unit):
    """Compare macro wall hull union to OSM in its declared frame, without fitting."""
    if not math.isfinite(metres_per_unit) or metres_per_unit <= 0:
        raise ValueError("INVALID_METRIC_SCALE")
    meshes = [m for m in geometry.get("meshes", []) if m.get("id") in component_names and m.get("vertices")]
    if not meshes:
        return {"passed": False, "reason": "NO_WALL_MESHES_FOR_FOOTPRINT"}
    polygons = [convex_hull([[v[0] * metres_per_unit, v[2] * metres_per_unit] for v in m["vertices"]]) for m in meshes]
    target = evidence["footprint"]
    all_points = np.array([*target, *[p for ring in polygons for p in ring]])
    lo, hi = all_points.min(axis=0) - 2, all_points.max(axis=0) + 2
    extent = float(max(hi - lo))

    def mask(rings):
        im = Image.new("1", (512, 512))
        draw = ImageDraw.Draw(im)
        for ring in rings:
            if len(ring) >= 3:
                draw.polygon([tuple((np.array(p) - lo) / extent * 510) for p in ring], fill=1)
        return np.asarray(im, dtype=bool)

    reference, built = mask([target]), mask(polygons)
    iou = float(np.logical_and(reference, built).sum() / max(1, np.logical_or(reference, built).sum()))
    vertices = [v for m in geometry.get("meshes", []) for v in m.get("vertices", [])]
    observed_height = evidence.get("height_m")
    built_height = max((v[1] for v in vertices), default=0) * metres_per_unit
    height_delta = abs(built_height - observed_height) / observed_height if observed_height else None
    return {
        "passed": iou >= 0.8 and (height_delta is None or height_delta <= 0.2),
        "footprint_iou": round(iou, 4),
        "minimum_iou": 0.8,
        "metres_per_unit": metres_per_unit,
        "built_roof_height_m": round(built_height, 3),
        "source_roof_height_m": observed_height,
        "height_relative_error": round(height_delta, 4) if height_delta is not None else None,
        "maximum_height_relative_error": 0.2,
        "wall_meshes": [m["id"] for m in meshes],
        "source": evidence["footprint_source"],
        "method": "Union of projected convex macro wall hulls vs approximate OSM polygon in declared east/up/south frame; no rotation, translation or camera fitting. Concave wall hulls may overestimate area.",
    }
