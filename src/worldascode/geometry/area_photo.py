"""Measured surfaces for an area: what the place looks like, taken from the captures.

Class recipes can only say what a building of some type usually looks like. The
captured views say what these buildings do look like. This module turns the
views and the height grid into three things the scene can show directly:

* a true orthophoto: every ground and roof point coloured from a view that
  actually sees it (line of sight over the height grid), so tall buildings do
  not smear across the streets behind them;
* masses per building: the footprint up to its lower roof level, plus any
  towers, penthouses or plant rooms the height grid shows standing on it;
* one facade image per wall, sampled from the oblique view that sees it best,
  with hidden parts filled from the visible rows of the same wall.

Everything is deterministic and costs no model call. The textures are derived
from the capture source and inherit its licence; they are a measurement layer,
not authored content.
"""

import math
from pathlib import Path

import numpy as np
from PIL import Image

from worldascode.evidence import georeference as georef
from worldascode.geometry import area_measure
from worldascode.geometry import surface_height as dsm

NEUTRAL = (138, 143, 150)


def load_views(views, folder, ground):
    loaded = []
    for view in views:
        image = np.asarray(Image.open(Path(folder) / view["image"]).convert("RGB"))
        camera = area_measure.view_camera(view, ground)
        loaded.append(
            {
                "id": view["id"],
                "image": image,
                "camera": camera,
                "nadir": view["pitch_deg"] < -80,
                "complete": bool(view.get("tiles_loaded")),
            }
        )
    return loaded


def sample(view, points):
    """Colours of points in a view, NaN where they fall outside the frame."""
    pix, depth = georef.project(view["camera"], points)
    image = view["image"]
    x, y = np.rint(pix[:, 0]), np.rint(pix[:, 1])
    ok = (depth > 0) & np.isfinite(x) & np.isfinite(y)
    ok &= (
        (x >= 0) & (x < image.shape[1]) & (y >= 0) & (y < image.shape[0] - 40)
    )  # skip the credit strip
    colours = np.full((len(points), 3), np.nan)
    colours[ok] = image[y[ok].astype(int), x[ok].astype(int)]
    return colours


def fill_missing(image, valid, rounds=60):
    """Grow valid colours into gaps from their neighbours; anything left becomes neutral."""
    image, valid = image.copy(), valid.copy()
    for _ in range(rounds):
        if valid.all():
            break
        total = np.zeros_like(image)
        count = np.zeros(valid.shape, float)
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            shifted_valid = np.roll(valid, (dr, dc), axis=(0, 1))
            shifted = np.roll(image, (dr, dc), axis=(0, 1))
            if dr == 1:
                shifted_valid[0] = False
            elif dr == -1:
                shifted_valid[-1] = False
            elif dc == 1:
                shifted_valid[:, 0] = False
            else:
                shifted_valid[:, -1] = False
            total += np.where(shifted_valid[..., None], shifted, 0)
            count += shifted_valid
        grow = ~valid & (count > 0)
        image[grow] = total[grow] / count[grow][:, None]
        valid |= grow
    image[~valid] = NEUTRAL
    return image


