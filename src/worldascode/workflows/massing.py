"""Evidence -> fitted programme -> compiled World IR -> calibrated render review.

No step here is specific to one building: inputs are an evidence bundle (or bare
OSM outlines) and outputs are a programme, a World recipe and measurements.
"""

import json
import math
from pathlib import Path

from PIL import Image, ImageDraw

import worldascode.evidence.georeference as georef
import worldascode.geometry.massing as massing
from worldascode.adapters.rendering.browser import bundle, capture
from worldascode.evidence.images import evidence_capture, render_camera
from worldascode.storage.artifacts import digest, file_hash, write_json

# Review thresholds for the massing stage only. They say the outline agrees with
# the evidence views; they do not accept facade detail, materials or style.
MASSING_MEAN_IOU = 0.85
MASSING_MIN_IOU = 0.75
DETAIL_FIELDS = (
    "storeys",
    "bay_m",
    "window_width",
    "window_height",
    "dormers",
    "chimneys",
)


def contact_sheet(evidence, run, out, cell=(520, 390)):
    """Rows of scoped reference | render | silhouette difference, one row per view."""
    run = Path(run)
    views = evidence["views"]
    sheet = Image.new("RGB", (cell[0] * 3, cell[1] * len(views)), "#202020")
    draw = ImageDraw.Draw(sheet)
    for row, view in enumerate(views):
        for column, prefix in enumerate(("reference-", "view-", "diff-")):
            image = Image.open(run / (prefix + view["id"] + ".png")).convert("RGB")
            image.thumbnail(cell)
            sheet.paste(image, (column * cell[0], row * cell[1]))
        draw.text((8, row * cell[1] + 6), view["id"], fill="#ffffff")
    sheet.save(out)
    return out


def detail_defaults(program, evidence):
    """Storey count from tags or height when no observation supplies it."""
    tags = evidence.get("tags", {})
    try:
        storeys = int(float(tags["building:levels"]))
        source = "OSM building:levels"
    except (KeyError, ValueError):
        storeys = max(1, round(program.eave_height / 3.6))
        source = "eave height / 3.6 m"
    provenance = {**program.provenance, "storeys": source}
    return program.model_copy(update={"storeys": storeys, "provenance": provenance})


def author_details(evidence, program, run, settings, max_tokens=60000):
    """One bounded vision call that may set programme detail parameters only.

    The reply is validated field by field; registration, heights, roof form and
    every coordinate stay with the fitted programme.
    """
    from worldascode.adapters.llm.transport import Provider

    provider = Provider(settings, run, max_calls=1, max_tokens=max_tokens)
    facts = {
        "wall_height_m": round(program.eave_height, 2),
        "roof": program.roof.model_dump(),
        "edge_lengths_m": [
            round(v, 1)
            for v in massing.edge_lengths(massing.to_plan(evidence["footprint"]))
        ],
        "tags": evidence.get("tags", {}),
        "views": [v["id"] for v in evidence["views"]],
    }
    prompt = (
        "You are estimating repeatable facade and roof detail parameters of ONE building for a "
        "procedural generator. Geometry of walls and roof is already fixed by measurement; do not "
        "describe or change it. Images are rendered photogrammetry views of the same building, in "
        "the order listed; ignore clipped fragments, sky and melted or shadowed mesh artifacts.\n"
        "FACTS: " + json.dumps(facts) + "\n"
        'Return JSON {"storeys": int counted on the walls below the eave, "bay_m": typical '
        'horizontal spacing of windows in metres, "window_width": window width as a fraction of a '
        'bay (0.2-0.8), "window_height": window height as a fraction of a storey (0.3-0.8), '
        '"dormers": null or {"spacing_m": spacing along the eave, "width_m":, "height_m":}, '
        '"chimneys": null or {"spacing_m": spacing along the ridge, "width_m":, "above_ridge_m":}, '
        '"colours": {"wall": "#rrggbb", "roof": "#rrggbb", "trim": "#rrggbb"} as the sunlit '
        "surface colour of each material (not its shadowed appearance), "
        '"confidence": {field: "observed"|"inferred"}, "notes": [short strings]}. '
        "Use null when a feature is not visible. Estimate from what is visible; do not invent "
        "features to match an architectural style."
    )
    reply = provider.call(
        "program-detail", prompt, [v["image"] for v in evidence["views"]], 1500
    )
    write_json(Path(run) / "program-detail.json", reply)
    accepted, rejected = {}, {}
    for field in DETAIL_FIELDS:
        if field not in reply:
            continue
        try:
            trial = massing.BuildingProgram.model_validate(
                {**program.model_dump(), **accepted, field: reply[field]}
            )
            accepted[field] = getattr(trial, field)
        except ValueError as exc:
            rejected[field] = str(exc)[:200]
    provenance = {
        **program.provenance,
        **{
            field: "vision estimate ("
            + str(reply.get("confidence", {}).get(field, "unstated"))
            + ")"
            for field in accepted
        },
    }
    colours = reply.get("colours")
    if isinstance(colours, dict):
        try:
            from worldascode.contracts.world import _hex

            chosen = {
                k: _hex(colours[k]) for k in ("wall", "roof", "trim") if k in colours
            }
            accepted["appearance"] = massing.Appearance(
                **{
                    **program.appearance.model_dump(),
                    **chosen,
                    "source": "vision estimate of sunlit material colour from evidence views",
                }
            )
            provenance["appearance"] = (
                "vision estimate; sampled pixels are mostly shadowed"
            )
        except (ValueError, TypeError) as exc:
            rejected["colours"] = str(exc)[:200]
    write_json(
        Path(run) / "program-detail-validation.json",
        {"accepted": sorted(accepted), "rejected": rejected},
    )
    return program.model_copy(update={**accepted, "provenance": provenance})


