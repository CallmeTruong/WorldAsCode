"""Measured height field of one object and roof planes fitted to it.

Screenshots only constrain an outline. The photogrammetric surface the views
were rendered from also has heights, and a dense sample of them shows ridges,
hips, towers, dormers and chimneys directly. This module samples that surface on
a grid aligned with the footprint's principal axes and reduces it to a small set
of planes with rectangular plan regions. The output is a compact recipe
(plane coefficients + rectangles), compiled to sloped prisms; the sampled mesh
itself is never shipped.
"""

import json
import math
from pathlib import Path

import numpy as np

import worldascode.evidence.georeference as georef
import worldascode.geometry.massing as massing
from worldascode.storage.artifacts import write_json


def grid_axes(evidence):
    """Unit vectors (in plan: x east, n north) of the footprint's principal frame."""
    angle = georef.principal_angle(massing.to_plan(evidence["footprint"]))
    return (
        (math.cos(angle), math.sin(angle)),
        (-math.sin(angle), math.cos(angle)),
        angle,
    )


def grid_layout(evidence, step, margin=4.0):
    u_axis, v_axis, angle = grid_axes(evidence)
    plan = massing.to_plan(evidence["footprint"])
    us = [p[0] * u_axis[0] + p[1] * u_axis[1] for p in plan]
    vs = [p[0] * v_axis[0] + p[1] * v_axis[1] for p in plan]
    u0, v0 = min(us) - margin, min(vs) - margin
    nu = int(math.ceil((max(us) + margin - u0) / step)) + 1
    nv = int(math.ceil((max(vs) + margin - v0) / step)) + 1
    return {"u0": u0, "v0": v0, "step": step, "nu": nu, "nv": nv, "angle_rad": angle}


def grid_plan_points(layout):
    """Plan coordinates [x, north] of every cell centre, shape (nv, nu, 2)."""
    c, s = math.cos(layout["angle_rad"]), math.sin(layout["angle_rad"])
    u = layout["u0"] + layout["step"] * np.arange(layout["nu"])
    v = layout["v0"] + layout["step"] * np.arange(layout["nv"])
    uu, vv = np.meshgrid(u, v)
    return np.stack([uu * c - vv * s, uu * s + vv * c], axis=2)


def capture(evidence, out, url, step=0.6, batch=1500):
    """Sample the streamed surface height under each grid cell through the local viewer."""
    from playwright.sync_api import sync_playwright

    layout = grid_layout(evidence, step)
    points = grid_plan_points(layout).reshape(-1, 2)
    origin = evidence["frame"]["origin"]
    frame = georef.Frame(origin["longitude"], origin["latitude"])
    lonlat = [
        [
            origin["longitude"] + math.degrees(float(x) / frame.east_radius),
            origin["latitude"] + math.degrees(float(n) / frame.north_radius),
        ]
        for x, n in points
    ]
    heights = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 960})
        page.goto(url, wait_until="load")
        for _ in range(200):
            if page.evaluate("()=>window.__GOOGLE_REFERENCE_READY__===true"):
                break
            if page.evaluate("()=>!!window.__GOOGLE_REFERENCE_FAILURE__"):
                raise RuntimeError("HEIGHT_PROVIDER_CONNECTION_FAILED")
            page.wait_for_timeout(300)
        else:
            raise RuntimeError("HEIGHT_PROVIDER_START_TIMEOUT")
        page.set_default_timeout(300000)
        source = page.evaluate("()=>window.googleEvidenceStats().source")
        for start in range(0, len(lonlat), batch):
            result = page.evaluate(
                "p=>window.sampleEvidenceHeights(p)", lonlat[start : start + batch]
            )
            heights.extend(r["height"] for r in result)
        browser.close()
    ground = evidence["frame"]["ground_height_m"]
    record = {
        "schema": "worldscale-heights-1",
        "object_id": evidence["object_id"],
        "source": source,
        "not_surveyed": True,
        "layout": layout,
        "ground_height_m": ground,
        "heights_above_ground": [
            None if h is None else round(h - ground, 3) for h in heights
        ],
    }
    write_json(Path(out), record)
    return record


def polygon_mask(plan, layout):
    """Cells whose centre lies inside a plan polygon."""
    from PIL import Image, ImageDraw

    c, s = math.cos(-layout["angle_rad"]), math.sin(-layout["angle_rad"])
    pixels = [
        (
            (x * c - n * s - layout["u0"]) / layout["step"],
            (x * s + n * c - layout["v0"]) / layout["step"],
        )
        for x, n in plan
    ]
    image = Image.new("L", (layout["nu"], layout["nv"]), 0)
    ImageDraw.Draw(image).polygon(pixels, fill=1)
    return np.asarray(image) > 0