def orthophoto(above, layout, views, out, resolution=0.5):
    """True orthophoto on the height grid's extent; row 0 is the north edge."""
    step, half = layout["step"], -layout["u0"]
    # Line of sight is decided per height-grid cell, colour per orthophoto pixel.
    n_cells = layout["nu"]
    axis = layout["u0"] + step * np.arange(n_cells)
    east, north = np.meshgrid(axis, axis)
    surface = np.nan_to_num(above, nan=0.0)
    cell_points = np.stack(
        [east.ravel(), surface.ravel() + 0.5, -north.ravel()], axis=1
    )
    order = sorted(views, key=lambda v: (not v["nadir"],))
    sight = [
        area_measure.visible(
            cell_points, v["camera"]["position"], above, layout, 2.5
        ).reshape(n_cells, n_cells)
        for v in order
    ]
    size = int(round(2 * half / resolution))
    xs = -half + (np.arange(size) + 0.5) * resolution
    norths = half - (np.arange(size) + 0.5) * resolution
    px, pn = np.meshgrid(xs, norths)
    col = np.clip(np.rint((px - layout["u0"]) / step).astype(int), 0, n_cells - 1)
    row = np.clip(np.rint((pn - layout["v0"]) / step).astype(int), 0, n_cells - 1)
    points = np.stack([px.ravel(), surface[row, col].ravel(), -pn.ravel()], axis=1)
    image = np.zeros((size * size, 3))
    done = np.zeros(size * size, bool)
    used = {}
    for view, seen in zip(order, sight):
        want = ~done & seen[row, col].ravel()
        if not want.any():
            continue
        colours = sample(view, points[want])
        got = np.isfinite(colours[:, 0])
        index = np.flatnonzero(want)[got]
        image[index] = colours[got]
        done[index] = True
        used[view["id"]] = int(got.sum())
    image = fill_missing(image.reshape(size, size, 3), done.reshape(size, size))
    Image.fromarray(image.astype(np.uint8)).save(out)
    return {
        "image": Path(out).name,
        "half_m": half,
        "resolution_m": resolution,
        "size": size,
        "pixels_by_view": used,
        "filled_fraction": round(float(1 - done.mean()), 4),
    }


def ortho_colour(ortho_image, half, x, z):
    size = ortho_image.shape[0]
    col = int(np.clip((x + half) / (2 * half) * size, 0, size - 1))
    row = int(np.clip((half + z) / (2 * half) * size, 0, size - 1))
    return [int(v) for v in ortho_image[row, col]]


def oriented_rectangle(blob, layout, angle):
    """Rectangle around a cell blob in axes rotated by ``angle``: corners as [x, z]."""
    rows, cols = np.where(blob)
    x = layout["u0"] + cols * layout["step"]
    n = layout["v0"] + rows * layout["step"]
    c, s = math.cos(-angle), math.sin(-angle)
    u, v = x * c - n * s, x * s + n * c
    pad = layout["step"] / 2
    u0, u1, v0, v1 = u.min() - pad, u.max() + pad, v.min() - pad, v.max() + pad
    c, s = math.cos(angle), math.sin(angle)
    corners = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
    return [
        [round(float(a * c - b * s), 2), round(float(-(a * s + b * c)), 2)]
        for a, b in corners
    ], float((u1 - u0) * (v1 - v0))


def proud_masses(region, above, base, angle, layout, min_area, depth=0):
    """Rectangular masses standing at least a storey above ``base`` inside ``region``."""
    step = layout["step"]
    masses = []
    remaining = region & (above > base + 3.5)
    while remaining.any():
        blob = dsm.component(remaining, tuple(np.argwhere(remaining)[0]))
        remaining &= ~blob
        area = float(blob.sum() * step**2)
        if area < min_area:
            continue
        polygon, box_area = oriented_rectangle(blob, layout, angle)
        if (
            area < 0.5 * box_area
        ):  # not a compact block: keep it as part of the roof below
            continue
        top = float(np.percentile(above[blob], 60))
        masses.append(
            {
                "polygon": polygon,
                "y0": round(base, 1),
                "y1": round(top, 1),
                "role": "volume",
                "area_m2": round(area, 1),
            }
        )
        if depth < 1:
            masses += proud_masses(
                blob, above, top, angle, layout, max(16.0, min_area / 3), depth + 1
            )
    return masses


