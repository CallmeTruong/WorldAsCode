"""Area reconstruction: map data plus measurements, compiled deterministically.

    centre + radius
        -> map data (OpenStreetMap; cached)
        -> area model (buildings, roads, rails, surfaces, points; one frame)
        -> measurements, when a reference viewer is available
               height grid -> ground datum, building heights, roof structure, trees
               reference views -> roof and wall colour cues, pictures to compare against
        -> appearance (material class per building, one palette for the area)
        -> scene -> render through the reference cameras
        -> report: height agreement per building, coverage, side-by-side sheets

No model call is needed to produce the area. Agents add value on top of it
(style palettes, class recipes, landmark detail), not underneath it.
"""

import hashlib
import json
import math
import re
import shutil
import subprocess
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from worldascode.adapters.rendering.browser import capture, record_runtime_snapshot
from worldascode.config import ROOT, paths
from worldascode.evidence import georeference as georef
from worldascode.geometry import area_measure, area_model, area_style
from worldascode.storage.artifacts import digest, file_hash, write_json

INDEX_HTML = (
    '<!doctype html><meta charset="utf-8"><title>WorldAsCode area</title><style>body{margin:0;'
    "background:#161c24;color:#eee;font:15px system-ui}header{padding:10px}canvas{display:block}"
    '</style><header>Area preview · Hour <input id="hour" type="range" min="0" max="23.9" '
    'value="13" step=".1"> Wetness <input id="wetness" type="range" min="0" max="1" step=".05" '
    'value="0"> Wind <input id="wind" type="range" min="0" max="2" step=".1" value="0"> Explode '
    '<input id="explode" type="range" min="0" max="1" step=".05" value="0"> <span id="selection">'
    'Click a part</span></header><div id="viewport"></div><script type="module" '
    'src="./bundle.js"></script>'
)


def seed_of(text):
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:4], "big")


def interior_points(polygon, count, margin=3.0):
    """Up to ``count`` well-separated points safely inside a polygon."""
    xs, zs = [p[0] for p in polygon], [p[1] for p in polygon]
    step = max(2.0, min(max(xs) - min(xs), max(zs) - min(zs)) / 6)
    candidates = []
    x = min(xs) + step / 2
    while x < max(xs):
        z = min(zs) + step / 2
        while z < max(zs):
            if all(
                area_model.inside(polygon, (x + dx, z + dz))
                for dx in (-margin, margin)
                for dz in (-margin, margin)
            ):
                candidates.append((x, z))
            z += step
        x += step
    if not candidates:
        return []
    cx, cz = np.mean(candidates, axis=0)
    candidates.sort(key=lambda p: math.hypot(p[0] - cx, p[1] - cz))
    chosen = [candidates[0]]
    for p in candidates[1:]:
        if len(chosen) >= count:
            break
        if all(math.hypot(p[0] - q[0], p[1] - q[1]) >= 2.5 * margin for q in chosen):
            chosen.append(p)
    return chosen


