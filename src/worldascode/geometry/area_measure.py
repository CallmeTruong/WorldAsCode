"""Join the area model with measurements: ground, building heights, roofs, colours, trees.

Every number records where it came from. Map tags and the height grid are
cross-checked rather than one silently overriding the other, so a disagreement
is visible in the report instead of in the picture.
"""

import colorsys
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image

from worldascode.evidence import georeference as georef
from worldascode.evidence.roof_structure import roof_structure
from worldascode.geometry import surface_height as dsm

STOREY_M = 3.6
AGREEMENT = 0.25  # tag and measurement within this fraction count as agreeing


def load_heights(path, origin=None):
    record = json.loads(Path(path).read_text(encoding="utf-8"))
    if record.get("schema") != "worldascode-area-heights-1":
        raise ValueError("UNSUPPORTED_AREA_HEIGHT_SCHEMA")
    if origin and any(
        abs(record.get("origin", {}).get(k, float("inf")) - v) > 1e-7
        for k, v in origin.items()
    ):
        raise ValueError("AREA_HEIGHT_ORIGIN_MISMATCH")
    layout = record["layout"]
    if (
        not all(
            isinstance(layout.get(k), (float, int)) and math.isfinite(layout[k])
            for k in ("u0", "v0", "step", "angle_rad")
        )
        or layout["step"] <= 0
        or abs(layout["angle_rad"]) > 1e-9
        or any(
            type(layout.get(k)) is not int or not 2 <= layout[k] <= 1501
            for k in ("nu", "nv")
        )
        or len(record["heights"]) != layout["nu"] * layout["nv"]
    ):
        raise ValueError("AREA_HEIGHT_LAYOUT_INVALID")
    grid = np.array([np.nan if h is None else h for h in record["heights"]], float)
    if np.isinf(grid).any():
        raise ValueError("AREA_HEIGHT_NONFINITE_VALUE")
    return grid.reshape(layout["nv"], layout["nu"]), layout


def cells(points, layout):
    """Grid (row, col) of area points [x east, z south]."""
    points = np.asarray(points, float)
    col = np.rint((points[..., 0] - layout["u0"]) / layout["step"]).astype(int)
    row = np.rint((-points[..., 1] - layout["v0"]) / layout["step"]).astype(int)
    ok = (col >= 0) & (col < layout["nu"]) & (row >= 0) & (row < layout["nv"])
    return row, col, ok


def polygon_cells(polygon, layout, holes=()):
    """Test the actual metric sample centres; raster rounding mixes neighboring roofs."""
    result = np.zeros((layout["nv"], layout["nu"]), bool)
    x0 = max(0, math.ceil((min(p[0] for p in polygon) - layout["u0"]) / layout["step"]))
    x1 = min(
        layout["nu"] - 1,
        math.floor((max(p[0] for p in polygon) - layout["u0"]) / layout["step"]),
    )
    y0 = max(
        0, math.ceil((-max(p[1] for p in polygon) - layout["v0"]) / layout["step"])
    )
    y1 = min(
        layout["nv"] - 1,
        math.floor((-min(p[1] for p in polygon) - layout["v0"]) / layout["step"]),
    )
    if x0 > x1 or y0 > y1:
        return result
    x, z = np.meshgrid(
        layout["u0"] + np.arange(x0, x1 + 1) * layout["step"],
        -(layout["v0"] + np.arange(y0, y1 + 1) * layout["step"]),
    )

    def contains(ring):
        mask = np.zeros(x.shape, bool)
        for a, b in zip(ring, ring[1:] + ring[:1]):
            if b[1] != a[1]:
                mask ^= ((a[1] > z) != (b[1] > z)) & (
                    x < (b[0] - a[0]) * (z - a[1]) / (b[1] - a[1]) + a[0]
                )
        return mask

    mask = contains(polygon)
    for hole in holes:
        mask &= ~contains(hole)
    result[y0 : y1 + 1, x0 : x1 + 1] = mask
    return result


