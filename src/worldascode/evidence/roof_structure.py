"""Roof structure from a sampled height field: wing sections and roof volumes.

A wing roof is described the way a builder would: a cross-section (heights
across the wing's width) swept along the wing, with each end either a vertical
gable or a hip of measured run. Whatever still stands well above those swept
surfaces is reported as a roof volume (pavilion, tower, penthouse, plant room)
with a measured base, top and cap character.

The result is a handful of numbers per wing. It applies to pitched, mansard,
shed and flat roofs alike, and is omitted when rectangles do not cover the
outline well enough to be trusted.
"""

import math
import warnings

import numpy as np

import worldascode.geometry.surface_height as dsm

PROFILE_SAMPLES = 15
PROFILE_TOLERANCE_M = 0.3
VOLUME_PROUD_M = 1.5
VOLUME_MIN_M2 = 6.0
COVERAGE_MIN_IOU = 0.82


def sampler(grid, layout):
    """Nearest-cell lookup of plan points [x, north]; NaN outside the grid."""
    c, s = math.cos(-layout["angle_rad"]), math.sin(-layout["angle_rad"])

    def sample(points):
        points = np.asarray(points, float)
        u = points[..., 0] * c - points[..., 1] * s
        v = points[..., 0] * s + points[..., 1] * c
        col = np.rint((u - layout["u0"]) / layout["step"]).astype(int)
        row = np.rint((v - layout["v0"]) / layout["step"]).astype(int)
        ok = (col >= 0) & (col < layout["nu"]) & (row >= 0) & (row < layout["nv"])
        out = np.full(points.shape[:-1], np.nan)
        out[ok] = grid[row[ok], col[ok]]
        return out

    return sample


def wing_axes(wing):
    """Unit vectors of a wing in plan [x, north]: along its length and across it."""
    yaw = wing["rotation_y_rad"]
    return (math.cos(yaw), math.sin(yaw)), (math.sin(yaw), -math.cos(yaw))


def in_wing(wing, points, margin=0.0):
    (ux, un), (vx, vn) = wing_axes(wing)
    cx, cn = wing["centre_xz"][0], -wing["centre_xz"][1]
    dx, dn = points[..., 0] - cx, points[..., 1] - cn
    return (np.abs(dx * ux + dn * un) <= wing["length_m"] / 2 + margin) & (
        np.abs(dx * vx + dn * vn) <= wing["width_m"] / 2 + margin
    )


def simplify(points, tolerance):
    """Douglas-Peucker on a polyline of (v, y)."""
    if len(points) <= 2:
        return points
    (x0, y0), (x1, y1) = points[0], points[-1]
    span = math.hypot(x1 - x0, y1 - y0) or 1.0
    distances = [
        abs((x1 - x0) * (y0 - y) - (x0 - x) * (y1 - y0)) / span for x, y in points[1:-1]
    ]
    worst = int(np.argmax(distances))
    if distances[worst] <= tolerance:
        return [points[0], points[-1]]
    middle = worst + 1
    return simplify(points[: middle + 1], tolerance)[:-1] + simplify(
        points[middle:], tolerance
    )


def classify(profile, hips):
    ys = [y for _, y in profile]
    relief = max(ys) - min(ys)
    if relief < 0.6:
        return "flat"
    peak = int(np.argmax(ys))
    if peak in (0, len(ys) - 1):
        return "shed"
    slopes = [
        abs((b[1] - a[1]) / (b[0] - a[0]))
        for a, b in zip(profile, profile[1:])
        if b[0] != a[0]
    ]
    if len(profile) >= 5 and slopes[0] > 2.2 * max(slopes[1], 0.05):
        return "mansard"
    return "hipped" if any(h > 0 for h in hips) else "gabled"


