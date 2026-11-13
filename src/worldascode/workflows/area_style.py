"""Style references -> authored procedural families -> transfer/render/review.

Map preparation stays deterministic. This stage replaces the default building
recipes with model-authored JavaScript, reusable across member sites and areas.
Only accepted local recipe drafts enter the content-addressed cache; this is
not publication to the shared kit library.
"""

import copy
import json
import math
import os
import shutil
import tempfile
from pathlib import Path
from typing import Literal

from PIL import Image, ImageDraw
from pydantic import Field

from worldascode.adapters.geospatial.inspection import project_bounds
from worldascode.adapters.llm.transport import Provider, request_reserve
from worldascode.adapters.rendering.browser import capture
from worldascode.config import ACCEPT, RESOURCE_ROOT, Settings, paths
from worldascode.contracts.execution import record_failure
from worldascode.contracts.region import Bounds, Strict
from worldascode.geometry import area_look, area_measure, area_style
from worldascode.kits.code import analyze_source, lint
from worldascode.kits.context import context
from worldascode.nodes.building import style_sheet
from worldascode.quality.evaluation import validated_scores
from worldascode.storage.artifacts import digest, file_hash, write_json
from worldascode.workflows.area import build_scene, bundle_scene

VERSION = "area-style-families-2"


def write_module(path, code):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        stream.write(code.encode("utf-8"))
        temporary = Path(stream.name)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class Light(Strict):
    sun: float = Field(default=2.4, ge=1, le=5)
    sky: float = Field(default=1.2, ge=0.5, le=3)
    exposure: float = Field(default=1, ge=0.6, le=1.4)


class Environment(Strict):
    palette: dict = Field(default_factory=dict)
    light: Light = Field(default_factory=Light)
    tree_detail: int = Field(default=2, ge=0, le=2)
    projection: Literal["perspective", "orthographic"] = "perspective"
    profile: dict = Field(default_factory=dict)


class Architecture(Strict):
    facade: str = Field(
        default="unknown",
        pattern=r"^(unknown|curtain_grid|vertical_fins|horizontal_bands|masonry_punched|colonnade)$",
    )
    material: str = Field(
        default="unknown", pattern=r"^(unknown|glass|stone|brick|concrete|metal)$"
    )
    bay_m: float | None = Field(default=None, ge=0.8, le=12)
    glazing_fraction: float | None = Field(default=None, ge=0.05, le=0.95)
    wall_colour: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    confidence: float = Field(default=0, ge=0, le=1)