def building_site(building):
    """The kit ``site`` for one building, in its own frame around its centroid."""
    ax, az = building["centroid"]
    local = [[round(x - ax, 2), round(z - az, 2)] for x, z in building["polygon"]]
    holes = [
        [[round(x - ax, 2), round(z - az, 2)] for x, z in hole]
        for hole in building.get("holes", [])
    ]
    appearance = building["appearance"]
    roof = dict(building["roof"])
    if holes and roof["form"] != "flat":
        roof = {
            "form": "flat",
            "volumes": [],
            "uncertainty": "Courtyard pitched roof requires a dedicated recipe; flat roof is a simplified prior.",
        }
    plan = [[x, -z] for x, z in local]
    plan = plan if georef.area(plan) > 0 else plan[::-1]
    yaw = georef.principal_angle(plan)
    if roof["form"] == "sections":
        roof["sections"] = [
            {
                **s,
                "centre_xz": [
                    round(s["centre_xz"][0] - ax, 2),
                    round(s["centre_xz"][1] - az, 2),
                ],
            }
            for s in roof["sections"]
        ]
    roof["volumes"] = [
        {**v, "x": round(v["x"] - ax, 2), "z": round(v["z"] - az, 2)}
        for v in roof.get("volumes", [])
    ]
    eave = building["height_m"]
    if roof["form"] in ("gable", "hip", "mansard"):
        rise = building.get("roof_height_tag") or min(5.0, 0.3 * eave)
        roof["rise_m"] = round(rise, 1)
        if building["height_source"].startswith("map tag"):
            eave = max(2.5, eave - rise)  # a tagged height includes the roof
    if (
        roof["form"] == "flat"
        and not roof["volumes"]
        and building["area_m2"] >= 250
        and eave >= 12
    ):
        units = 1 + seed_of(building["id"]) % 3
        roof["mechanical"] = [
            {
                "x": round(x, 1),
                "z": round(z, 1),
                "yaw": round(yaw, 3),
                "width_m": 4.0 + (i % 2) * 2,
                "depth_m": 3.0,
                "height_m": 2.2,
            }
            for i, (x, z) in enumerate(interior_points(local, units, margin=4.0))
        ]
        roof["mechanical_source"] = "seeded estimate, not an observed rooftop layout"
    kind = "mass" if appearance["class"] in ("canopy", "raised") else "building"
    return {
        "kind": kind,
        "object_id": building["id"],
        "name": building.get("name"),
        "footprint": local,
        "holes": holes,
        "edges": area_model.edges_of(local),
        "axis_yaw": round(yaw, 4),
        "storeys": building["storeys"],
        "eave_m": round(eave, 1),
        "ridge_m": building["top_m"],
        "top_m": building["top_m"],
        "min_height_m": building.get("min_height", 0.0),
        "roof": roof,
        "features": {"dormers": [], "chimneys": []},
        "appearance": appearance,
        "colours": {
            "wall": appearance.get("wall"),
            "roof": appearance["roof"],
            "trim": appearance["trim"],
        },
        "seed": seed_of(building["id"]),
        "tags": building.get("tags", {}),
        "height_source": building["height_source"],
        "observed": building.get("observed", {}),
    }


def build_scene(area):
    def network(features):
        return [
            {
                **feature,
                "source_id": feature["id"],
                "id": feature["id"] + f":segment-{i}",
                "points": points,
            }
            for feature in features
            for i, points in enumerate(
                area_model.clip_polyline(feature["points"], area["radius_m"])
            )
        ]

    surfaces = []
    for surface in area["surfaces"]:
        polygon = area_model.clip_polygon(surface["polygon"], area["radius_m"])
        if polygon:
            holes = [
                h
                for hole in surface.get("holes", [])
                if (h := area_model.clip_polygon(hole, area["radius_m"]))
            ]
            surfaces.append({**surface, "polygon": polygon, "holes": holes})
    trees = []
    for point in area["points"]:
        if point["kind"] == "tree":
            seed = seed_of(point["id"])
            trees.append(
                {
                    "x": point["x"],
                    "z": point["z"],
                    "height_m": 7 + seed % 5,
                    "seed": seed % 997,
                    "source": "OSM position; seeded height prior",
                }
            )
    for tree in area.get("detected_trees", []):
        if all(math.hypot(tree["x"] - t["x"], tree["z"] - t["z"]) > 3.5 for t in trees):
            trees.append({**tree, "seed": seed_of(f"{tree['x']},{tree['z']}") % 997})
    buildings = []
    for b in area["buildings"]:
        masses = b.get("masses") or []
        towers = (
            [m for m in masses if m["role"] == "volume"]
            if b.get("recipe_family") == "observed"
            else []
        )
        main = b
        if towers and b["roof"]["form"] != "sections":
            # The footprint rises to its lower roof; each mass above it is built as its own
            # block on the same foundations, with the same facade treatment.
            base = masses[0]["y1"]
            storey = b["height_m"] / max(1, b["storeys"])
            main = {
                **b,
                "height_m": base,
                "top_m": base,
                "storeys": max(1, round(base / storey)),
                "roof": {"form": "flat", "volumes": []},
            }
        site = building_site(main)
        site["recipe_family"] = b.get("recipe_family")
        buildings.append({"id": b["id"], "anchor": main["centroid"], "site": site})
        if main is b:
            continue
        for index, tower in enumerate(towers):
            polygon = tower["polygon"]
            centre = [
                round(sum(p[0] for p in polygon) / len(polygon), 2),
                round(sum(p[1] for p in polygon) / len(polygon), 2),
            ]
            part = {
                **b,
                "id": f"{b['id']}#mass{index}",
                "polygon": polygon,
                "holes": [],
                "centroid": centre,
                "area_m2": tower["area_m2"],
                "height_m": tower["y1"] - tower["y0"],
                "top_m": tower["y1"] - tower["y0"],
                "storeys": max(1, round((tower["y1"] - tower["y0"]) / storey)),
                "min_height": 0.0,
                "roof": {"form": "flat", "volumes": []},
            }
            site = building_site(part)
            site["recipe_family"] = "observed"
            site["part_of"] = b["id"]
            buildings.append(
                {
                    "id": part["id"],
                    "source_id": b["id"],
                    "anchor": centre,
                    "elevation_m": tower["y0"],
                    "site": site,
                }
            )
    return {
        "palette": area["palette"],
        "style": area.get("style"),
        "radius_m": area["radius_m"],
        "surfaces": surfaces,
        "roads": network(area["roads"]),
        "paths": network(area["paths"]),
        "rails": network(area["rails"]),
        "points": [p for p in area["points"] if p["kind"] != "tree"],
        "trees": trees,
        "buildings": buildings,
    }