def run_massing(evidence_path, run, program_path=None, settings=None):
    run = Path(run).resolve()
    run.mkdir(parents=True, exist_ok=True)
    evidence = georef.load_evidence(evidence_path)
    program, fit_report = massing.fit(evidence)
    program = detail_defaults(program, evidence)
    if settings is not None:
        program = author_details(evidence, program, run, settings)
    if program_path:
        supplied = json.loads(Path(program_path).read_text(encoding="utf-8"))
        unknown = set(supplied) - set(DETAIL_FIELDS) - {"cornice"}
        if unknown:
            raise ValueError(
                "PROGRAM_OVERRIDE_NOT_A_DETAIL_FIELD: " + ",".join(sorted(unknown))
            )
        program = massing.BuildingProgram.model_validate(
            {**program.model_dump(), **supplied}
        )
    # Roofs face the sky and are sampled in direct light; walls are mostly in
    # baked shadow, so a vision estimate of the wall colour is kept when present.
    program = massing.sample_appearance(
        evidence,
        program,
        ("roof",) if "appearance" in program.provenance else ("wall", "roof"),
    )
    write_json(run / "program.json", program.model_dump())
    write_json(run / "fit.json", fit_report)
    measured_roof = None
    heights = Path(evidence["path"]).parent / "heights.json"
    if heights.is_file():
        import worldascode.geometry.surface_height as dsm

        grid, layout = dsm.load(heights)
        plan = massing.registered_plan(evidence["footprint"], program.registration)
        measured_roof, roof_report, _ = dsm.fit_roof(
            grid, layout, plan, evidence["height_m"]
        )
        roof_report["heights_sha256"] = file_hash(heights)
        write_json(run / "roof-planes.json", measured_roof)
        write_json(run / "roof-fit.json", roof_report)
        program = program.model_copy(
            update={
                "eave_height": roof_report["eave_height_m"],
                "provenance": {
                    **program.provenance,
                    "eave_height": "20th percentile of sampled heights along the footprint rim",
                    "roof": "planes fitted to the sampled height field; parametric roof kept as the low-detail fallback",
                },
            }
        )
        write_json(run / "program.json", program.model_dump())
    blueprint_id = "building/" + evidence["object_id"]
    parts = massing.compile_parts(evidence["footprint"], program, measured_roof)
    world = {
        "origin": {
            **evidence["frame"]["origin"],
            "altitude": evidence["frame"]["ground_height_m"],
        },
        "blueprints": [
            massing.blueprint(blueprint_id, parts, program, tier="landmark")
        ],
        "instances": [
            {
                "id": evidence["object_id"],
                "blueprint": blueprint_id,
                "anchor": [0, 0, 0],
            }
        ],
    }
    first = render_camera(evidence["views"][0])
    write_json(
        run / "render-config.json",
        {"width": first["render_width"], "height": first["render_height"]},
    )
    bundle(run, world=world)
    browser = {}
    report = capture(
        run,
        camera_override={
            "azimuth": 35,
            "elevation": 30,
            "method": "review orbit; scoring uses evidence cameras",
        },
        extra=evidence_capture(evidence, run, browser),
    )
    contact_sheet(evidence, run, run / "evidence-contact-sheet.jpg")
    oblique = fit_report["fit_views"] or list(browser)
    scores = [browser[v]["iou"] for v in oblique]
    drift = max(abs(browser[v]["iou"] - fit_report["per_view_iou"][v]) for v in browser)
    result = {
        "accepted": False,
        "status": "massing-review",
        "object_id": evidence["object_id"],
        "evidence_sha256": file_hash(evidence["path"]),
        "program_sha256": digest(program.model_dump()),
        "browser_passed": report.get("passed", False),
        "triangles": report.get("manifest", {}).get("triangles"),
        "massing": {
            "mean_iou": round(sum(scores) / len(scores), 4),
            "min_iou": min(scores),
            "scored_views": oblique,
            "per_view": browser,
            "thresholds": {"mean": MASSING_MEAN_IOU, "min": MASSING_MIN_IOU},
            "passed": sum(scores) / len(scores) >= MASSING_MEAN_IOU
            and min(scores) >= MASSING_MIN_IOU,
            "roof_source": "measured height field"
            if measured_roof
            else "parametric fit",
            # Only comparable when the browser renders the same parametric parts that were fitted.
            "fit_vs_browser_max_iou_drift": None if measured_roof else round(drift, 4),
        },
        "note": "Massing agreement with calibrated evidence views only. Facade detail, materials and style have no acceptance gate here; accepted stays false.",
    }
    write_json(run / "result.json", result)
    return result