def architecture_boards(scene, views, ground, folder):
    thumbnails = []
    for entry in scene["buildings"]:
        images = crops(
            [entry], views, ground, folder / "crops" / digest(entry["id"])[:12], limit=1
        )
        if images:
            thumbnails.append(images[0])
    result = []
    for offset in range(0, len(thumbnails), 9):
        selected = thumbnails[offset : offset + 9]
        board = Image.new("RGB", (960, 320 * math.ceil(len(selected) / 3)), "#222222")
        for i, path in enumerate(selected):
            with Image.open(path) as image:
                image = image.convert("RGB")
                image.thumbnail((320, 320))
                board.paste(image, ((i % 3) * 320, (i // 3) * 320))
        path = folder / f"architecture-{offset // 9}.jpg"
        board.save(path, quality=92)
        result.append(path)
    return result


def observe_architecture(provider, scene, views, ground, folder):
    if len(scene["buildings"]) > 24:
        observed = {}
        for i in range(0, len(scene["buildings"]), 24):
            observed.update(
                observe_architecture(
                    provider,
                    {**scene, "buildings": scene["buildings"][i : i + 24]},
                    views,
                    ground,
                    folder / f"batch-{i // 24}",
                )
            )
        return observed
    boards = architecture_boards(scene, views, ground, folder)
    if not boards:
        return {e["id"]: Architecture().model_dump() for e in scene["buildings"]}
    reply = provider.call(
        "area-architecture-observer",
        "Observe actual architectural differences for the labeled entity IDs in source crop boards. "
        "A projected crop may contain a foreground neighbor; if the named target is occluded/unresolved, use unknown and low confidence. "
        "Return {entities:{entity_id:architecture}} using ONLY the listed IDs and this architecture schema. "
        "Preserve material identity and facade rhythm; estimate intrinsic wall colour only if visible, not baked shadow. "
        "Do not change footprints, heights, storeys, camera or world coordinates. Missing entities will stay unknown. "
        "\nSCHEMA: "
        + json.dumps(Architecture.model_json_schema())
        + "\nTARGETS: "
        + json.dumps(
            {
                e["id"]: {
                    "height": e["site"]["eave_m"],
                    "tags": e["site"].get("tags", {}),
                    "kind": e["site"]["appearance"]["class"],
                    "observed_cues": e["site"].get("observed", {}),
                }
                for e in scene["buildings"]
            }
        ),
        boards,
        5500,
    )
    supplied = reply.get("entities")
    if not isinstance(supplied, dict) or not set(supplied) <= {
        e["id"] for e in scene["buildings"]
    }:
        raise ValueError("ARCHITECTURE_OBSERVER_ENTITY_INVALID")
    return {
        e["id"]: Architecture.model_validate(supplied.get(e["id"], {})).model_dump()
        for e in scene["buildings"]
    }


def families(scene):
    groups = {}
    for entry in scene["buildings"]:
        site = entry["site"]
        key = "-".join(
            (
                site["appearance"]["class"],
                site["roof"]["form"],
                "courtyard" if site.get("holes") else "solid",
            )
        )
        site["recipe_family"] = key
        groups.setdefault(key, []).append(entry)
    return groups


def representatives(members, limit=2):
    ordered = sorted(
        members,
        key=lambda e: (e["site"]["eave_m"], len(e["site"]["footprint"]), e["id"]),
    )
    indices = sorted(
        {
            round(i * (len(ordered) - 1) / max(1, limit - 1))
            for i in range(min(limit, len(ordered)))
        }
    )
    return [ordered[i] for i in indices]


def observed_tone_examples(area):
    """Bounded tone ranges let style interpretation compensate for capture lighting."""
    groups = {}
    for building in area["buildings"]:
        observed = building.get("observed", {})
        if observed.get("wall_rgb"):
            groups.setdefault(building["appearance"]["class"], []).append(observed)
    result = {}
    for name, values in groups.items():
        values = sorted(values, key=lambda v: sum(v["wall_rgb"]))
        chosen = sorted({0, len(values) // 2, len(values) - 1})
        result[name] = [
            {
                k: values[i].get(k)
                for k in (
                    "wall_rgb",
                    "glass_rgb",
                    "roof_rgb",
                    "glass_fraction",
                    "rhythm",
                )
            }
            for i in chosen
        ]
    return result


def expected_bounds(entry):
    site, anchor = entry["site"], entry["anchor"]
    elevation = entry.get("elevation_m", 0)
    return Bounds(
        min=(
            min(p[0] for p in site["footprint"]) + anchor[0],
            elevation,
            min(p[1] for p in site["footprint"]) + anchor[1],
        ),
        max=(
            max(p[0] for p in site["footprint"]) + anchor[0],
            elevation + max(site["top_m"], site["eave_m"]),
            max(p[1] for p in site["footprint"]) + anchor[1],
        ),
    )


def validate_recipe(code, members):
    problems = lint(code)
    if problems:
        raise ValueError("STYLE_RECIPE_LINT: " + "; ".join(problems))
    analysis = analyze_source(code)
    if analysis.get("material_literal_errors"):
        raise ValueError(
            "STYLE_RECIPE_MATERIAL_ID_REQUIRED: "
            + json.dumps(analysis["material_literal_errors"])
            + "; use declared string material IDs; louvers is not a boolean toggle"
        )
    if any(
        json.dumps(e["id"]) in code or ("'" + e["id"] + "'") in code for e in members
    ):
        raise ValueError("STYLE_RECIPE_HARDCODED_ENTITY_ID")
    return code


def load_pack(folder, key):
    folder = Path(folder)
    manifest = json.loads((folder / "pack.json").read_text(encoding="utf-8"))
    if manifest.get("key") != key or manifest.get("status") != "accepted-local-draft":
        raise ValueError("STYLE_PACK_NOT_ACCEPTED_OR_STYLE_RUNTIME_MISMATCH")
    codes = {}
    for family, record in manifest["recipes"].items():
        path = (folder / record["file"]).resolve()
        if (
            not path.is_relative_to(folder.resolve())
            or file_hash(path) != record["sha256"]
        ):
            raise ValueError("STYLE_PACK_HASH_OR_PATH_INVALID")
        codes[family] = path.read_text(encoding="utf-8")
    return codes, manifest


def source_views(source, area):
    folder = source / "inputs" / "measurements"
    path = folder / "reference-views.json"
    if not path.is_file():
        return []
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("origin") != area["origin"]:
        raise ValueError("STYLE_SOURCE_FRAME_MISMATCH")
    views = []
    for view in manifest["views"]:
        image = (folder / view["image"]).resolve()
        if (
            not image.is_relative_to(folder.resolve())
            or file_hash(image) != view["sha256"]
        ):
            raise ValueError("STYLE_SOURCE_IMAGE_HASH_OR_PATH_INVALID")
        views.append({**view, "image": str(image)})
    return views


def crops(members, views, ground, folder, rendered=None, limit=4):
    folder.mkdir(parents=True, exist_ok=True)
    result = []
    for member in members:
        options = []
        for view in views:
            camera = area_measure.pose_for_render(view, ground)
            rect = project_bounds(camera, expected_bounds(member))
            if rect:
                area = math.prod(
                    max(0, b - a) for a, b in zip(rect["min"], rect["max"])
                )
                options.append((view.get("pitch_deg", -35) > -80, area, view, rect))
        ordered = sorted(options, key=lambda x: x[:2], reverse=True)
        chosen = ordered[:1]
        count = min(2, max(1, math.ceil(limit / max(1, len(members)))))
        if count > 1:
            overhead = next(
                (item for item in ordered if item[2].get("pitch_deg", -35) < -80), None
            )
            if overhead and overhead not in chosen:
                chosen.append(overhead)
            elif len(ordered) > 1:
                chosen.append(ordered[1])
        for _, _, view, rect in chosen:
            image = (
                Path(rendered) / ("source-" + view["id"] + ".png")
                if rendered
                else Path(view["image"])
            )
            with Image.open(image) as original:
                margin = 12
                box = (
                    max(0, math.floor(rect["min"][0]) - margin),
                    max(0, math.floor(rect["min"][1]) - margin),
                    min(original.width, math.ceil(rect["max"][0]) + margin),
                    min(original.height, math.ceil(rect["max"][1]) + margin),
                )
                tile = original.convert("RGB").crop(box)
                tile.thumbnail((480, 480))
                ImageDraw.Draw(tile).text(
                    (3, 3),
                    member["id"] + " / " + view["id"],
                    fill="white",
                    stroke_width=1,
                    stroke_fill="black",
                )
                dest = folder / (digest([member["id"], view["id"]])[:16] + ".jpg")
                tile.save(dest, quality=90)
                result.append(dest)
    return result[:limit]


def render_candidate(folder, scene, codes, views, ground):
    folder.mkdir(parents=True, exist_ok=True)
    modules = {}
    for family, code in codes.items():
        path = folder / "recipes" / (family + ".mjs")
        path.parent.mkdir(exist_ok=True)
        path.write_text(code, encoding="utf-8")
        modules[family] = path
    bundle_scene(folder, scene, modules)
    inspection = {}

    def extra(page, shots):
        inspection.update(
            page.evaluate(
                "({failures:worldscale.root.userData.buildFailures,warnings:worldscale.root.userData.buildWarnings,entities:worldscale.addresses().entities,canopyParts:Object.values(worldscale.root.userData.componentIndex??{}).filter(p=>['loft','walls','volume'].includes(p.kind))})"
            )
        )
        for view in views:
            pose = area_measure.pose_for_render(view, ground)
            page.evaluate(
                "c=>worldscale.pose(c)",
                {**pose, "near": max(1, scene["radius_m"] / 50)},
            )
            name = "source-" + view["id"] + ".png"
            page.locator("canvas").screenshot(path=str(folder / name))
            shots.append(name)

    report = capture(
        folder,
        camera_override={"azimuth": 215, "elevation": 38, "scale": 0.9},
        extra=extra,
        review_only=True,
        export_geometry=False,
    )
    entities = inspection.get("entities", {})
    envelope = {}
    envelope_errors = {}
    canopy_open = {}
    for member in scene["buildings"]:
        expected = expected_bounds(member)
        actual = entities.get(member["id"], {}).get("bounds")
        envelope[member["id"]] = bool(
            actual
            and all(
                actual["min"][i]
                >= expected.min[i] - max(1, (expected.max[i] - expected.min[i]) * 0.15)
                and actual["max"][i]
                <= expected.max[i] + max(1, (expected.max[i] - expected.min[i]) * 0.25)
                for i in range(3)
            )
            and actual["max"][1]
            >= member.get("elevation_m", 0) + member["site"]["eave_m"] * 0.8
        )
        if not envelope[member["id"]]:
            envelope_errors[member["id"]] = {
                "expected": expected.model_dump(mode="json"),
                "actual": actual,
            }
        if member["site"]["appearance"]["class"] == "canopy":
            width = max(0.1, expected.max[0] - expected.min[0])
            depth = max(0.1, expected.max[2] - expected.min[2])
            canopy_open[member["id"]] = not any(
                p["entity_id"] == member["id"]
                and p["bounds"]["max"][1] - p["bounds"]["min"][1]
                > member["site"]["eave_m"] * 0.5
                and (p["bounds"]["max"][0] - p["bounds"]["min"][0])
                * (p["bounds"]["max"][2] - p["bounds"]["min"][2])
                > 0.5 * width * depth
                for p in inspection.get("canopyParts", [])
            )
    checks = {
        "browser": bool(report.get("passed")),
        "no_recipe_fallback": not inspection.get("failures"),
        "all_entities": set(entities) == {e["id"] for e in scene["buildings"]},
        "envelopes": all(envelope.values()),
        "canopies_open": all(canopy_open.values()),
        "triangles": 0
        < report.get("manifest", {}).get("triangles", 0)
        <= 200000 * len(scene["buildings"]),
    }
    metrics = {
        "passed": all(checks.values()),
        "checks": checks,
        "entity_envelopes": envelope,
        "envelope_errors": envelope_errors,
        "canopy_open": canopy_open,
        "failures": inspection.get("failures", []),
        "warnings": inspection.get("warnings", []),
        "triangles": report.get("manifest", {}).get("triangles", 0),
        "performance": report.get("manifest", {}).get("performance"),
    }
    write_json(folder / "metrics.json", metrics)
    return metrics


def validate_review(review, revision, groups):
    scores = validated_scores(review)
    if review.get("revision") != revision:
        raise ValueError("STALE_STYLE_REVIEW")
    defects = review.get("defects")
    if not isinstance(defects, list) or len(defects) > 30:
        raise ValueError("STYLE_DEFECTS_INVALID")
    for d in defects:
        family = d.get("family")
        owners = {e["id"] for e in groups.get(family, [])}
        if (
            not owners
            or not isinstance(d.get("entity_ids"), list)
            or not d["entity_ids"]
            or not set(d["entity_ids"]) <= owners
            or not isinstance(d.get("correction"), str)
        ):
            raise ValueError("STYLE_DEFECT_ADDRESS_INVALID")
    return scores, defects


def run_area_style(
    source,
    styles,
    run,
    settings=None,
    max_rounds=1,
    max_tokens=220000,
    reuse_pack=None,
    initial_run=None,
    projection=None,
    provider=None,
):
    source, run = Path(source).resolve(), Path(run).resolve()
    styles = [Path(p).resolve() for p in styles]
    if not styles or len(styles) > 6 or not 0 <= max_rounds <= 3:
        raise ValueError("STYLE_REFERENCE_OR_ROUND_LIMIT_INVALID")
    if initial_run and reuse_pack:
        raise ValueError("STYLE_INITIAL_RUN_AND_PACK_ARE_EXCLUSIVE")
    if projection not in (None, "perspective", "orthographic"):
        raise ValueError("STYLE_PROJECTION_INVALID")
    area = json.loads((source / "area.json").read_text(encoding="utf-8"))
    scene = build_scene(area)
    groups = families(scene)
    if not groups or len(groups) > 24:
        raise ValueError("STYLE_FAMILY_COUNT_INVALID")
    run.mkdir(parents=True, exist_ok=False)
    style_paths = []
    for i, p in enumerate(styles):
        target = run / "styles" / (str(i) + p.suffix)
        target.parent.mkdir(exist_ok=True)
        shutil.copy2(p, target)
        style_paths.append(target)
    key = digest(
        {
            "version": VERSION,
            "styles": [file_hash(p) for p in style_paths],
            "kit": file_hash(RESOURCE_ROOT / "runtime/kit.mjs"),
            "api": file_hash(RESOURCE_ROOT / "runtime/kit-api.md"),
        }
    )
    cache = paths().cache_dir / "style-recipes" / key
    provider = provider or Provider(
        settings or Settings.load(),
        run,
        max_calls=6
        + math.ceil(len(scene["buildings"]) / 24)
        + len(groups) * (max_rounds + 2),
        max_tokens=max_tokens,
        max_seconds=3600,
    )
    attempts = []
    codes = {}
    selected = None
    last_built = None
    best_rank = None
    review_reserve, budget_stop = 0, None
    try:
        views = source_views(source, area)
        ground = area.get("ground", {}).get("ellipsoid_height_m", 0)
        cache_folder = Path(reuse_pack) if reuse_pack else cache
        if initial_run:
            prior = Path(initial_run).resolve()
            receipt = json.loads((prior / "inputs.json").read_text(encoding="utf-8"))
            if receipt["style_images"] != [
                file_hash(p) for p in style_paths
            ] or receipt["area_sha256"] != file_hash(source / "area.json"):
                raise ValueError("STYLE_INITIAL_RUN_INPUT_MISMATCH")
            outcome = json.loads((prior / "result.json").read_text(encoding="utf-8"))
            style = json.loads((prior / "style.json").read_text(encoding="utf-8"))
            if outcome.get("selected_render"):
                rendered = Path(outcome["selected_render"]).resolve()
                if (
                    not rendered.is_relative_to(prior)
                    or not (rendered / "scene.json").is_file()
                ):
                    raise ValueError("STYLE_INITIAL_RUN_RETAINED_RENDER_REQUIRED")
                previous_scene = json.loads(
                    (rendered / "scene.json").read_text(encoding="utf-8")
                )
                environment = Environment(
                    palette=previous_scene["palette"],
                    light=Light.model_validate(style["light"]),
                    tree_detail=style.get("tree_detail", 2),
                    projection=style.get("projection", "perspective"),
                    profile=style.get("look_profile", {}),
                )
                recipe_folder, partial = rendered / "recipes", False
            else:
                # A failed author call must not discard earlier paid, validated modules.
                environment = Environment.model_validate(
                    json.loads((prior / "environment.json").read_text(encoding="utf-8"))
                )
                recipe_folder, partial = prior / "draft-recipes", True
            for family in groups:
                path = recipe_folder / (family + ".mjs")
                if partial and not path.is_file():
                    continue
                codes[family] = validate_recipe(
                    path.read_text(encoding="utf-8"), groups[family]
                )
            if not codes:
                raise ValueError("STYLE_INITIAL_RUN_RECIPES_REQUIRED")
            small = style_paths
        elif (cache_folder / "pack.json").is_file():
            codes, pack = load_pack(cache_folder, key)
            style, environment = (
                pack["style"],
                Environment.model_validate(pack["environment"]),
            )
            small = style_paths
        else:
            style, small = style_sheet(provider, style_paths, run)
            reply = provider.call(
                "area-style-environment",
                "Derive a coherent AREA style configuration from the style image and sheet. Retain material identities; do not import the reference city architecture/geography. "
                "profile is optional numeric interpretation of observed tones and procedural form: {name:'custom',colour:{saturation:0..4,value_floor:0..1,value_gain:0..4,tint:'#rrggbb',tint_strength:0..1},glass:{same colour rules},window_scale:0.5..1.5,bay_scale:0.5..3,facade_mode:'texture'|'relief',relief_m:0..0.8,roof_detail:boolean}. No descriptive lists in profile. Do not erase material differences. Return only this schema: "
                + json.dumps(Environment.model_json_schema())
                + "\nSTYLE: "
                + json.dumps(style)
                + "\nBASE PALETTE: "
                + json.dumps(scene["palette"])
                + "\nOBSERVED TONE RANGES (include capture shadows/skylight; choose profile transforms to lift them into the STYLE, without treating shadow-blue paving or shadow-dark cladding as intrinsic material): "
                + json.dumps(observed_tone_examples(area)),
                small,
                1800,
            )
            environment = Environment.model_validate(reply)
        check_area = copy.deepcopy(area)
        render_profile = area_look.resolve(environment.profile)
        if projection:
            environment = environment.model_copy(update={"projection": projection})
        area_style.apply(check_area, environment.palette)
        if any("observed" in b for b in area["buildings"]):
            area_look.apply(
                check_area,
                {
                    "light": {
                        "background": check_area["palette"]["background"],
                        "ground": check_area["palette"]["ground"],
                    },
                    **environment.profile,
                },
            )
        scene["palette"] = check_area["palette"]
        appearances = {b["id"]: b["appearance"] for b in check_area["buildings"]}
        for e in scene["buildings"]:
            original = e["site"]["appearance"]
            e["site"]["appearance"] = {
                **original,
                **appearances[e.get("source_id", e["id"])],
            }
            e["site"]["colours"] = {
                k: e["site"]["appearance"][k] for k in ("wall", "roof", "trim")
            }
        scene["style"] = {
            **render_profile,
            **(check_area.get("style") or {}),
            **style,
            "light": environment.light.model_dump(),
            "tree_detail": environment.tree_detail,
            "projection": environment.projection,
            "look_profile": environment.profile,
        }
        scene["requireAuthoredRecipes"] = True
        architecture = observe_architecture(
            provider, scene, views, ground, run / "architecture"
        )
        write_json(run / "architecture.json", architecture)
        for entry in scene["buildings"]:
            entry["site"]["architecture"] = architecture[entry["id"]]
        write_json(run / "style.json", scene["style"])
        write_json(run / "environment.json", environment.model_dump())
        write_json(
            run / "families.json",
            {
                k: {
                    "entity_ids": [e["id"] for e in members],
                    "author_examples": [e["id"] for e in representatives(members)],
                    "transfer_entities": [
                        e["id"] for e in members if e not in representatives(members)
                    ],
                }
                for k, members in groups.items()
            },
        )
        write_json(
            run / "inputs.json",
            {
                "source_run": str(source),
                "area_sha256": file_hash(source / "area.json"),
                "style_key": key,
                "style_images": [file_hash(p) for p in style_paths],
            },
        )
        pending = set(groups)
        feedback = {}
        for iteration in range(max_rounds + 1):
            repaired_this_round = False
            for family in sorted(pending):
                if iteration == 0 and family in codes:
                    validate_recipe(codes[family], groups[family])
                    continue
                examples = representatives(groups[family])
                reference_images = crops(
                    examples, views, ground, run / "reference-crops" / family, limit=3
                )
                requested = (
                    ["geometry"]
                    if family.startswith(("canopy", "raised"))
                    else ["systems", "facades", "massing"]
                )
                api = context(
                    RESOURCE_ROOT / "runtime/kit-api.md",
                    site=examples[0]["site"],
                    requested=requested,
                    previous=codes.get(family, ""),
                    feedback=feedback.get(family, []),
                    max_chars=16000,
                )["text"]
                prompt = (
                    "Write ONE reusable procedural JavaScript recipe for this architectural family in the user visual STYLE. "
                    "Return {code:string,intent:string,uncertainty:[strings]}. code exports function design(site,b,style). "
                    "Keep the module concise (roughly 40-100 lines, no long commentary); reuse kit systems and loops. "
                    "You create the architecture with the building kit: real framed windows/mullions, facade rhythm, layered roof forms, entrances, materials and relief. "
                    "Changing colors alone does not meet the goal. Dense repeated elements must use loops and derived dimensions, bounded by site length/storeys. "
                    "Support live style controls: style.facade_mode ('texture' or 'relief'), style.relief_m, style.bay_scale, style.window_scale, style.roof_detail and style.glow. Use site.appearance wall/glass/roof/frame colors as the profile's rendered observations, not hardcoded facade colors. Texture mode keeps repeated fields inexpensive; relief adds bounded aggregated framing/fins. Disabling roof_detail removes secondary fixtures, never the defining roof silhouette. "
                    "For towers use aggregated b.curtainWall/b.frameGrid/b.fins for repeated geometry; never create one separate b.window part per bay on every floor. Reserve individual window parts for distinctive close details. "
                    "Preserve site footprint, height and ground frame using b.walls for buildings. For kind mass (canopy/raised), use b.loft and measured min_height_m. "
                    "Do not call b.ground: area terrain is host-owned. Open canopies are roofs on posts, never solid blocks down to ground; raised masses start at min_height_m. "
                    "No imports/network, world coordinates, object IDs/names or city-specific constants. The SAME function runs on all family members, including sites not shown here. "
                    "Use site.edges and semantic facing/length/end attributes, never assume fixed edge order/count. Derive roof from site.roof; source uncertainty is not a mandate to copy melted mesh. "
                    "Use site.architecture as entity-specific observations: branch on facade/material, bay_m and glazing_fraction when confidence is sufficient. Unknown values use conservative defaults. The family may contain vertical fins, horizontal bands or punched masonry; do not force every building into the same blue curtain grid. Never branch on entity ID. "
                    "site.observed contains numeric cues from visible source pixels: wall/glass/roof RGB, glazing share and rhythm. They are approximate and can include capture shadows; use as evidence of differences, not photographic textures or proof of semantic materials. "
                    "For site.part_of this is an upper mass: the host places it at its measured elevation; all dimensions and roof heights in site are already LOCAL. Do not add the parent's height again or extend walls below local zero. "
                    "The first images are identified source crops, possibly occluded/partial. The final images are STYLE references: transfer visual treatment and detail density, not their geography or building shapes. "
                    "Material IDs must be declared strings, not booleans. b.at returns a frame object, not an array. Box/cylinder y is bottom. "
                    "For roof sections rotation_y_rad aligns local +X with LENGTH: b.box(b.at(cx,cz,rotation_y_rad),{w:length_m,d:width_m,...}). Never swap length and width; that rotates long roof masses across the footprint. Retain site.roof.mechanical/volumes as roof layout priors rather than a single arbitrary cube. "
                    "For courtyard site.holes use flat roof if no suitable measured roof sections; keep courtyard open. "
                    "Avoid excessive triangles: balance modeled facade relief with textured repeated fields; target <60000 triangles per ordinary building. "
                    "\nKIT:\n"
                    + api
                    + "\nSTYLE:\n"
                    + json.dumps(scene["style"])
                    + "\nFAMILY:\n"
                    + family
                    + "\nFAMILY ARCHITECTURAL VARIANTS:\n"
                    + json.dumps([e["site"]["architecture"] for e in groups[family]])
                    + "\nEXAMPLE SITES:\n"
                    + json.dumps([e["site"] for e in examples])
                    + "\nPREVIOUS CODE:\n"
                    + codes.get(family, "")
                    + "\nFEEDBACK:\n"
                    + json.dumps(feedback.get(family, []))
                )
                if iteration and review_reserve and hasattr(provider, "max_tokens"):
                    remaining = provider.max_tokens - sum(
                        provider.usage.get(k, 0)
                        for k in (
                            "input_tokens",
                            "output_tokens",
                            "unknown_token_reserve",
                        )
                    )
                    needed = (
                        request_reserve(prompt, [*reference_images, *small], 4200)
                        + review_reserve
                    )
                    if remaining < needed:
                        budget_stop = {
                            "reason": "reserve_final_review",
                            "remaining_tokens": remaining,
                            "required_reserve": needed,
                            "deferred_family": family,
                        }
                        break
                reply = provider.call(
                    "area-recipe-author-" + family + "-" + str(iteration),
                    prompt,
                    [*reference_images, *small],
                    4200,
                )
                try:
                    codes[family] = validate_recipe(reply.get("code"), groups[family])
                except ValueError as invalid:
                    reply = provider.call(
                        "area-recipe-author-contract-" + family + "-" + str(iteration),
                        prompt
                        + "\nINVALID CODE:\n"
                        + str(reply.get("code"))
                        + "\nVALIDATION ERROR:\n"
                        + str(invalid)
                        + "\nReturn corrected complete code.",
                        [*reference_images, *small],
                        4200,
                    )
                    codes[family] = validate_recipe(reply.get("code"), groups[family])
                draft = run / "draft-recipes" / (family + ".mjs")
                draft.parent.mkdir(exist_ok=True)
                draft.write_text(codes[family], encoding="utf-8")
                repaired_this_round = True
                write_json(
                    run / "intents" / (family + f"-{iteration}.json"),
                    {k: v for k, v in reply.items() if k != "code"},
                )
            if iteration and budget_stop and not repaired_this_round:
                break
            codes = {k: codes[k] for k in groups}
            revision = digest(codes)
            folder = run / f"attempt-{iteration}"
            metrics = render_candidate(folder, scene, codes, views, ground)
            last_built = {
                "iteration": iteration,
                "render": str(folder),
                "revision": revision,
                "metrics": metrics,
                "accepted": False,
                "evaluation": "unreviewed",
            }
            write_json(folder / "evaluation-pending.json", last_built)
            review = {
                "revision": revision,
                "likeness": 0,
                "style": 0,
                "detail": 0,
                "defects": [],
            }
            image_manifest = [{"type": "generated overview"}]
            review_images = [folder / "front.png"]
            examples = [
                e for members in groups.values() for e in representatives(members, 1)
            ]
            refs = crops(
                examples,
                views,
                ground,
                folder / "review-reference",
                limit=len(examples),
            )
            outputs = crops(
                examples,
                views,
                ground,
                folder / "review-output",
                rendered=folder,
                limit=len(examples),
            )
            for ref, out in zip(refs, outputs):
                review_images.extend([ref, out])
                image_manifest.extend(
                    [
                        {"type": "source crop; may be partial/occluded"},
                        {"type": "same-camera generated crop"},
                    ]
                )
            review_images.extend(small)
            image_manifest.extend({"type": "user STYLE reference"} for _ in small)
            review_prompt = (
                "Review actual procedural architecture and user STYLE fidelity, not merely palette or successful execution. "
                "The objective is recognizable procedural reconstruction IN THE REQUESTED STYLE, not a photographic pixel match. Judge spatial layout, massing, characteristic roofs, material identity and useful detail; allow simplified incidental fixtures and intentionally normalized lighting. Do not penalize removing baked shadows, mesh melting or source-image noise. "
                "Style is visual treatment, not reference city architecture. Source crops can be partial or occluded. "
                "Evaluate facade relief, material scale, roof hierarchy, glazing, greenery and area coherence. Geometry guard results are mandatory. "
                "Return {revision:exact revision,likeness:0..1,style:0..1,detail:0..1,defects:[{family:exact key,entity_ids:[members of that family],correction:string}]}. "
                "Address defects to the family whose code must change. Empty defects only if all important issues are resolved. "
                "\nREVISION: "
                + revision
                + "\nSTYLE: "
                + json.dumps(scene["style"])
                + "\nFAMILIES: "
                + json.dumps({k: [e["id"] for e in v] for k, v in groups.items()})
                + "\nMETRICS: "
                + json.dumps(metrics)
                + "\nIMAGE ORDER: "
                + json.dumps(image_manifest)
            )
            # Keep enough for a final review and a small growth/contract-repair margin.
            review_reserve = request_reserve(review_prompt, review_images, 2600) + 8192
            review = provider.call(
                "area-style-critic-" + str(iteration),
                review_prompt,
                review_images,
                2600,
            )
            try:
                scores, defects = validate_review(review, revision, groups)
            except ValueError as invalid:
                review = provider.call(
                    "area-style-critic-contract-" + str(iteration),
                    "Repair this review contract only. Return {revision,likeness,style,detail,defects:[{family,entity_ids,correction}]}. "
                    "Each entity must belong to the named family in the authoritative map. Split defects across families; never guess ownership. "
                    "\nREVISION: "
                    + revision
                    + "\nOWNER MAP: "
                    + json.dumps({k: [e["id"] for e in v] for k, v in groups.items()})
                    + "\nINVALID REVIEW: "
                    + json.dumps(review)
                    + "\nERROR: "
                    + str(invalid),
                    (),
                    2600,
                )
                scores, defects = validate_review(review, revision, groups)
            accepted = (
                metrics["passed"]
                and not defects
                and all(scores[k] >= v for k, v in ACCEPT.items())
            )
            record = {
                "iteration": iteration,
                "revision": revision,
                "render": str(folder),
                "metrics": metrics,
                "review": review,
                "accepted": accepted,
                "recipe_hashes": {k: digest(v) for k, v in codes.items()},
            }
            attempts.append(record)
            write_json(folder / "review.json", record)
            (folder / "evaluation-pending.json").unlink(missing_ok=True)
            rank = (bool(accepted), metrics["passed"], min(scores.values()))
            if best_rank is None or rank > best_rank:
                selected = record
                best_rank = rank
            if accepted:
                cache.mkdir(parents=True, exist_ok=True)
                records = {}
                for family, code in codes.items():
                    dest = cache / (family + "-" + digest(code)[:16] + ".mjs")
                    write_module(dest, code)
                    records[family] = {"file": dest.name, "sha256": file_hash(dest)}
                write_json(
                    cache / "pack.json",
                    {
                        "key": key,
                        "status": "accepted-local-draft",
                        "style": style,
                        "environment": environment.model_dump(),
                        "recipes": records,
                        "validation_run": str(folder),
                        "note": "Local style cache; not promotion/publication to the shared kit library.",
                    },
                )
                break
            feedback = {}
            for defect in defects:
                feedback.setdefault(defect["family"], []).append(defect)
            for failure in metrics.get("failures", []):
                family = next(
                    e["site"]["recipe_family"]
                    for e in scene["buildings"]
                    if e["id"] == failure["id"]
                )
                feedback.setdefault(family, []).append(
                    {"correction": "Fix exact runtime error: " + failure["error"]}
                )
            for entity_id, passed in metrics["entity_envelopes"].items():
                if not passed:
                    family = next(
                        e["site"]["recipe_family"]
                        for e in scene["buildings"]
                        if e["id"] == entity_id
                    )
                    feedback.setdefault(family, []).append(
                        {
                            "correction": "Restore measured envelope for "
                            + entity_id
                            + ". Remove b.ground or outlying context parts; retain exact wall plan and height."
                            + json.dumps(
                                metrics.get("envelope_errors", {}).get(entity_id, {})
                            )
                        }
                    )
            for entity_id, opened in metrics.get("canopy_open", {}).items():
                if not opened:
                    family = next(
                        e["site"]["recipe_family"]
                        for e in scene["buildings"]
                        if e["id"] == entity_id
                    )
                    feedback.setdefault(family, []).append(
                        {
                            "correction": "Canopy "
                            + entity_id
                            + " must be a thin roof on posts. Remove the solid ground-to-roof extrusion; keep open air below the roof."
                        }
                    )
            pending = set(feedback)
            if not pending:
                break
        result = {
            "execution_status": "completed",
            "accepted": bool(selected and selected["accepted"]),
            "quality_status": "accepted"
            if selected and selected["accepted"]
            else "rejected",
            "selected_render": selected["render"]
            if selected
            else last_built["render"]
            if last_built
            else None,
            "attempts": attempts,
            "recipe_pack": str(cache) if selected and selected["accepted"] else None,
            "families": len(groups),
            "budget_stop": budget_stop,
            "buildings": len(scene["buildings"]),
            "acceptance_basis": "automated style/likeness critic and deterministic geometry guards; not human acceptance",
        }
    except Exception as error:
        result = {
            "execution_status": "failed",
            "accepted": False,
            "quality_status": "unreviewed",
            "attempts": attempts,
            "selected_render": selected["render"]
            if selected
            else last_built["render"]
            if last_built
            else None,
            "failure": record_failure(run, error).model_dump(),
        }
    finally:
        provider.save()
    result["usage"] = provider.usage
    if result.get("selected_render"):
        target = (
            Path(result["selected_render"]).relative_to(run).as_posix() + "/index.html"
        )
        (run / "index.html").write_text(
            '<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url='
            + target
            + '"><a href="'
            + target
            + '">Open generated scene</a>',
            encoding="utf-8",
        )
    write_json(run / "result.json", result)
    return result