def ground_datum(area, grid, layout):
    """Ground level from the height grid under surface roads; a low percentile otherwise."""
    if not np.isfinite(grid).any():
        raise ValueError("AREA_HEIGHT_NO_VALID_CELLS")
    samples = []
    for road in area["roads"]:
        if road["layer"] == 0:
            row, col, ok = cells(road["points"], layout)
            samples.extend(grid[row[ok], col[ok]].tolist())
    samples = [s for s in samples if np.isfinite(s)]
    if len(samples) >= 20:
        return float(
            np.percentile(samples, 30)
        ), "30th percentile of the height grid under surface roads"
    return float(np.nanpercentile(grid, 5)), "5th percentile of the whole height grid"


def oriented_volumes(blob_mask, grid, base, plan_angle, layout, limit=6):
    """Compact masses standing above ``base``: oriented rectangles in the building's own axes."""
    step = layout["step"]
    c, s = math.cos(-plan_angle), math.sin(-plan_angle)
    volumes, remaining = [], blob_mask.copy()
    while remaining.any() and len(volumes) < limit * 3:
        blob = dsm.component(remaining, tuple(np.argwhere(remaining)[0]))
        remaining &= ~blob
        area = float(blob.sum() * step**2)
        if area < 12:
            continue
        rows, cols = np.where(blob)
        x = layout["u0"] + cols * step
        n = layout["v0"] + rows * step
        u, v = x * c - n * s, x * s + n * c
        du, dv = float(np.ptp(u)) + step, float(np.ptp(v)) + step
        if area < 0.4 * du * dv:
            continue
        cu, cv = (u.min() + u.max()) / 2, (v.min() + v.max()) / 2
        volumes.append(
            {
                "x": round(float(cu * c + cv * s), 2),
                "z": round(float(-(-cu * s + cv * c)), 2),
                "rotation_y_rad": round(plan_angle, 4),
                "width_m": round(du, 1),
                "depth_m": round(dv, 1),
                "base_m": round(float(base), 1),
                "top_m": round(float(np.percentile(grid[blob], 90)), 1),
                "area_m2": round(area, 1),
            }
        )
    return sorted(volumes, key=lambda item: -item["area_m2"])[:limit]