def component(mask, seed):
    """4-connected region of ``mask`` containing ``seed`` (row, column)."""
    region = np.zeros_like(mask)
    region[seed] = mask[seed]
    while True:
        grown = region.copy()
        grown[1:] |= region[:-1]
        grown[:-1] |= region[1:]
        grown[:, 1:] |= region[:, :-1]
        grown[:, :-1] |= region[:, 1:]
        grown &= mask
        if (grown == region).all():
            return region
        region = grown


def plane_through(u, v, h):
    """Least-squares h = a*u + b*v + c."""
    design = np.column_stack([u, v, np.ones(len(u))])
    return np.linalg.lstsq(design, h, rcond=None)[0]


def regularise(plane, u, v, h, flat_deg=4.0, snap_deg=14.0):
    """Snap near-level planes flat and near-axis slopes onto the footprint's axes.

    Roofs are built square to their walls; a few degrees of photogrammetric
    wobble should not become a twisted surface.
    """
    a, b, _ = plane
    slope = math.hypot(a, b)
    if math.degrees(math.atan(slope)) < flat_deg:
        return np.array([0.0, 0.0, float(np.median(h))])
    direction = math.degrees(math.atan2(b, a)) % 90
    if min(direction, 90 - direction) < snap_deg:
        along_u = abs(a) >= abs(b)
        t = u if along_u else v
        if np.ptp(t) < 1e-6:
            return np.array([0.0, 0.0, float(np.median(h))])
        k, c = plane_through(t, np.zeros(len(t)), h)[[0, 2]]
        return np.array([k, 0.0, c]) if along_u else np.array([0.0, k, c])
    return np.asarray(plane, float)


def rectangles(mask):
    """Greedy cover of a cell mask by maximal axis-aligned rectangles (c0, r0, c1, r1)."""
    mask = mask.copy()
    result = []
    while mask.any():
        rows, cols = mask.shape
        heights = np.zeros(cols, int)
        best = (0, 0, 0, 0, 0)
        for r in range(rows):
            heights = np.where(mask[r], heights + 1, 0)
            stack = []
            for c in range(cols + 1):
                current = heights[c] if c < cols else 0
                start = c
                while stack and stack[-1][1] >= current:
                    start, height = stack.pop()
                    area = height * (c - start)
                    if area > best[0]:
                        best = (area, start, r - height + 1, c, r + 1)
                stack.append((start, current))
        _, c0, r0, c1, r1 = best
        mask[r0:r1, c0:c1] = False
        result.append((c0, r0, c1, r1))
    return result