def section_surface(section, points):
    """Height of a swept section at plan points; NaN outside its rectangle."""
    (ux, un), (vx, vn) = wing_axes(section)
    cx, cn = section["centre_xz"][0], -section["centre_xz"][1]
    dx, dn = points[..., 0] - cx, points[..., 1] - cn
    u, v = dx * ux + dn * un, dx * vx + dn * vn
    half = section["length_m"] / 2
    profile = np.asarray(section["profile"], float)
    y = np.interp(v, profile[:, 0], profile[:, 1])
    base = profile[:, 1].min()
    scale = np.ones_like(u)
    if section["hip_start_m"] > 0:
        scale = np.minimum(scale, np.clip((u + half) / section["hip_start_m"], 0, 1))
    if section["hip_end_m"] > 0:
        scale = np.minimum(scale, np.clip((half - u) / section["hip_end_m"], 0, 1))
    y = base + (y - base) * scale
    outside = (np.abs(u) > half) | (np.abs(v) > section["width_m"] / 2)
    return np.where(outside, np.nan, y)


def roof_structure(grid, layout, plan, wings, eave, height_prior):
    """Wing sections and roof volumes, or ``None`` when rectangles misfit the outline."""
    wings = [w for w in wings if w.get("centre_xz") is not None]
    if not wings:
        return None
    step = layout["step"]
    points = dsm.grid_plan_points(layout)
    inside = dsm.polygon_mask(plan, layout)
    covered = np.zeros_like(inside)
    for wing in wings:
        covered |= in_wing(wing, points)
    union = (inside | covered).sum()
    coverage = float((inside & covered).sum() / union) if union else 0.0
    if coverage < COVERAGE_MIN_IOU:
        return {
            "sections": [],
            "volumes": [],
            "coverage_iou": round(coverage, 3),
            "note": "wing rectangles do not cover the outline; use the offset roof",
        }
    cap = 1.45 * height_prior + 4.0
    valid = inside & np.isfinite(grid) & (grid < cap) & (grid > eave - 1.5)
    heights = np.where(valid, grid, np.nan)
    sample = sampler(heights, layout)
    sections = []
    for index, wing in enumerate(wings):
        (ux, un), (vx, vn) = wing_axes(wing)
        cx, cn = wing["centre_xz"][0], -wing["centre_xz"][1]
        length, width = wing["length_m"], wing["width_m"]
        us = np.arange(-length / 2 + step / 2, length / 2, step)
        vs = np.linspace(-width / 2 + step / 2, width / 2 - step / 2, PROFILE_SAMPLES)
        uu, vv = np.meshgrid(us, vs, indexing="ij")
        field = sample(
            np.stack([cx + uu * ux + vv * vx, cn + uu * un + vv * vn], axis=-1)
        )
        centre_line = np.stack([cx + us * ux, cn + us * un], axis=-1)
        shared = np.zeros(len(us), bool)
        for other in wings:
            if other is not wing:
                shared |= in_wing(other, centre_line)
        own = ~shared if (~shared).sum() >= 4 else np.ones(len(us), bool)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN rows are expected
            # A low percentile looks under dormers and stacks to the roof they sit on.
            profile = np.nanpercentile(field[own], 40, axis=0)
            ridge_line = np.nanpercentile(field, 85, axis=1)
        if not np.isfinite(profile).sum() >= 3:
            continue
        good = np.isfinite(profile)
        profile = np.interp(vs, vs[good], profile[good])
        # The profile ends at the wall line, where the roof meets the eave.
        polyline = [(-width / 2, float(profile[0]))]
        polyline += [(float(v), float(y)) for v, y in zip(vs, profile)]
        polyline += [(width / 2, float(profile[-1]))]
        polyline = simplify(polyline, PROFILE_TOLERANCE_M)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            ridge = (
                float(np.nanmedian(ridge_line[own]))
                if np.isfinite(ridge_line[own]).any()
                else eave
            )
        base = min(y for _, y in polyline)
        hips = []
        for end, order in ((-1, range(len(us))), (1, range(len(us) - 1, -1, -1))):
            tip = np.array(
                [
                    [
                        cx + end * (length / 2 + 0.6) * ux,
                        cn + end * (length / 2 + 0.6) * un,
                    ]
                ]
            )
            joined = any(in_wing(o, tip)[0] for o in wings if o is not wing)
            run = 0.0
            if not joined and ridge - base > 1.0:
                threshold = base + 0.8 * (ridge - base)
                reached = next(
                    (
                        i
                        for i in order
                        if np.isfinite(ridge_line[i]) and ridge_line[i] >= threshold
                    ),
                    None,
                )
                if reached is not None:
                    run = float(length / 2 - end * us[reached]) / 0.8
                run = 0.0 if run < 1.2 else min(run, width * 0.8, length * 0.45)
            hips.append(round(run, 1))
        sections.append(
            {
                "id": f"s{index}",
                "centre_xz": [
                    round(wing["centre_xz"][0], 2),
                    round(wing["centre_xz"][1], 2),
                ],
                "rotation_y_rad": round(wing["rotation_y_rad"], 5),
                "length_m": round(length, 2),
                "width_m": round(width, 2),
                "profile": [[round(v, 2), round(y, 2)] for v, y in polyline],
                "ridge_m": round(max(y for _, y in polyline), 2),
                "hip_start_m": hips[0],
                "hip_end_m": hips[1],
                "form": classify(polyline, hips),
            }
        )
    if not sections:
        return {
            "sections": [],
            "volumes": [],
            "coverage_iou": round(coverage, 3),
            "note": "no wing had enough valid height samples",
        }
    surface = np.full(grid.shape, np.nan)
    for section in sections:
        surface = np.fmax(surface, section_surface(section, points))
    proud = valid & np.isfinite(surface) & (grid - surface > VOLUME_PROUD_M)
    rim = inside.copy()
    for _ in range(max(1, round(1.5 / step))):
        shrunk = rim.copy()
        shrunk[1:] &= rim[:-1]
        shrunk[:-1] &= rim[1:]
        shrunk[:, 1:] &= rim[:, :-1]
        shrunk[:, :-1] &= rim[:, 1:]
        rim = shrunk
    near_outline = inside & ~rim
    c, s = math.cos(layout["angle_rad"]), math.sin(layout["angle_rad"])
    volumes = []
    remaining = proud.copy()
    while remaining.any():
        blob = dsm.component(remaining, tuple(np.argwhere(remaining)[0]))
        remaining &= ~blob
        area = float(blob.sum() * step**2)
        if area < VOLUME_MIN_M2:
            continue
        rows, cols = np.where(blob)
        du, dv = (np.ptp(cols) + 1) * step, (np.ptp(rows) + 1) * step
        if area < 0.45 * du * dv:  # a sprawl of noise, not a compact mass
            continue
        u = layout["u0"] + (cols.min() + cols.max()) / 2 * step
        v = layout["v0"] + (rows.min() + rows.max()) / 2 * step
        tops = grid[blob]
        top, typical = float(np.percentile(tops, 97)), float(np.median(tops))
        peaked = top - typical > 0.22 * min(du, dv)
        volumes.append(
            {
                "id": f"v{len(volumes)}",
                "kind": "pavilion"
                if (blob & near_outline).any() and area >= 12
                else "roof_volume",
                "x": round(u * c - v * s, 2),
                "z": round(-(u * s + v * c), 2),
                "rotation_y_rad": round(layout["angle_rad"], 5),
                "width_m": round(float(du), 1),
                "depth_m": round(float(dv), 1),
                "base_m": round(float(np.median(surface[blob])), 1),
                "shoulder_m": round(typical if peaked else top, 1),
                "top_m": round(top, 1),
                # An elongated peaked mass is a cross roof with a ridge along its
                # long side; a compact one comes to a point.
                "cap": "flat"
                if not peaked
                else ("gable" if max(du, dv) >= 1.6 * min(du, dv) else "pyramid"),
                "area_m2": round(area, 1),
            }
        )
    volumes.sort(key=lambda item: -item["area_m2"])
    error = np.abs(surface - grid)[valid & np.isfinite(surface)]
    return {
        "sections": sections,
        "volumes": volumes[:12],
        "coverage_iou": round(coverage, 3),
        "section_fit_mae_m": round(float(error.mean()), 2) if error.size else None,
        "source": "sampled height field; cross-sections are medians along each wing, not surveyed",
    }


def structure_surface(structure, layout):
    """Height grid of sections plus volumes (flat at their shoulder), for tests and audits."""
    points = dsm.grid_plan_points(layout)
    surface = np.full(points.shape[:-1], np.nan)
    for section in structure["sections"]:
        surface = np.fmax(surface, section_surface(section, points))
    return surface


__all__ = [
    "roof_structure",
    "section_surface",
    "structure_surface",
    "sampler",
]