def measure_buildings(area, grid, layout, ground):
    """Heights and roof structure per building from the grid (heights above ground)."""
    above = grid - ground
    for building in area["buildings"]:
        footprint_cells = polygon_cells(
            building["polygon"], layout, building.get("holes", [])
        )
        mask = polygon_cells(
            building["polygon"], layout, building.get("holes", [])
        ) & np.isfinite(above)
        coverage = float(mask.sum() / max(1, footprint_cells.sum()))
        building["measurement_quality"] = {
            "coverage": round(coverage, 3),
            "valid_cells": int(mask.sum()),
        }
        # Stay off the outline: its rim mixes roof, facade and street samples.
        core = mask.copy()
        core[1:-1, 1:-1] &= (
            mask[:-2, 1:-1] & mask[2:, 1:-1] & mask[1:-1, :-2] & mask[1:-1, 2:]
        )
        values = above[core if core.sum() >= 12 else mask]
        if values.size < 6 or coverage < 0.6:
            building["measured"] = None
            continue
        p20, p50, p90, p98 = (float(np.percentile(values, q)) for q in (20, 50, 90, 98))
        building["measured"] = {
            "cells": int(values.size),
            "p20_m": round(p20, 1),
            "median_m": round(p50, 1),
            "p90_m": round(p90, 1),
            "p98_m": round(p98, 1),
        }
    resolve_heights(area)
    for building in area["buildings"]:
        measured = building.get("measured")
        building["roof"] = {
            "form": {"gabled": "gable", "hipped": "hip", "mansard": "mansard"}.get(
                building.get("roof_shape_tag") or "", "flat"
            ),
            "volumes": [],
        }
        if not measured or building["height_source"].startswith(
            "map tag (height grid disagrees"
        ):
            continue
        plan = [[x, -z] for x, z in building["polygon"]]
        plan = plan if georef.area(plan) > 0 else plan[::-1]
        angle = georef.principal_angle(plan)
        mask = polygon_cells(
            building["polygon"], layout, building.get("holes", [])
        ) & np.isfinite(above)
        relief = measured["p90_m"] - measured["p20_m"]
        structure = None
        if relief > 2.0 and building["height_m"] < 45 and len(plan) <= 12:
            wings = [
                {
                    "centre_xz": [w["centre"][0], -w["centre"][1]],
                    "length_m": max(w["length"], w["width"]),
                    "width_m": min(w["length"], w["width"]),
                    "rotation_y_rad": w["axis_angle_rad"]
                    + (0 if w["length"] >= w["width"] else math.pi / 2),
                }
                for w in georef.wings(plan)
            ]
            try:
                structure = roof_structure(
                    above, layout, plan, wings, measured["p20_m"], building["height_m"]
                )
            except (ValueError, IndexError):
                structure = None
        pitched = [
            s for s in (structure or {}).get("sections", []) if s["form"] != "flat"
        ]
        if (
            pitched
            and structure["section_fit_mae_m"] is not None
            and structure["section_fit_mae_m"] < 1.5
        ):
            eave = min(min(y for _, y in s["profile"]) for s in structure["sections"])
            building["roof"] = {
                "form": "sections",
                "sections": structure["sections"],
                "volumes": structure["volumes"],
                "fit_mae_m": structure["section_fit_mae_m"],
            }
            building["height_m"], building["top_m"] = (
                round(eave, 1),
                round(measured["p98_m"], 1),
            )
            building["height_source"] = "height grid: eave of fitted roof sections"
        else:
            base = measured["median_m"]
            proud = mask & (above > base + 2.5) & (above < base + 40)
            building["roof"]["volumes"] = oriented_volumes(
                proud, above, base, angle, layout
            )
            if building["roof"]["volumes"]:
                building["top_m"] = round(
                    max(v["top_m"] for v in building["roof"]["volumes"]), 1
                )
    return area


def resolve_heights(area):
    """One height per building with its source; tags and measurement are cross-checked."""
    for building in area["buildings"]:
        tag = building.get("height_tag")
        levels = building.get("levels_tag")
        measured = (building.get("measured") or {}).get("median_m")
        if measured is not None and measured < 2.5:
            measured = None  # demolished, under construction or not in the capture
        if tag and measured:
            if abs(measured - tag) / tag <= AGREEMENT:
                height, source = measured, "height grid (agrees with map tag)"
            else:
                height, source = (
                    tag,
                    f"map tag (height grid disagrees: {measured:.0f} m)",
                )
        elif measured:
            height, source = measured, "height grid"
        elif tag:
            height, source = tag, "map tag height"
        elif levels:
            height, source = (
                levels * (4.0 if levels >= 10 else STOREY_M),
                "map tag building:levels",
            )
        else:
            height, source = 12.0, "assumed (no tag, no measurement)"
        if building["use"] == "roof" and not (tag or measured):
            height, source = 5.0, "assumed canopy height"
        height = max(float(height), building.get("min_height", 0) + 0.5, 0.5)
        building["height_m"] = round(float(height), 1)
        building["top_m"] = building["height_m"]
        building["height_source"] = source
        storey = 4.2 if height >= 60 else 3.9 if height >= 25 else 3.4
        building["storeys"] = (
            int(levels)
            if levels and abs(levels * storey - height) < 0.35 * height
            else max(1, round(height / storey))
        )
    return area