def fit_roof(grid, layout, plan, height_prior, tolerance=0.35, seed=7):
    """Planes with rectangular plan regions that reproduce the measured roof.

    Returns a recipe in the grid's (u, v) frame and a report. Deterministic for a
    given grid; no image or language model is involved.
    """
    step = layout["step"]
    rng = np.random.default_rng(seed)
    inside = polygon_mask(plan, layout)
    cap = 1.45 * height_prior + 4.0  # taller surfaces belong to a neighbour
    valid = np.isfinite(grid) & (grid < cap)
    rim_inner = massing.offset(plan, 1.8)
    rim = polygon_mask(plan, layout) & valid & (grid > 0.4 * height_prior)
    if rim_inner:
        rim &= ~polygon_mask(rim_inner, layout)
    if rim.sum() < 20:
        raise ValueError("HEIGHT_FIELD_DOES_NOT_COVER_FOOTPRINT")
    eave = float(np.percentile(grid[rim], 20))
    building = inside & valid & (grid > eave - 0.5)
    # A much taller mass that reaches the outline is a neighbour leaning into the
    # footprint, not a tower of this building: towers stand inside their own roof.
    tall = building & (grid > np.percentile(grid[building], 95) + 3.0)
    edge = inside.copy()
    edge[1:-1, 1:-1] &= ~(
        inside[:-2, 1:-1] & inside[2:, 1:-1] & inside[1:-1, :-2] & inside[1:-1, 2:]
    )
    removed = 0
    while (tall & edge).any():
        region = component(tall, tuple(np.argwhere(tall & edge)[0]))
        building &= ~region
        tall &= ~region
        removed += int(region.sum())
    vv, uu = np.mgrid[0 : layout["nv"], 0 : layout["nu"]]
    u = layout["u0"] + uu * step
    v = layout["v0"] + vv * step
    labels = np.full(grid.shape, -1, int)
    planes = []
    free = building.copy()
    minimum = max(6, int(2.2 / step**2))
    max_slope = math.tan(math.radians(72))
    while free.sum() > 0.03 * building.sum() and len(planes) < 80:
        candidates = []
        cells = np.argwhere(free)
        for r, c in cells[
            rng.choice(len(cells), size=min(160, len(cells)), replace=False)
        ]:
            window = (slice(max(r - 2, 0), r + 3), slice(max(c - 2, 0), c + 3))
            local = free[window]
            if local.sum() < 10:
                continue
            plane = plane_through(
                u[window][local], v[window][local], grid[window][local]
            )
            if math.hypot(plane[0], plane[1]) > max_slope:
                continue
            fit = free & (
                np.abs(grid - (plane[0] * u + plane[1] * v + plane[2])) < tolerance
            )
            if fit[r, c]:
                candidates.append((int(fit.sum()), (r, c), plane))
        candidates.sort(key=lambda item: -item[0])
        best = None
        for _, cell, plane in candidates[:6]:
            region = component(
                free
                & (np.abs(grid - (plane[0] * u + plane[1] * v + plane[2])) < tolerance),
                tuple(cell),
            )
            if best is None or region.sum() > best[0].sum():
                best = (region, cell)
        if best is None or best[0].sum() < minimum:
            break
        region, cell = best
        plane = regularise(
            plane_through(u[region], v[region], grid[region]),
            u[region],
            v[region],
            grid[region],
        )
        region = component(
            free
            & (
                np.abs(grid - (plane[0] * u + plane[1] * v + plane[2]))
                < 1.4 * tolerance
            ),
            tuple(cell),
        )
        if region.sum() < minimum:
            free[tuple(cell)] = False
            continue
        labels[region] = len(planes)
        planes.append(plane)
        free &= ~region
    # Whatever no plane explains (chimney tops, finials, noise) becomes small level steps.
    rest = building & (labels < 0)
    while rest.any():
        cell = tuple(np.argwhere(rest)[0])
        level = float(grid[cell])
        region = component(rest & (np.abs(grid - level) < 1.0), cell)
        labels[region] = len(planes)
        planes.append(np.array([0.0, 0.0, float(np.median(grid[region]))]))
        rest &= ~region
    surface = np.full(grid.shape, np.nan)
    recipe_planes = []
    for index, plane in enumerate(planes):
        region = labels == index
        if not region.any():
            continue
        surface[region] = plane[0] * u[region] + plane[1] * v[region] + plane[2]
        rows, cols = np.where(region)
        r0, c0 = rows.min(), cols.min()
        crop = region[r0 : rows.max() + 1, c0 : cols.max() + 1]
        level = abs(plane[0]) + abs(plane[1]) < 1e-9
        recipe_planes.append(
            {
                "a": round(float(plane[0]), 5),
                "b": round(float(plane[1]), 5),
                "c": round(float(plane[2]), 3),
                # A small level patch standing above the eave is a stack or finial.
                "material": "trim"
                if level and region.sum() * step**2 < 4.0 and plane[2] > eave + 1.5
                else "roof",
                "rects": [
                    [
                        round(layout["u0"] + (c0 + a - 0.5) * step, 3),
                        round(layout["v0"] + (r0 + b - 0.5) * step, 3),
                        round(layout["u0"] + (c0 + c - 0.5) * step, 3),
                        round(layout["v0"] + (r0 + d - 0.5) * step, 3),
                    ]
                    for a, b, c, d in rectangles(crop)
                ],
            }
        )
    error = np.abs(surface - grid)[building]
    recipe = {
        "schema": "worldscale-roof-planes-1",
        "frame_angle_rad": layout["angle_rad"],
        "base_y": round(eave - 0.4, 3),
        "planes": recipe_planes,
    }
    report = {
        "eave_height_m": round(eave, 3),
        "top_height_m": round(float(np.nanmax(surface)), 3),
        "planes": len(recipe_planes),
        "rectangles": sum(len(p["rects"]) for p in recipe_planes),
        "cells": int(building.sum()),
        "neighbour_cells_removed": removed,
        "cell_m": step,
        "mean_abs_error_m": round(float(error.mean()), 3),
        "p90_abs_error_m": round(float(np.percentile(error, 90)), 3),
        "method": "sequential local plane fits with connected inliers, axis/flat regularisation, greedy rectangle cover",
        "source_note": "Heights are photogrammetric samples, not surveyed; planes smooth their noise and can merge small features.",
    }
    return recipe, report, labels


def load(path):
    record = json.loads(Path(path).read_text(encoding="utf-8"))
    if record.get("schema") != "worldscale-heights-1":
        raise ValueError("UNSUPPORTED_HEIGHT_SCHEMA")
    layout = record["layout"]
    grid = np.array(
        [np.nan if h is None else h for h in record["heights_above_ground"]], float
    ).reshape(layout["nv"], layout["nu"])
    return grid, layout