def building_masses(building, above, layout):
    """The footprint up to its lower roof level, then whatever stands above it."""
    low, high = building.get("min_height", 0.0), building["height_m"]
    main = {
        "polygon": building["polygon"],
        "holes": building.get("holes", []),
        "y0": round(low, 1),
        "y1": round(high, 1),
        "role": "main",
    }
    measured = building.get("measured")
    if building.get("use") == "roof":
        main["y0"] = round(max(0.0, high - 0.6), 1)
        return [main]
    if not measured or low > 1 or above is None:
        return [main]
    mask = area_measure.polygon_cells(
        building["polygon"], layout, building.get("holes", [])
    )
    mask &= np.isfinite(above)
    core = mask.copy()
    core[1:-1, 1:-1] &= (
        mask[:-2, 1:-1] & mask[2:, 1:-1] & mask[1:-1, :-2] & mask[1:-1, 2:]
    )
    if core.sum() < 12:
        return [main]
    values = above[core]
    # A podium under a tower: a substantial lower level and a substantial higher one.
    p20, p50 = float(np.percentile(values, 20)), float(np.percentile(values, 50))
    base = (
        p20
        if (p50 - p20 > 8 and (values < p20 + 4).mean() >= 0.15 and p20 > 3)
        else p50
    )
    main["y1"] = round(base, 1)
    plan = [[x, -z] for x, z in building["polygon"]]
    plan = plan if georef.area(plan) > 0 else plan[::-1]
    angle = georef.principal_angle(plan)
    return [main] + proud_masses(core, above, base, angle, layout, 30.0)