def view_camera(view, ground):
    camera = view["camera"]
    horizontal = 2 * math.degrees(
        math.atan(
            math.tan(math.radians(camera["fov_vertical_deg"]) / 2)
            * camera["width"]
            / camera["height"]
        )
    )
    projected = {
        "position": [
            camera["east_m"],
            camera["height_ellipsoid_m"] - ground,
            camera["south_m"],
        ],
        "target": [0.0, camera["target_height_ellipsoid_m"] - ground, 0.0],
        "fov_deg": horizontal
        if camera["width"] >= camera["height"]
        else camera["fov_vertical_deg"],
        "width": camera["width"],
        "height": camera["height"],
        "heading_deg": view["heading_deg"],
    }
    if view.get("pose"):
        pose = pose_for_render(view, ground)
        projected.update(
            {"position": pose["position"], "target": pose["target"], "up": pose["up"]}
        )
        if view.get("actual_camera") and view.get("origin"):
            origin = view["origin"]
            projected.update(
                {
                    "local_to_ecef": georef.Frame(
                        origin["longitude"], origin["latitude"], ground
                    ).local_to_ecef(),
                    "view_matrix": view["actual_camera"]["view_matrix"],
                    "projection_matrix": view["actual_camera"]["projection_matrix"],
                }
            )
    return projected


def pose_for_render(view, ground):
    if view.get("pose"):
        pose = {**view["pose"]}
        for key in ("position", "target"):
            pose[key] = list(pose[key])
            pose[key][1] -= ground
        return pose
    c = view["camera"]
    return {
        "position": [c["east_m"], c["height_ellipsoid_m"] - ground, c["south_m"]],
        "target": [0, c["target_height_ellipsoid_m"] - ground, 0],
        "up": [0, 1, 0],
        "fov_vertical_deg": c["fov_vertical_deg"],
        "render_width": c["width"],
        "render_height": c["height"],
    }


def pixels_at(image, camera, points):
    pix, depth = georef.project(camera, points)
    ok = (depth > 0) & np.isfinite(pix).all(axis=1)
    x, y = np.rint(pix[:, 0]).astype(int), np.rint(pix[:, 1]).astype(int)
    ok &= (x >= 0) & (x < image.shape[1]) & (y >= 0) & (y < image.shape[0])
    return image[y[ok], x[ok]], ok


def visible(points, camera_position, above, layout, clearance=2.0):
    """Line of sight from points to a camera over the height grid."""
    points = np.asarray(points, float)
    direction = np.asarray(camera_position, float) - points
    length = np.linalg.norm(direction, axis=1)
    direction /= length[:, None]
    result = np.ones(len(points), bool)
    for distance in np.arange(4.0, 420.0, layout["step"]):
        probe = points + direction * distance
        active = result & (distance < length)
        if not active.any():
            break
        row, col, ok = cells(probe[:, [0, 2]], layout)
        check = active & ok
        surface = np.full(len(points), -np.inf)
        surface[check] = above[row[check], col[check]]
        result &= ~(np.nan_to_num(surface, nan=-np.inf) > probe[:, 1] + clearance)
    return result