def bundle_scene(run, scene, recipe_modules=None, variants=None):
    run = Path(run)
    write_json(run / "scene.json", scene)
    viewer = (ROOT / "runtime/viewer.mjs").as_posix()
    authored_imports = []
    authored_bindings = []
    for i, (family, path) in enumerate(sorted((recipe_modules or {}).items())):
        authored_imports.append(
            f"import {{design as recipe{i}}} from {json.dumps(Path(path).resolve().as_posix())};"
        )
        authored_bindings.append(json.dumps(family) + f":recipe{i}")
    variant_code = ""
    if variants:
        write_json(run / "variants.json", variants)
        variant_code = (
            "import variants from './variants.json';\n"
            "const menu=document.createElement('select');menu.id='style';menu.ariaLabel='Style';\n"
            "for(const [key,value] of Object.entries(variants)){const option=document.createElement('option');option.value=key;option.textContent=value.style.name;menu.append(option);}\n"
            "menu.value=Object.keys(variants)[0];document.querySelector('header').prepend(menu);\n"
            "window.worldscale.styles=Object.keys(variants);\n"
            "window.worldscale.setStyle=key=>{if(!Object.hasOwn(variants,key))throw Error('AREA_STYLE_UNKNOWN_VARIANT');"
            "const next=buildArea(variants[key],{buildDesign,recipes});"
            "if(next.userData.buildFailures.length)throw Error('AREA_STYLE_BUILD_FAILED');"
            "window.worldscale.replaceRoot(next);menu.value=key;return {name:variants[key].style.name,buildings:next.userData.buildingIds.length};};\n"
            "menu.onchange=()=>window.worldscale.setStyle(menu.value);\n"
        )
    entry = (
        f"import {{monitorAssets,mount}} from {json.dumps(viewer)};\nmonitorAssets();\n"
        f"import {{buildDesign}} from {json.dumps((ROOT / 'runtime/kit.mjs').as_posix())};\n"
        f"import {{recipes as defaults}} from {json.dumps((ROOT / 'recipes/buildings.mjs').as_posix())};\n"
        + "\n".join(authored_imports)
        + "\n"
        + f"const recipes={{...defaults,{','.join(authored_bindings)}}};\n"
        + f"import {{buildArea}} from {json.dumps((ROOT / 'runtime/area.mjs').as_posix())};\n"
        f"import scene from './scene.json';\n"
        "const root=buildArea(scene,{buildDesign,recipes});\n"
        "mount(root,{width:1100,height:825,near:Math.max(1,scene.radius_m/50),far:Math.max(1000,scene.radius_m*20),projection:scene.style?.projection});\n"
        + variant_code
    )
    (run / "entry.mjs").write_text(entry, encoding="utf-8")
    script = (
        "require(process.argv[3]+'/esbuild').buildSync({entryPoints:[process.argv[1]],"
        "outfile:process.argv[2],nodePaths:[process.argv[3]],bundle:true,format:'esm',"
        "platform:'browser',sourcemap:true,logLevel:'warning'});"
    )
    result = subprocess.run(
        [
            "node",
            "-e",
            script,
            str(run / "entry.mjs"),
            str(run / "bundle.js"),
            str(paths().node_modules),
        ],
        cwd=run,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError("AREA_BUNDLE_FAILED: " + result.stderr[-2000:])
    (run / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    record_runtime_snapshot(run)


def pair_sheet(pairs, out, cell=(700, 525)):
    """Reference above, reconstruction below, one column per view."""
    sheet = Image.new("RGB", (cell[0] * len(pairs), cell[1] * 2), "#101418")
    draw = ImageDraw.Draw(sheet)
    for column, (label, reference, render) in enumerate(pairs):
        for row, path in enumerate((reference, render)):
            if path and Path(path).is_file():
                image = Image.open(path).convert("RGB")
                image.thumbnail(cell)
                sheet.paste(
                    image,
                    (
                        column * cell[0] + (cell[0] - image.width) // 2,
                        row * cell[1] + (cell[1] - image.height) // 2,
                    ),
                )
        draw.text((column * cell[0] + 8, 6), label + " — reference", fill="#ffffff")
        draw.text(
            (column * cell[0] + 8, cell[1] + 6),
            label + " — reconstruction",
            fill="#ffffff",
        )
    sheet.save(out, quality=90)


def height_agreement(area, model, above, layout):
    """Model top-down height against the height grid: overall and per building."""
    radius = area["radius_m"]
    east, north = np.meshgrid(
        layout["u0"] + layout["step"] * np.arange(layout["nu"]),
        layout["v0"] + layout["step"] * np.arange(layout["nv"]),
    )
    within = (np.hypot(east, north) <= radius) & np.isfinite(above)
    built = np.where(np.isfinite(model), model, 0.0)
    error = built - above
    rows = []
    covered = np.zeros(above.shape, bool)
    for building in area["buildings"]:
        mask = (
            area_measure.polygon_cells(
                building["polygon"], layout, building.get("holes", [])
            )
            & within
        )
        covered |= mask
        if mask.sum() < 6 or building.get("min_height", 0) > 1:
            continue
        values = error[mask]
        rows.append(
            {
                "id": building["id"],
                "name": building.get("name"),
                "class": building["appearance"]["class"],
                "height_m": building["height_m"],
                "height_source": building["height_source"],
                "measured_median_m": (building.get("measured") or {}).get("median_m"),
                "mean_abs_error_m": round(float(np.abs(values).mean()), 2),
                "bias_m": round(float(values.mean()), 2),
                "relative_error": round(
                    float(np.abs(values).mean() / max(building["height_m"], 1)), 3
                ),
            }
        )
    rows.sort(key=lambda r: -r["mean_abs_error_m"])
    open_ground = within & ~covered
    summary = {
        "cells": int(within.sum()),
        "mean_abs_error_m": round(float(np.abs(error[within]).mean()), 2)
        if within.any()
        else None,
        "building_cells_mean_abs_error_m": round(
            float(np.abs(error[within & covered]).mean()), 2
        )
        if (within & covered).any()
        else None,
        "open_ground_mean_abs_error_m": round(
            float(np.abs(error[open_ground]).mean()), 2
        )
        if open_ground.any()
        else None,
        "buildings_within_10_percent": sum(r["relative_error"] <= 0.10 for r in rows),
        "buildings_within_25_percent": sum(r["relative_error"] <= 0.25 for r in rows),
        "buildings_compared": len(rows),
        "note": "Reconstruction height minus the sampled height grid (above the ground datum). Open ground includes trees, vehicles and structures that are not mapped.",
    }
    return summary, rows


def error_image(area, model, above, layout, out):
    built = np.where(np.isfinite(model), model, 0.0)
    error = np.clip((built - np.nan_to_num(above, nan=0.0)) / 20.0, -1, 1)
    error[~np.isfinite(above)] = 0
    image = np.full((*error.shape, 3), 235, np.uint8)
    low, high = error < -0.1, error > 0.1
    image[low] = np.stack(
        [235 * np.ones(low.sum()), 235 * (1 + error[low]), 235 * (1 + error[low])],
        axis=-1,
    )
    image[high] = np.stack(
        [235 * (1 - error[high]), 235 * (1 - error[high]), 235 * np.ones(high.sum())],
        axis=-1,
    )
    scale = max(1, 900 // error.shape[0])
    Image.fromarray(image[::-1]).resize(
        (error.shape[1] * scale, error.shape[0] * scale), Image.NEAREST
    ).save(out)


def _run_area(
    latitude,
    longitude,
    radius,
    run,
    measurements=None,
    palette=None,
    osm=None,
    surface="recipes",
    style="faithful",
):
    """Build one area. ``measurements`` is a folder with heights.json and reference views."""
    run = Path(run).resolve()
    if (run / "result.json").exists():
        raise ValueError("USE_NEW_AREA_RUN")
    run.mkdir(parents=True, exist_ok=True)
    started, stages = time.monotonic(), []

    def stage(name, **facts):
        stages.append(
            {"stage": name, "seconds": round(time.monotonic() - started, 1), **facts}
        )
        write_json(run / "progress.json", stages)

    key = digest([latitude, longitude, radius])[:20]
    osm_path = (
        Path(osm)
        if osm
        else area_model.fetch_osm(
            latitude, longitude, radius + 30, paths().cache_dir / "area" / f"{key}.osm"
        )
    )
    pinned_map = run / "inputs" / "map.osm"
    pinned_map.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(osm_path, pinned_map)
    area = area_model.parse(pinned_map, latitude, longitude, radius)
    stage(
        "map",
        buildings=len(area["buildings"]),
        roads=len(area["roads"]),
        paths=len(area["paths"]),
        rails=len(area["rails"]),
        surfaces=len(area["surfaces"]),
        points=len(area["points"]),
        skipped=area["skipped"],
        map_sha256=file_hash(osm_path),
    )

    above = layout = None
    views, ground = [], None
    measurements = Path(measurements) if measurements else None
    if measurements:
        if not (measurements / "heights.json").is_file():
            raise ValueError("AREA_MEASUREMENTS_HEIGHTS_MISSING")
        grid, layout = area_measure.load_heights(
            measurements / "heights.json", area["origin"]
        )
        pinned_heights = run / "inputs" / "measurements" / "heights.json"
        pinned_heights.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(measurements / "heights.json", pinned_heights)
        ground, ground_source = area_measure.ground_datum(area, grid, layout)
        above = grid - ground
        area["ground"] = {
            "ellipsoid_height_m": round(ground, 2),
            "source": ground_source,
        }
        area_measure.measure_buildings(area, grid, layout, ground)
        if (measurements / "reference-views.json").is_file():
            source_views = json.loads(
                (measurements / "reference-views.json").read_text(encoding="utf-8")
            )
            if source_views.get("origin") != area["origin"]:
                raise ValueError("AREA_REFERENCE_ORIGIN_MISMATCH")
            seen = set()
            for view in source_views["views"]:
                if (
                    not re.fullmatch(r"[a-zA-Z0-9-]{1,80}", view.get("id", ""))
                    or view["id"] in seen
                ):
                    raise ValueError("AREA_REFERENCE_ID_INVALID_OR_DUPLICATE")
                seen.add(view["id"])
                image = (measurements / view["image"]).resolve()
                if (
                    not image.is_relative_to(measurements.resolve())
                    or file_hash(image) != view["sha256"]
                ):
                    raise ValueError("AREA_REFERENCE_HASH_OR_PATH_INVALID")
            views = source_views["views"]
            pinned = run / "inputs" / "measurements"
            pinned.mkdir(parents=True, exist_ok=True)
            shutil.copy2(measurements / "heights.json", pinned / "heights.json")
            shutil.copy2(
                measurements / "reference-views.json", pinned / "reference-views.json"
            )
            for view in source_views["views"]:
                target = pinned / view["image"]
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(measurements / view["image"], target)
            measurements = pinned
            colour_views = [v for v in views if v.get("tiles_loaded")]
            area_measure.sample_colours(
                area, colour_views, measurements, above, layout, ground
            )
            area["detected_trees"] = area_measure.detect_trees(
                area, above, layout, colour_views, measurements, ground
            )
        stage(
            "measure",
            ground_m=round(ground, 2),
            grid_coverage=round(float(np.isfinite(above).mean()), 3),
            views=[v["id"] for v in views],
            detected_trees=len(area.get("detected_trees", [])),
        )
    else:
        area_measure.resolve_heights(area)
        for building in area["buildings"]:
            building["roof"] = {
                "form": {"gabled": "gable", "hipped": "hip", "mansard": "mansard"}.get(
                    building.get("roof_shape_tag") or "", "flat"
                ),
                "volumes": [],
            }
        stage(
            "measure",
            skipped="no measurements supplied; map tags and explicit height priors",
        )

    area_style.apply(area, palette)
    photo = None
    if surface == "measured":
        if not views or above is None:
            raise ValueError("MEASURED_SURFACE_NEEDS_HEIGHT_GRID_AND_VIEWS")
        from worldascode.geometry import area_photo

        photo = area_photo.build(area, above, layout, views, measurements, ground, run)
        stage(
            "surfaces",
            ortho_filled_fraction=photo["ortho"]["filled_fraction"],
            ortho_pixels_by_view=photo["ortho"]["pixels_by_view"],
            masses=len(photo["masses"]),
            **photo["wall_observation"],
        )
    observation = None
    if surface == "observed":
        if not views or above is None:
            raise ValueError("OBSERVED_SURFACE_NEEDS_HEIGHT_GRID_AND_VIEWS")
        from worldascode.geometry import area_look, area_photo

        observation = area_photo.observe(
            area, above, layout, views, measurements, ground, run / "observation"
        )
        area_look.apply(area, style)
        stage(
            "observe",
            style=area["style"]["name"],
            **{
                k: observation[k]
                for k in (
                    "buildings_with_facade_observation",
                    "buildings",
                    "masses",
                    "ground",
                )
            },
        )
    write_json(run / "area.json", area)
    scene = build_scene(area)
    if photo:
        scene["photo"] = photo
    bundle_scene(run, scene)
    stage(
        "compile",
        classes={
            c: sum(b["appearance"]["class"] == c for b in area["buildings"])
            for c in sorted({b["appearance"]["class"] for b in area["buildings"]})
        },
        trees=len(scene["trees"]),
    )

    inspection = {}

    def extra(page, shots):
        inspection.update(
            page.evaluate(
                "({failures:worldscale.root.userData.buildFailures,warnings:worldscale.root.userData.buildWarnings,built:worldscale.root.userData.buildingIds})"
            )
        )
        hour = (area.get("style") or {}).get("hour", 13)
        if hour != 13:
            page.evaluate("h=>worldscale.state({hour:h,wetness:0,wind:0})", hour)
        for view in views:
            page.evaluate(
                "c=>worldscale.pose(c)",
                {
                    **area_measure.pose_for_render(view, ground),
                    "near": max(1, radius / 50),
                },
            )
            name = f"render-{view['id']}.png"
            page.locator("canvas").screenshot(path=str(run / name))
            shots.append(name)
        for name, azimuth, elevation, scale in (
            ("hero-a", 215, 38, 0.9),
            ("hero-b", 35, 32, 0.9),
            ("hero-c", 125, 28, 0.85),
        ):
            page.evaluate("v=>worldscale.view(...v)", [azimuth, elevation, scale])
            page.locator("canvas").screenshot(path=str(run / f"{name}.png"))
            shots.append(f"{name}.png")
        if layout is not None:
            flat = page.evaluate("l=>worldscale.heightMap(l)", layout)
            inspection["model"] = np.array(
                [np.nan if v is None else v for v in flat], float
            ).reshape(layout["nv"], layout["nu"])
            write_json(
                run / "model-heights.json",
                {
                    "layout": layout,
                    "heights": [
                        None if not np.isfinite(v) else round(float(v), 2)
                        for v in inspection["model"].ravel()
                    ],
                },
            )

    report = capture(
        run,
        camera_override={
            "azimuth": 215,
            "elevation": 38,
            "scale": 0.8,
            "method": "area overview",
        },
        extra=extra,
        review_only=True,
        export_geometry=False,
    )
    if report.get("runtime_error") or not report.get("manifest"):
        stage("render", error=str(report.get("runtime_error") or report)[:400])
        result = {
            "status": "render-failed",
            "execution_status": "failed",
            "accepted": False,
            "quality_status": "unreviewed",
            "error": str(report.get("runtime_error") or report),
            "stages": stages,
        }
        write_json(run / "result.json", result)
        return result
    stage(
        "render",
        triangles=report["manifest"]["triangles"],
        draw_calls=report["manifest"]["performance"]["drawCalls"],
        build_failures=inspection.get("failures", []),
    )

    agreement, rows = None, []
    if "model" in inspection:
        agreement, rows = height_agreement(area, inspection["model"], above, layout)
        error_image(area, inspection["model"], above, layout, run / "height-error.png")
        write_json(run / "building-heights.json", rows)
    if views:
        pair_sheet(
            [
                (
                    v["id"]
                    + (" (partial source)" if not v.get("tiles_loaded") else ""),
                    measurements / v["image"],
                    run / f"render-{v['id']}.png",
                )
                for v in views
            ],
            run / "comparison.jpg",
        )
    sources = {}
    for building in area["buildings"]:
        label = building["height_source"].split(" (")[0].split(":")[0]
        sources[label] = sources.get(label, 0) + 1
    result = {
        "status": "area-built",
        "origin": area["origin"],
        "radius_m": radius,
        "model_calls": 0,
        "source_views": [
            {
                "id": v["id"],
                "tiles_complete": bool(v.get("tiles_loaded")),
                "geometry_stable": bool(v.get("surface_stable")),
            }
            for v in views
        ],
        "network_elevation": {
            "source": "OSM layer ordering; 6.5 m per layer is an estimated prior"
        },
        "execution_status": "completed"
        if report.get("passed")
        and set(inspection.get("built", [])) == {b["id"] for b in scene["buildings"]}
        else "failed",
        "accepted": False,
        "quality_status": "unreviewed",
        "checks": {
            "browser": bool(report.get("passed")),
            "all_buildings_present": set(inspection.get("built", []))
            == {b["id"] for b in scene["buildings"]},
            "recipes_without_fallback": not inspection.get("failures"),
        },
        "recipe_warnings": inspection.get("warnings", []),
        "counts": {
            "buildings": len(area["buildings"]),
            "roads": len(area["roads"]),
            "paths": len(area["paths"]),
            "rails": len(area["rails"]),
            "surfaces": len(area["surfaces"]),
            "trees": len(scene["trees"]),
            "street_objects": len(scene["points"]),
        },
        "height_sources": sources,
        "classes": stages[-2]["classes"]
        if len(stages) >= 2 and "classes" in stages[-2]
        else None,
        "build_failures": inspection.get("failures", []),
        "height_agreement": agreement,
        "worst_buildings": rows[:8],
        "triangles": report["manifest"]["triangles"],
        "draw_calls": report["manifest"]["performance"]["drawCalls"],
        "browser_checks_passed": bool(report.get("passed")),
        "seconds": round(time.monotonic() - started, 1),
        "inputs": {
            "map": str(osm_path),
            "measurements": str(measurements) if measurements else None,
        },
        "surface": surface,
        "style": (area.get("style") or {}).get("name"),
        "observation": observation,
        "measured_surfaces": {
            k: photo[k] for k in ("wall_observation", "views", "note")
        }
        | {"ortho_filled_fraction": photo["ortho"]["filled_fraction"]}
        if photo
        else None,
        "note": "Geometry and heights are compiled from map data and measurements; "
        + (
            "ground, roofs and walls carry reprojected capture imagery."
            if photo
            else "facades are procedural recipes driven by approximate observations, not recovered window layouts."
            if observation
            else "facades are class recipes, not observed window layouts."
        ),
    }
    stage("report")
    write_json(run / "result.json", result)
    return result


def run_area(
    latitude,
    longitude,
    radius,
    run,
    measurements=None,
    palette=None,
    osm=None,
    surface="recipes",
    style="faithful",
):
    area_model.validate_extent(latitude, longitude, radius)
    run = Path(run).resolve()
    if run.exists():
        raise ValueError("USE_NEW_AREA_RUN")
    try:
        return _run_area(
            latitude, longitude, radius, run, measurements, palette, osm, surface, style
        )
    except Exception as error:
        from worldascode.contracts.execution import record_failure

        result = {
            "status": "area-failed",
            "execution_status": "failed",
            "accepted": False,
            "quality_status": "unreviewed",
            "failure": record_failure(run, error).model_dump(),
        }
        write_json(run / "result.json", result)
        return result