def facade_tile(
    a, b, y0, y1, outward, views, above, layout, pixels_per_m, return_mask=False
):
    """One wall as an image (row 0 at the top), with the share of it actually observed."""
    length, height = math.dist(a, b), y1 - y0
    w = int(np.clip(round(length * pixels_per_m), 2, 420))
    h = int(np.clip(round(height * pixels_per_m), 2, 420))
    t = (np.arange(w) + 0.5) / w
    f = 1 - (np.arange(h) + 0.5) / h
    tt, ff = np.meshgrid(t, f)
    normal = np.array([outward[0], 0.0, outward[1]])
    points = (
        np.stack(
            [
                a[0] + (b[0] - a[0]) * tt.ravel(),
                y0 + height * ff.ravel(),
                a[1] + (b[1] - a[1]) * tt.ravel(),
            ],
            axis=1,
        )
        + normal * 0.6
    )
    # Visibility on a coarse lattice of the wall, then applied to every pixel.
    cw, ch = max(1, int(length // 3)), max(1, int(height // 3))
    ct, cf = np.meshgrid((np.arange(cw) + 0.5) / cw, 1 - (np.arange(ch) + 0.5) / ch)
    coarse = (
        np.stack(
            [
                a[0] + (b[0] - a[0]) * ct.ravel(),
                y0 + height * cf.ravel(),
                a[1] + (b[1] - a[1]) * ct.ravel(),
            ],
            axis=1,
        )
        + normal * 0.6
    )
    cj = np.clip((tt.ravel() * cw).astype(int), 0, cw - 1)
    ci = np.clip(((1 - ff.ravel()) * ch).astype(int), 0, ch - 1)
    centre = points.mean(axis=0)
    ranked = []
    for view in views:
        if view["nadir"]:
            continue
        to_camera = np.asarray(view["camera"]["position"]) - centre
        facing = float(to_camera @ normal / np.linalg.norm(to_camera))
        if facing > 0.12:
            ranked.append((facing, view))
    image = np.zeros((h * w, 3))
    done = np.zeros(h * w, bool)
    for _, view in sorted(ranked, key=lambda item: -item[0]):
        seen = area_measure.visible(
            coarse, view["camera"]["position"], above, layout, 2.5
        )
        want = ~done & seen.reshape(ch, cw)[ci, cj]
        if not want.any():
            continue
        colours = sample(view, points[want])
        got = np.isfinite(colours[:, 0])
        index = np.flatnonzero(want)[got]
        image[index] = colours[got]
        done[index] = True
    image, done = image.reshape(h, w, 3), done.reshape(h, w)
    observed = float(done.mean())
    if observed >= 0.04:
        # A storey looks like the storeys beside it: continue each row from what was seen of it,
        # and rows never seen from the nearest row that was.
        row_ok = done.mean(axis=1) >= 0.12
        for i in np.flatnonzero(row_ok):
            image[i, ~done[i]] = np.median(image[i, done[i]], axis=0)
        if row_ok.any():
            seen_rows = np.flatnonzero(row_ok)
            for i in np.flatnonzero(~row_ok):
                image[i] = image[seen_rows[np.argmin(np.abs(seen_rows - i))]]
        else:
            image[~done] = np.median(image[done], axis=0)
        result = (image.astype(np.uint8), observed)
    else:
        result = (None, observed)
    return (*result, done) if return_mask else result


def facades(
    buildings_masses, views, above, layout, out, pixels_per_m=1.3, atlas_width=2048
):
    """Wall images for every mass, packed into one atlas. Returns per-wall rectangles."""
    tiles, records = [], []
    for building_id, masses in buildings_masses:
        seen_colours = []
        for mass_index, mass in enumerate(masses):
            polygon = mass["polygon"]
            ccw = georef.area([[x, -z] for x, z in polygon]) > 0
            walls = []
            for a, b in zip(polygon, polygon[1:] + polygon[:1]):
                length = math.dist(a, b)
                if length < 0.5 or mass["y1"] - mass["y0"] < 0.5:
                    walls.append(None)
                    continue
                dx, dz = (b[0] - a[0]) / length, (b[1] - a[1]) / length
                outward = (-dz, dx) if ccw else (dz, -dx)
                image, observed = facade_tile(
                    a,
                    b,
                    mass["y0"],
                    mass["y1"],
                    outward,
                    views,
                    above,
                    layout,
                    pixels_per_m,
                )
                if image is not None:
                    seen_colours.append(np.median(image.reshape(-1, 3), axis=0))
                walls.append(
                    {
                        "image": image,
                        "observed": round(observed, 3),
                        "size": (
                            max(2, int(round(length * pixels_per_m))),
                            max(
                                2, int(round((mass["y1"] - mass["y0"]) * pixels_per_m))
                            ),
                        ),
                    }
                )
            records.append((building_id, mass_index, walls))
        # Walls nobody saw take the building's own observed tone rather than a guess.
        tone = (
            np.median(seen_colours, axis=0)
            if seen_colours
            else np.array(NEUTRAL, float)
        )
        for record in records:
            if record[0] != building_id:
                continue
            for wall in record[2]:
                if wall and wall["image"] is None:
                    wall["image"] = np.tile(tone.astype(np.uint8), (4, 4, 1))
                    wall["unobserved"] = True
    for building_id, mass_index, walls in records:
        for edge, wall in enumerate(walls):
            if wall:
                tiles.append((building_id, mass_index, edge, wall))
    tiles.sort(key=lambda item: -item[3]["image"].shape[0])
    x = y = shelf = 0
    placed = []
    for item in tiles:
        h, w = item[3]["image"].shape[:2]
        if x + w + 2 > atlas_width:
            x, y, shelf = 0, y + shelf + 2, 0
        placed.append((item, x, y))
        x, shelf = x + w + 2, max(shelf, h)
    height = y + shelf + 2
    atlas = np.zeros((height, atlas_width, 3), np.uint8)
    rectangles = {}
    for (building_id, mass_index, edge, wall), px, py in placed:
        h, w = wall["image"].shape[:2]
        atlas[py : py + h, px : px + w] = wall["image"]
        rectangles[(building_id, mass_index, edge)] = {
            "rect": [px, py, w, h],
            "observed": wall["observed"],
            "unobserved": bool(wall.get("unobserved")),
        }
    Image.fromarray(atlas).save(out)
    return rectangles, {
        "image": Path(out).name,
        "width": atlas_width,
        "height": height,
        "walls": len(placed),
    }


def build(area, above, layout, views, folder, ground, run):
    """Write the orthophoto and facade atlas; return the scene's measured-surface section."""
    run = Path(run)
    loaded = load_views(views, folder, ground)
    ortho = orthophoto(above, layout, loaded, run / "ortho.png")
    ortho_image = np.asarray(Image.open(run / "ortho.png"))
    # A building centred outside the measured extent with no height samples has neither
    # height nor image evidence here; it is left out rather than shown as an untextured block.
    reach = ortho["half_m"] - 2.0
    inside = [
        b
        for b in area["buildings"]
        if b.get("measured")
        or (abs(b["centroid"][0]) <= reach and abs(b["centroid"][1]) <= reach)
    ]
    per_building = [(b["id"], building_masses(b, above, layout)) for b in inside]
    rectangles, atlas = facades(
        per_building, loaded, above, layout, run / "facades.png"
    )
    masses, observed = [], []
    for building_id, building_masses_ in per_building:
        for index, mass in enumerate(building_masses_):
            walls = []
            for edge in range(len(mass["polygon"])):
                entry = rectangles.get((building_id, index, edge))
                walls.append(entry["rect"] if entry else None)
                if entry:
                    observed.append(0.0 if entry["unobserved"] else entry["observed"])
            masses.append({**mass, "building": building_id, "walls": walls})
    for tree in area.get("detected_trees", []):
        tree["colour"] = ortho_colour(
            ortho_image, ortho["half_m"], tree["x"], tree["z"]
        )
    return {
        "ortho": ortho,
        "atlas": atlas,
        "masses": masses,
        "buildings_outside_measured_extent": [
            b["id"] for b in area["buildings"] if b not in inside
        ],
        "wall_observation": {
            "walls": len(observed),
            "mean_observed_fraction": round(float(np.mean(observed)), 3)
            if observed
            else None,
            "walls_never_seen": int(sum(v == 0 for v in observed)),
        },
        "views": [{"id": v["id"], "complete": v["complete"]} for v in loaded],
        "note": "Textures are reprojected capture imagery: colours include the capture's lighting and its blur. Unseen wall areas are continued from seen rows of the same wall.",
    }


def two_tone(pixels):
    """Split wall pixels into a dark and a light population (glazing against cladding)."""
    pixels = np.asarray(pixels, float)
    luma = pixels @ np.array([0.299, 0.587, 0.114])
    low, high = np.percentile(luma, 25), np.percentile(luma, 75)
    for _ in range(8):
        dark = np.abs(luma - low) <= np.abs(luma - high)
        if dark.all() or not dark.any():
            break
        low, high = luma[dark].mean(), luma[~dark].mean()
    if high - low < 14 or dark.all() or not dark.any():
        tone = [int(v) for v in np.median(pixels, axis=0)]
        return {
            "wall_rgb": tone,
            "glass_rgb": None,
            "glass_fraction": None,
            "contrast": round(float(high - low), 1),
        }
    return {
        "wall_rgb": [int(v) for v in np.median(pixels[~dark], axis=0)],
        "glass_rgb": [int(v) for v in np.median(pixels[dark], axis=0)],
        "glass_fraction": round(float(dark.mean()), 3),
        "contrast": round(float(high - low), 1),
    }


def observe(area, above, layout, views, folder, ground, work):
    """Describe what was seen as parameters: masses, two-tone facade colours and rhythm,
    roof colour per building, and the colours of the ground surfaces.

    Nothing here is a texture. The result is a handful of numbers per building
    that any style can reinterpret, so the scene stays procedural.
    """
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    loaded = load_views(views, folder, ground)
    ortho = orthophoto(above, layout, loaded, work / "ortho.png", resolution=1.0)
    ortho_image = np.asarray(Image.open(work / "ortho.png"))
    half = ortho["half_m"]
    seen_buildings = 0
    for building in area["buildings"]:
        masses = building_masses(building, above, layout)
        building["masses"] = masses
        pixels, rows_var, cols_var, fractions = [], [], [], []
        for mass in masses:
            polygon = mass["polygon"]
            ccw = georef.area([[x, -z] for x, z in polygon]) > 0
            for a, b in zip(polygon, polygon[1:] + polygon[:1]):
                length = math.dist(a, b)
                if length < 6 or mass["y1"] - mass["y0"] < 6:
                    continue
                dx, dz = (b[0] - a[0]) / length, (b[1] - a[1]) / length
                outward = (-dz, dx) if ccw else (dz, -dx)
                tile, observed, valid = facade_tile(
                    a,
                    b,
                    mass["y0"],
                    mass["y1"],
                    outward,
                    loaded,
                    above,
                    layout,
                    1.0,
                    return_mask=True,
                )
                if tile is None or observed < 0.3:
                    continue
                fractions.append(observed)
                # Filled pixels are useful for the reference preview, never evidence.
                pixels.append(tile[valid])
                luma = tile.astype(float) @ np.array([0.299, 0.587, 0.114])
                row_count, col_count = valid.sum(axis=1), valid.sum(axis=0)
                row_means = (luma * valid).sum(axis=1) / np.maximum(row_count, 1)
                col_means = (luma * valid).sum(axis=0) / np.maximum(col_count, 1)
                rows_var.append(
                    float(row_means[row_count >= max(2, 0.3 * valid.shape[1])].var())
                    if (row_count >= max(2, 0.3 * valid.shape[1])).sum() >= 3
                    else 0
                )
                cols_var.append(
                    float(col_means[col_count >= max(2, 0.3 * valid.shape[0])].var())
                    if (col_count >= max(2, 0.3 * valid.shape[0])).sum() >= 3
                    else 0
                )
        observed = {
            "walls_used": len(pixels),
            "basis": "visible pixels only; dark/light split and rhythm are approximate cues, not semantic glass segmentation",
            "source_views_complete": all(v["complete"] for v in loaded),
        }
        if pixels:
            seen_buildings += 1
            observed.update(two_tone(np.concatenate(pixels)))
            rows, cols = float(np.mean(rows_var)), float(np.mean(cols_var))
            # Floor bands vary down the wall, fins and piers vary along it.
            observed["rhythm"] = (
                "bands"
                if rows > 1.8 * cols
                else "fins"
                if cols > 1.8 * rows
                else "grid"
            )
            observed["mean_observed_fraction"] = round(float(np.mean(fractions)), 3)
        mask = area_measure.polygon_cells(
            building["polygon"], layout, building.get("holes", [])
        )
        rows, cols = np.where(mask)
        if len(rows) >= 4:
            scale = ortho_image.shape[0] / layout["nu"]
            r = np.clip(
                ((layout["nv"] - 1 - rows) * scale).astype(int),
                0,
                ortho_image.shape[0] - 1,
            )
            c = np.clip((cols * scale).astype(int), 0, ortho_image.shape[1] - 1)
            observed["roof_rgb"] = [
                int(v) for v in np.median(ortho_image[r, c], axis=0)
            ]
        building["observed"] = observed

    def along(features, limit=4000):
        samples = []
        for feature in features:
            for x, z in feature["points"]:
                if abs(x) < half - 2 and abs(z) < half - 2:
                    samples.append(ortho_colour(ortho_image, half, x, z))
        return (
            [int(v) for v in np.median(samples[:limit], axis=0)]
            if len(samples) >= 8
            else None
        )

    def within(kind):
        samples = []
        for surface in area["surfaces"]:
            if surface["kind"] != kind:
                continue
            mask = area_measure.polygon_cells(surface["polygon"], layout)
            rows, cols = np.where(mask)
            scale = ortho_image.shape[0] / layout["nu"]
            r = np.clip(
                ((layout["nv"] - 1 - rows) * scale).astype(int),
                0,
                ortho_image.shape[0] - 1,
            )
            c = np.clip((cols * scale).astype(int), 0, ortho_image.shape[1] - 1)
            samples.extend(ortho_image[r, c].tolist())
        return (
            [int(v) for v in np.median(samples, axis=0)] if len(samples) >= 8 else None
        )

    trees = area.get("detected_trees", [])
    for tree in trees:
        tree["colour"] = ortho_colour(ortho_image, half, tree["x"], tree["z"])
    area["observed_ground"] = {
        "road": along([r for r in area["roads"] if r["layer"] <= 0]),
        "sidewalk": along(area["paths"]),
        "rail_bed": along(area["rails"]),
        "green": within("green"),
        "water": within("water"),
        "plaza": within("plaza"),
        "leaf": [int(v) for v in np.median([t["colour"] for t in trees], axis=0)]
        if len(trees) >= 5
        else None,
    }
    return {
        "buildings_with_facade_observation": seen_buildings,
        "buildings": len(area["buildings"]),
        "masses": sum(len(b["masses"]) for b in area["buildings"]),
        "ground": {k: v is not None for k, v in area["observed_ground"].items()},
        "views": [{"id": v["id"], "complete": v["complete"]} for v in loaded],
        "note": "Observed colours carry the capture's lighting; a style decides how they are rendered.",
    }