def sample_colours(area, views, folder, above, layout, ground):
    """Roof colour from the top view, wall colour from oblique views where the wall is actually seen."""
    images = {
        v["id"]: np.asarray(Image.open(Path(folder) / v["image"]).convert("RGB"))
        for v in views
    }
    cameras = {v["id"]: view_camera(v, ground) for v in views}
    top = next((v["id"] for v in views if v["pitch_deg"] < -80), None)
    for building in area["buildings"]:
        colours = {}
        if top:
            mask = polygon_cells(building["polygon"], layout, building.get("holes", []))
            rows, cols = np.where(mask)
            if len(rows) >= 8:
                pick = np.linspace(0, len(rows) - 1, min(250, len(rows))).astype(int)
                points = np.stack(
                    [
                        layout["u0"] + cols[pick] * layout["step"],
                        np.full(len(pick), building["height_m"]),
                        -(layout["v0"] + rows[pick] * layout["step"]),
                    ],
                    axis=1,
                )
                rgb, _ = pixels_at(images[top], cameras[top], points)
                if len(rgb) >= 8:
                    colours["roof_rgb"] = [int(v) for v in np.median(rgb, axis=0)]
        polygon = building["polygon"]
        signed = georef.area([[x, -z] for x, z in polygon])
        samples = []
        for a, b in zip(polygon, polygon[1:] + polygon[:1]):
            length = math.dist(a, b)
            if length < 4:
                continue
            dx, dz = (b[0] - a[0]) / length, (b[1] - a[1]) / length
            normal = np.array([dz, 0.0, -dx]) * (1 if signed < 0 else -1)
            for t in np.linspace(0.15, 0.85, max(2, int(length // 6))):
                for f in (0.45, 0.65, 0.85):
                    point = np.array(
                        [
                            a[0] + (b[0] - a[0]) * t,
                            building["min_height"]
                            + (building["height_m"] - building["min_height"]) * f,
                            a[1] + (b[1] - a[1]) * t,
                        ]
                    )
                    samples.append((point + normal * 0.6, normal))
        wall = []
        if samples:
            points = np.array([s[0] for s in samples])
            normals = np.array([s[1] for s in samples])
            for view in views:
                if view["pitch_deg"] < -80:
                    continue
                camera = cameras[view["id"]]
                facing = ((np.array(camera["position"]) - points) * normals).sum(
                    axis=1
                ) > 0
                seen = facing & visible(points, camera["position"], above, layout)
                if seen.any():
                    rgb, ok = pixels_at(images[view["id"]], camera, points[seen])
                    wall.extend(rgb.tolist())
        if len(wall) >= 10:
            wall = np.array(wall, float)
            luma = wall @ np.array([0.299, 0.587, 0.114])
            lit = wall[luma >= np.percentile(luma, 50)]
            colours["wall_rgb"] = [int(v) for v in np.median(lit, axis=0)]
            colours["wall_samples"] = int(len(wall))
        building["colours_measured"] = colours
    return area


def detect_trees(area, above, layout, views, folder, ground, limit=400):
    """Tree crowns: vegetation-coloured local height maxima outside buildings and carriageways."""
    top = next((v for v in views if v["pitch_deg"] < -80), None)
    if top is None:
        return []
    image = np.asarray(Image.open(Path(folder) / top["image"]).convert("RGB"))
    camera = view_camera(top, ground)
    blocked = np.zeros(above.shape, bool)
    for building in area["buildings"]:
        blocked |= polygon_cells(building["polygon"], layout, building.get("holes", []))
    grown = blocked.copy()
    grown[1:] |= blocked[:-1]
    grown[:-1] |= blocked[1:]
    grown[:, 1:] |= blocked[:, :-1]
    grown[:, :-1] |= blocked[:, 1:]
    candidate = ~grown & np.isfinite(above) & (above > 3.5) & (above < 28)
    reach = max(1, round(3.5 / layout["step"]))
    padded = np.pad(np.where(candidate, above, -np.inf), reach, constant_values=-np.inf)
    peak = candidate.copy()
    for dr in range(-reach, reach + 1):
        for dc in range(-reach, reach + 1):
            if dr or dc:
                peak &= (
                    above
                    >= padded[
                        reach + dr : reach + dr + above.shape[0],
                        reach + dc : reach + dc + above.shape[1],
                    ]
                )
    rows, cols = np.where(peak)
    if not len(rows):
        return []
    points = np.stack(
        [
            layout["u0"] + cols * layout["step"],
            above[rows, cols],
            -(layout["v0"] + rows * layout["step"]),
        ],
        axis=1,
    )
    rgb, ok = pixels_at(image, camera, points)
    trees = []
    for (x, y, z), colour in zip(points[ok], rgb):
        h, s, v = colorsys.rgb_to_hsv(*(colour / 255.0))
        # Leaves from spring green to autumn orange; roofs, glass and asphalt are grey or blue.
        if (
            0.04 <= h <= 0.45
            and s >= 0.22
            and v >= 0.2
            and math.hypot(x, z) <= area["radius_m"]
        ):
            trees.append(
                {
                    "x": round(float(x), 1),
                    "z": round(float(z), 1),
                    "height_m": round(float(y), 1),
                    "source": "height grid crown with vegetation colour in the top view",
                }
            )
    trees.sort(key=lambda t: -t["height_m"])
    return trees[:limit]
