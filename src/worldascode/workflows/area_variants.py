"""Reuse observed geometry and procedural recipes across editable style profiles."""

import copy
import json
import math
import shutil
from pathlib import Path

from PIL import Image, ImageDraw

from worldascode.adapters.rendering.browser import capture
from worldascode.geometry import area_look
from worldascode.storage.artifacts import digest, file_hash, write_json
from worldascode.workflows.area import build_scene, bundle_scene

# Runtime states change uniforms/material properties, never the stored geometry.
GEOMETRY_SIGNATURE = """() => {
  let hash=2166136261;
  const bytes=array=>{for(const v of new Uint8Array(array.buffer,array.byteOffset,array.byteLength)){hash^=v;hash=Math.imul(hash,16777619);}};
  worldscale.root.updateMatrixWorld(true);
  worldscale.root.traverse(o=>{if(!o.isMesh)return;
    for(const a of Object.values(o.geometry.attributes))bytes(a.array);
    if(o.geometry.index)bytes(o.geometry.index.array);
    bytes(new Float64Array(o.matrixWorld.elements));
    if(o.instanceMatrix)bytes(o.instanceMatrix.array);
  });return (hash>>>0).toString(16);
}"""


def run_area_variants(source, profiles, run, recipes_from=None):
    source, run = Path(source).resolve(), Path(run).resolve()
    if not 1 <= len(profiles) <= 6:
        raise ValueError("AREA_VARIANTS_REQUIRE_ONE_TO_SIX_STYLES")
    profiles = [area_look.resolve(p) for p in profiles]
    if len({p["name"] for p in profiles}) != len(profiles):
        raise ValueError("AREA_VARIANTS_DUPLICATE_STYLE_NAME")
    area = json.loads((source / "area.json").read_text(encoding="utf-8"))
    if not any("observed" in b for b in area["buildings"]):
        raise ValueError("AREA_VARIANTS_NEED_OBSERVED_SOURCE")
    # Compile from facts each time, not from the preceding style's transformed colours.
    variants = {}
    for i, profile in enumerate(profiles):
        styled = area_look.apply(copy.deepcopy(area), profile)
        variants[f"style-{i}"] = build_scene(styled)
    modules, recipe_receipt = {}, {}
    if recipes_from:
        from worldascode.workflows.area_style import families, validate_recipe

        prior = Path(recipes_from).resolve()
        result = json.loads((prior / "result.json").read_text(encoding="utf-8"))
        rendered = Path(result.get("selected_render") or "").resolve()
        if (
            not rendered.is_relative_to(prior)
            or not (rendered / "scene.json").is_file()
        ):
            raise ValueError("AREA_VARIANTS_RETAINED_RECIPES_REQUIRED")
        previous_scene = json.loads(
            (rendered / "scene.json").read_text(encoding="utf-8")
        )
        previous_sites = {e["id"]: e["site"] for e in previous_scene["buildings"]}
        for scene in variants.values():
            scene["style"] = {**(previous_scene.get("style") or {}), **scene["style"]}
            for entry in scene["buildings"]:
                entry["site"]["architecture"] = previous_sites.get(entry["id"], {}).get(
                    "architecture", {}
                )
            scene["requireAuthoredRecipes"] = True
            groups = families(scene)
            for family, members in groups.items():
                path = rendered / "recipes" / (family + ".mjs")
                validate_recipe(path.read_text(encoding="utf-8"), members)
                modules[family] = path
                recipe_receipt[family] = file_hash(path)
    run.mkdir(parents=True, exist_ok=False)
    write_json(run / "area.json", area)
    for family, path in list(modules.items()):
        target = run / "recipes" / (family + ".mjs")
        target.parent.mkdir(exist_ok=True)
        shutil.copy2(path, target)
        modules[family] = target
    write_json(run / "styles.json", profiles)
    write_json(
        run / "inputs.json",
        {
            "source_run": str(source),
            "area_sha256": file_hash(source / "area.json"),
            "recipes": recipe_receipt,
            "observed_facts_sha256": digest(
                [
                    {
                        k: b.get(k)
                        for k in ("id", "polygon", "height_m", "masses", "observed")
                    }
                    for b in area["buildings"]
                ]
            ),
        },
    )
    bundle_scene(run, next(iter(variants.values())), modules, variants=variants)
    measurements = {}

    def extra(page, shots):
        page.evaluate("()=>worldscale.view(215,38,.9)")
        for key, scene in variants.items():
            camera = page.evaluate("()=>worldscale.cameraState()")
            page.evaluate("k=>worldscale.setStyle(k)", key)
            after_camera = page.evaluate("()=>worldscale.cameraState()")
            camera_kept = camera["projection"] == after_camera["projection"] and all(
                math.isclose(a, b, rel_tol=0, abs_tol=1e-8)
                for key in ("position", "target", "up", "zoom")
                for a, b in zip(
                    camera[key] if isinstance(camera[key], list) else [camera[key]],
                    after_camera[key]
                    if isinstance(after_camera[key], list)
                    else [after_camera[key]],
                )
            )
            page.evaluate(
                "h=>worldscale.state({hour:h,wetness:0,wind:0})",
                scene["style"].get("hour", 13),
            )
            before = page.evaluate(GEOMETRY_SIGNATURE)
            name = key + ".png"
            page.locator("canvas").screenshot(path=str(run / name))
            shots.append(name)
            manifest = page.evaluate("()=>worldscale.manifest()")
            state = page.evaluate("()=>worldscale.state({hour:21,wetness:.8,wind:1.2})")
            page.evaluate("k=>worldscale.setStyle(k)", key)
            after_state = page.evaluate("()=>worldscale.state({})")
            after = page.evaluate(GEOMETRY_SIGNATURE)
            inspection = page.evaluate(
                "()=>({failures:worldscale.root.userData.buildFailures,ids:worldscale.root.userData.buildingIds,warnings:worldscale.root.userData.buildWarnings})"
            )
            measurements[key] = {
                "style": scene["style"]["name"],
                "camera_preserved": camera_kept,
                "state_preserved": all(
                    state[k] == after_state[k] for k in ("hour", "wetness", "wind")
                ),
                "state_keeps_geometry": before == after,
                "geometry_signature": before,
                "all_entities": set(inspection["ids"])
                == {b["id"] for b in scene["buildings"]},
                "failures": inspection["failures"],
                "warnings": inspection["warnings"],
                "triangles": manifest["triangles"],
                "performance": manifest["performance"],
            }

    def prepare(page):
        shots = []
        extra(page, shots)
        page.evaluate("k=>worldscale.setStyle(k)", next(iter(variants)))
        page.evaluate("()=>worldscale.state({hour:13,wetness:0,wind:0})")
        return shots

    report = capture(
        run,
        camera_override={"azimuth": 215, "elevation": 38, "scale": 0.9},
        prepare=prepare,
        review_only=True,
        export_geometry=False,
    )
    passed = (
        bool(report.get("passed"))
        and len(measurements) == len(variants)
        and all(
            m["camera_preserved"]
            and m["state_preserved"]
            and m["state_keeps_geometry"]
            and m["all_entities"]
            and not m["failures"]
            for m in measurements.values()
        )
    )
    if measurements:
        keys = list(measurements)
        sheet = Image.new("RGB", (550 * len(keys), 440), "#20262d")
        draw = ImageDraw.Draw(sheet)
        for i, key in enumerate(keys):
            with Image.open(run / (key + ".png")) as image:
                image.thumbnail((550, 412))
                sheet.paste(image, (i * 550, 28))
            draw.text((i * 550 + 10, 7), measurements[key]["style"], fill="white")
        sheet.save(run / "comparison.jpg", quality=92)
    result = {
        "execution_status": "completed" if passed else "failed",
        "accepted": False,
        "quality_status": "unreviewed",
        "model_calls": 0,
        "recipe_source": "retained-model-authored"
        if recipes_from
        else "builtin-observed",
        "capture_imagery_in_output": False,
        "variants": measurements,
        "runtime_error": report.get("runtime_error"),
        "note": "Style/state checks do not establish visual likeness or city-scale throughput. "
        "Synthetic facade textures are generated by code; no source image is bundled.",
    }
    write_json(run / "result.json", result)
    return result