def run_district(osm_path, run, fitted=()):
    """Every OSM building outline as a compiled massing in one shared metric frame.

    Buildings with a fitted programme (a massing run directory) use it; the rest
    get a tag-derived default. Zero model calls.
    """
    run = Path(run).resolve()
    run.mkdir(parents=True, exist_ok=True)
    buildings = georef.osm_buildings(osm_path)
    if not buildings:
        raise ValueError("NO_BUILDING_WAYS_IN_SNAPSHOT")
    lon = sum(p[0] for b in buildings for p in b["ring"]) / sum(
        len(b["ring"]) for b in buildings
    )
    lat = sum(p[1] for b in buildings for p in b["ring"]) / sum(
        len(b["ring"]) for b in buildings
    )
    frame = georef.Frame(lon, lat)
    programs = {}
    for folder in fitted:
        folder = Path(folder)
        result = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        programs[result["object_id"]] = massing.BuildingProgram.model_validate(
            json.loads((folder / "program.json").read_text(encoding="utf-8"))
        )
    blueprints, instances, rows = [], [], []
    for b in buildings:
        local = [frame.model(*p)[::2] for p in b["ring"]]
        cx, cn = georef.centroid(massing.to_plan(local))
        footprint = [[x - cx, z + cn] for x, z in local]
        row = {"id": b["id"], "vertices": len(footprint)}
        try:
            if b["id"] in programs:
                program, row["source"] = programs[b["id"]], "fitted to imagery"
            else:
                height, source = massing.tag_height(b["tags"])
                program, row["source"] = (
                    massing.default_program(height, b["tags"]),
                    source,
                )
            parts = massing.compile_parts(footprint, program)
            blueprints.append(massing.blueprint("building/" + b["id"], parts, program))
        except ValueError as exc:
            row["skipped"] = str(exc)[:160]
            rows.append(row)
            continue
        instances.append(
            {"id": b["id"], "blueprint": "building/" + b["id"], "anchor": [cx, 0, -cn]}
        )
        row["height_m"] = round(program.eave_height + program.roof.rise, 2)
        rows.append(row)
    world = {
        "origin": {"longitude": lon, "latitude": lat},
        "blueprints": blueprints,
        "instances": instances,
    }
    bundle(run, world=world)
    report = capture(
        run, camera_override={"azimuth": 200, "elevation": 40, "method": "review orbit"}
    )
    extent = max(math.hypot(*i["anchor"][::2]) for i in instances)
    result = {
        "accepted": False,
        "status": "district-draft",
        "buildings": len(instances),
        "fitted_to_imagery": sum(r.get("source") == "fitted to imagery" for r in rows),
        "skipped": [r for r in rows if "skipped" in r],
        "model_calls": 0,
        "triangles": report.get("manifest", {}).get("triangles"),
        "browser_passed": report.get("passed", False),
        "radius_m": round(extent, 1),
        "note": "Tag-derived massings are placeholders with stated sources; multipolygon relations, roads and terrain are not included.",
    }
    write_json(run / "buildings.json", rows)
    write_json(run / "result.json", result)
    return result
