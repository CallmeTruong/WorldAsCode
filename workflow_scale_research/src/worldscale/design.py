"""Agent-authored building designs on measured sites.

Facts are measured (site brief), look comes from a style sheet read once per
style, and the agent writes a short design script in the building kit. The
script is rendered through the evidence cameras, checked against tolerant
metric limits, reviewed by a vision critic against the reference and the style,
revised a bounded number of times, and the best attempt is kept.
"""

import json
import math
import re
from hashlib import sha256
from pathlib import Path

import numpy as np
from PIL import Image

from . import brief as site_brief_module
from . import dsm, georef, massing
from .artifacts import digest, file_hash, write_json
from .browser import bundle, capture
from .config import ROOT
from .pipeline import detail_defaults, evidence_capture, render_camera
from .provider import Provider

KIT_API = ROOT / "runtime/kit-api.md"
# The script runs only inside the sandboxed browser page, with network denied by
# CSP and request routing. These patterns keep it to building geometry.
FORBIDDEN = re.compile(
    r"\b(?:import|require|fetch|XMLHttpRequest|WebSocket|eval|Function|localStorage|Worker|"
    r"setTimeout|setInterval)\b|\b(?:document|window|globalThis|navigator)\s*[.\[]"
)
# Tolerant on purpose: a stylised design should read as the same building, not trace it.
LIMITS = {
    "mean_oblique_iou": 0.70,
    "plan_iou": 0.75,
    "height_ratio": (0.8, 1.3),
    "max_triangles": 200_000,
}
ACCEPT = {"likeness": 0.7, "style": 0.65, "detail": 0.65}


def lint(code):
    problems = []
    if not isinstance(code, str) or "export function design(" not in code:
        problems.append("Script must define `export function design(site, b, style)`.")
        return problems
    stripped = re.sub(r"//[^\n]*|/\*.*?\*/", "", code, flags=re.S).replace(
        "export function design(", "function design(", 1
    )
    found = sorted({m.strip(" .[") for m in FORBIDDEN.findall(stripped)})
    if found:
        problems.append("Not allowed in a design script: " + ", ".join(found))
    if len(code) > 30_000:
        problems.append("Script too long; use loops and kit parts.")
    return problems


def sheet(paths, out, cell=(640, 480), columns=3):
    """Tile images into one JPEG so a review costs one image, not five."""
    rows = -(-len(paths) // columns)
    canvas = Image.new("RGB", (cell[0] * columns, cell[1] * rows), "#111111")
    for i, path in enumerate(paths):
        image = Image.open(path).convert("RGB")
        image.thumbnail(cell)
        canvas.paste(
            image,
            (i % columns * cell[0] + (cell[0] - image.width) // 2,
             i // columns * cell[1] + (cell[1] - image.height) // 2),
        )
    canvas.save(out, quality=88)
    return Path(out)


def reference_sheet(evidence, out):
    folder = Path(out).parent
    crops = []
    for view in evidence["views"]:
        path = folder / ("reference-" + view["id"] + ".png")
        georef.scoped_reference(view, evidence, out_image=path)
        crops.append(path)
    return sheet(crops, out)


def detail_sheet(evidence, folder, out, rendered=False):
    """Same source-derived image rectangles for source and candidate close-ups."""
    folder, out = Path(folder), Path(out)
    crops = []
    for view in evidence["views"]:
        mask = georef.scoped_reference(view, evidence)
        yy, xx = np.nonzero(mask)
        if not len(xx):
            continue
        source_w, source_h = mask.shape[1], mask.shape[0]
        image = Image.open(folder / ("view-" + view["id"] + ".png") if rendered else view["image"]).convert("RGB")
        sx, sy = image.width / source_w, image.height / source_h
        x0, x1 = max(0, int(xx.min()) - 5), min(source_w, int(xx.max()) + 6)
        y0, y1 = max(0, int(yy.min()) - 5), min(source_h, int(yy.max()) + 6)
        mid = y0 + int((y1 - y0) * .52)
        for label, a, b in (("upper", y0, mid + 12), ("lower", mid - 12, y1)):
            path = out.parent / ("detail-" + view["id"] + "-" + label + ".jpg")
            image.crop((round(x0*sx), round(a*sy), round(x1*sx), round(b*sy))).save(path, quality=93)
            crops.append(path)
    return sheet(crops, out, cell=(720, 340), columns=2)


def style_sheet(provider, styles, run):
    """Read the style reference once; the reply is cached by image content."""
    small = []
    for i, path in enumerate(styles):
        image = Image.open(path).convert("RGB")
        image.thumbnail((1024, 1024))
        target = Path(run) / f"style-{i}.jpg"
        image.save(target, quality=88)
        small.append(target)
    prompt = (
        "These images define a visual STYLE for procedurally generated 3D buildings. Describe the "
        "style so a designer can apply it to ANY building, of any architecture, in a different "
        "city. Do not describe the specific buildings or the place shown. Return JSON {"
        '"summary": one sentence, "form": [how masses and silhouettes are treated], '
        '"detail": [density and kind of detail, what is simplified, what is emphasised], '
        '"colour": [describe relationships of saturation, value, contrast and material identity; no named colours, hex palettes or object-specific colours], '
        '"materials": [surface treatment: flat, textured, glossy], '
        '"light": {"sun": number 1-5, "sky": number 0.5-3, "exposure": number 0.6-1.4, '
        '"shadow_treatment": description, "background_treatment": description}, '
        '"exaggeration": {"ornament_scale": number 1-1.6, "saturation": number 0.8-1.6}, '
        '"avoid": [things that would break the style]}. Do not copy water, vegetation, geography or architecture from the reference. Style is transferable visual treatment, not a fixed palette. Keep every list to at most 5 short items.'
    )
    return provider.call("style-sheet", prompt, small, 1400), small


def author(provider, node, site, style, images, previous=None, feedback=None, kit_api=None):
    prompt = (
        "You design ONE building as a short JavaScript script written in a building kit. "
        "Measured facts fix where the building is and how big it is; you decide what it is made "
        "of and how it looks, in the requested style. Be inventive with parts, rhythm and "
        "ornament where the photos are vague, and stay faithful where they are clear.\n\n"
        "Preserve distinctive roof gables and facade composition before adding microdetail. "
        "Features derived from height blobs have uncertain identity: confirm gable vs dormer vs turret in photos. "
        "Use b.window for real framed panes with storey-specific pediments; use b.gable for tall wall-plane features, "
        "and vary dormers by observed scale and roof type. Do not turn all tall projections into turrets. "
        "Use physical brick/slate dimensions (surface.scale is tile size, not brick width). "
        "Avoid copying the style reference's ground/vegetation colours. "
        "No hardcoded object name, edge IDs or world coordinates for unmeasured features: select edges by semantic attributes.\n"
        + Path(kit_api or KIT_API).read_text(encoding="utf-8")
        + "\n\nSITE (measured): " + json.dumps(site)
        + "\n\nSTYLE SHEET: " + json.dumps(style)
        + "\n\nIMAGES: first, a sheet of rendered photogrammetry views of the real building "
        "(order: " + ", ".join(site["views"]) + "; blurry, shadowed and partly melted — read "
        "them for composition, storeys, window rhythm, roof character, materials). Then the "
        "style reference image(s): take treatment from them, never architecture or location."
        " A source detail sheet follows the style image(s); it shows upper/lower crops of each camera in order. "
        "Upper/lower are image regions, not ground-truth roof/facade segmentations."
    )
    if previous:
        prompt += (
            "\n\nYOUR PREVIOUS SCRIPT:\n" + previous
            + "\n\nREVIEW OF ITS RENDER (fix these; keep what worked): " + json.dumps(feedback)
            + "\nThe last image is a sheet of your previous render from the same cameras as the "
            "reference sheet, then a free view."
        )
    prompt += (
        '\n\nReturn JSON {"code": the complete script as a string, "intent": one sentence, '
        '"used_measurements": [site fields you anchored to]}.'
    )
    return provider.call(node, prompt, images, 7000)


def measure(run, evidence, site, report, browser):
    """Tolerant metric checks; they catch a wrong building, not a stylised one."""
    oblique = [v["id"] for v in evidence["views"] if not massing.is_plan_view(v)]
    plan = [v["id"] for v in evidence["views"] if massing.is_plan_view(v)]
    mean = float(np.mean([browser[v]["iou"] for v in oblique])) if oblique else None
    plan_iou = min((browser[v]["iou"] for v in plan), default=None)
    bounds = report.get("manifest", {}).get("bounds")
    height = bounds["max"][1] if bounds else None
    ratio = height / site["top_m"] if height else None
    triangles = report.get("manifest", {}).get("triangles", 0)
    checks = {
        "browser": bool(report.get("passed")),
        "outline_oblique": mean is None or mean >= LIMITS["mean_oblique_iou"],
        "outline_plan": plan_iou is None or plan_iou >= LIMITS["plan_iou"],
        "height": ratio is not None
        and LIMITS["height_ratio"][0] <= ratio <= LIMITS["height_ratio"][1],
        "triangles": triangles <= LIMITS["max_triangles"],
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "mean_oblique_iou": None if mean is None else round(mean, 4),
        "plan_iou": plan_iou,
        "height_m": None if height is None else round(height, 2),
        "height_ratio": None if ratio is None else round(ratio, 3),
        "triangles": triangles,
        "per_view_iou": {k: v["iou"] for k, v in browser.items()},
        "limits": LIMITS,
    }


def render_attempt(folder, code, site, style, evidence, kit_path=None):
    """Bundle and capture one script. Returns (metrics, error text or None)."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "design.mjs").write_text(code, encoding="utf-8")
    problems = lint(code)
    if problems:
        return None, "LINT: " + " ".join(problems)
    first = render_camera(evidence["views"][0])
    write_json(
        folder / "render-config.json",
        {"width": first["render_width"], "height": first["render_height"]},
    )
    try:
        bundle(folder, design=folder / "design.mjs", site=site, style=style, kit_path=kit_path)
        record_runtime_snapshot(folder)
    except RuntimeError as exc:
        return None, str(exc)[-1500:]
    browser = {}
    report = capture(
        folder,
        camera_override={"azimuth": 215, "elevation": 32, "method": "free review view"},
        extra=evidence_capture(evidence, folder, browser),
    )
    if report.get("runtime_error"):
        return None, "RUNTIME: " + str(report["runtime_error"])[:1500]
    metrics = measure(folder, evidence, site, report, browser)
    write_json(folder / "metrics.json", metrics)
    sheet([folder / ("view-" + v["id"] + ".png") for v in evidence["views"]] + [folder / "front.png"],
          folder / "render-sheet.jpg")
    detail_sheet(evidence, folder, folder / "detail-sheet.jpg", rendered=True)
    return metrics, None


def record_runtime_snapshot(folder):
    """Hash the exact runtime content bundled, including between-attempt edits."""
    folder = Path(folder)
    mapping = json.loads((folder / "bundle.js.map").read_text(encoding="utf-8"))
    names = {"kit.mjs", "surfaces.mjs", "roof-openings.mjs", "viewer.mjs", "semantic.mjs"}
    versions = {
        source.replace("\\", "/"): sha256(content.encode("utf-8")).hexdigest()
        for source, content in zip(mapping["sources"], mapping["sourcesContent"], strict=True)
        if Path(source).name in names and content is not None
    }
    write_json(folder / "runtime-versions.json", {
        "bundle_sha256": file_hash(folder / "bundle.js"),
        "modules": versions,
        "provenance": "Exact source content embedded by esbuild, not the current runtime files after rendering.",
    })


def critic(provider, node, site, style, metrics, images):
    prompt = (
        "You review a stylised procedural 3D building against the real building it stands for. "
        "Image 1: reference views of the real building (rendered photogrammetry; blur, shadow "
        "and melted geometry are capture artifacts, not features). Image 2: the generated "
        "building from the SAME cameras in the same order, followed by one free view. Remaining "
        "image(s): the style reference (treatment only).\n"
        "The last two images are matching source and rendered upper/lower detail crops. Inspect "
        "roof intersections, gable identity/scale, dormer embedding, window-surround relief, masonry "
        "scale and repetition. High silhouette agreement does not establish likeness. "
        "Do not reward extra ornament if its placement/type is unsupported.\n"
        "The goal is NOT a pixel match. Judge: would a person recognise it as this building, "
        "rendered in that style, with enough architectural detail?\n"
        "MEASURED SITE: " + json.dumps({k: site[k] for k in ("storeys", "eave_m", "ridge_m", "roof", "features", "tags")})
        + "\nSTYLE SHEET: " + json.dumps(style)
        + "\nMETRIC CHECKS: " + json.dumps({k: metrics[k] for k in ("checks", "mean_oblique_iou", "height_ratio", "triangles")})
        + '\nReturn JSON {"likeness": 0-1, "style": 0-1, "detail": 0-1, '
        '"checklist": [{"feature": architectural feature visible in the reference, '
        '"status": "present"|"weak"|"missing"|"wrong"}] (6-12 items), '
        '"defects": [what looks broken, floating, intersecting or implausible], '
        '"fixes": [concrete instructions phrased in kit terms, most valuable first, max 8], '
        '"keep": [what works and must not be lost]}. Score strictly; 0.7 means clearly '
        "recognisable and coherent."
    )
    return provider.call(node, prompt, images, 2200)


def candidate_rank(record):
    scores = record["scores"]
    return (record["accepted"], record["metrics_passed"], not record.get("likeness_regression", False),
            min(scores[k] / ACCEPT[k] for k in ACCEPT), scores["likeness"], sum(scores.values()))


def validated_scores(review):
    scores = {}
    for key in ACCEPT:
        value = review.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError("INVALID_CRITIC_SCORE: " + key)
        scores[key] = float(value)
    return scores


def run_design(evidence_path, styles, run, settings, max_revisions=1, max_tokens=220_000, adaptive_kit=False, max_kit_cycles=1, kit_version=None):
    run = Path(run).resolve()
    run.mkdir(parents=True, exist_ok=True)
    from .kit_evolution import copy_active_version, snapshot

    pinned_kit = run / 'kit-versions/base/kit.mjs'
    if not pinned_kit.exists():
        pinned_kit = copy_active_version(kit_version,pinned_kit.parent) if kit_version else snapshot(pinned_kit.parent)
    evidence = georef.load_evidence(evidence_path)
    if adaptive_kit and not 1 <= max_kit_cycles <= 3:
        raise ValueError("KIT_CYCLE_LIMIT_MUST_BE_1_TO_3")
    provider = Provider(settings, run, max_calls=2 + 2 * (max_revisions + 1) + (3 + 5*max_kit_cycles if adaptive_kit else 0), max_tokens=max_tokens,
                        max_seconds=3600 if adaptive_kit else 1800)

    # Facts: zero model calls, and computed once per evidence bundle and fitter version.
    key = digest([file_hash(evidence["path"]), file_hash(Path(massing.__file__)),
                  file_hash(Path(georef.__file__))])
    cached = ROOT / ".cache/facts" / (key + ".json")
    if cached.is_file():
        stored = json.loads(cached.read_text(encoding="utf-8"))
        program = massing.BuildingProgram.model_validate(stored["program"])
        fit_report = stored["fit"]
    else:
        program, fit_report = massing.fit(evidence)
        program = massing.sample_appearance(evidence, detail_defaults(program, evidence))
        write_json(cached, {"program": program.model_dump(), "fit": fit_report})
    heights_path = Path(evidence["path"]).parent / "heights.json"
    heights = dsm.load(heights_path) if heights_path.is_file() else None
    site = site_brief_module.site_brief(evidence, program, heights)
    site["views"] = [v["id"] for v in evidence["views"]]
    write_json(run / "site.json", site)
    write_json(run / "fit.json", fit_report)

    style, style_images = style_sheet(provider, styles, run)
    write_json(run / "style.json", style)
    references = reference_sheet(evidence, run / "reference-sheet.jpg")
    source_details = detail_sheet(evidence, run, run / "reference-details.jpg")
    write_json(run / "input-manifest.json", {
        "evidence_sha256": file_hash(evidence["path"]),
        "height_field_sha256": file_hash(heights_path) if heights_path.is_file() else None,
        "styles": [file_hash(p) for p in styles],
        "kit_sha256": file_hash(pinned_kit),
        "surfaces_sha256": file_hash(pinned_kit.parent / "surfaces.mjs"),
        "site_sha256": digest(site),
    })

    attempts, previous, feedback, extra_image = [], None, None, []
    for index in range(max_revisions + 1):
        folder = run / f"attempt-{index}"
        reply = author(
            provider, f"author-{index}", site, style,
            [references, *style_images, source_details, *extra_image], previous, feedback,
            kit_api=pinned_kit.parent / 'kit-api.md',
        )
        code = reply.get("code", "")
        metrics, error = render_attempt(folder, code, site, style, evidence, kit_path=pinned_kit)
        record = {"attempt": index, "intent": reply.get("intent"), "code_sha256": digest(code)}
        if error:
            # A script that does not build is repaired by the next author turn.
            record["error"] = error
            previous, feedback, extra_image = code, {"build_error": error}, []
            attempts.append(record)
            continue
        review = critic(
            provider, f"critic-{index}", site, style, metrics,
            [references, folder / "render-sheet.jpg", *style_images, source_details, folder / "detail-sheet.jpg"],
        )
        write_json(folder / "review.json", review)
        scores = validated_scores(review)
        prior_likeness = max((a["scores"]["likeness"] for a in attempts if a.get("metrics_passed")), default=0)
        likeness_regression = scores["likeness"] < prior_likeness - .030001
        record.update(
            {
                "metrics_passed": metrics["passed"],
                "mean_oblique_iou": metrics["mean_oblique_iou"],
                "scores": scores,
                "likeness_regression": likeness_regression,
                "accepted": metrics["passed"] and all(scores[k] >= v for k, v in ACCEPT.items()),
            }
        )
        record["rank"] = candidate_rank(record)
        attempts.append(record)
        if record["accepted"]:
            break
        best_so_far = max((a for a in attempts if "rank" in a), key=candidate_rank)
        regressed = likeness_regression
        previous_folder = run / f"attempt-{best_so_far['attempt']}" if regressed else folder
        previous = (previous_folder / "design.mjs").read_text(encoding="utf-8")
        feedback = {
            "scores": scores,
            "checklist": review.get("checklist"),
            "defects": review.get("defects"),
            "fixes": review.get("fixes"),
            "keep": review.get("keep"),
            "failed_metric_checks": [k for k, v in metrics["checks"].items() if not v],
            "regressed_likeness": regressed,
            "base_attempt": best_so_far["attempt"] if regressed else index,
            "revision_policy": "Preserve the best likeness; address the lowest normalized score first. A style/detail gain cannot compensate for incorrect architectural features.",
        }
        extra_image = [previous_folder / "render-sheet.jpg", previous_folder / "detail-sheet.jpg"]

    built = [a for a in attempts if "rank" in a]
    best = max(built, key=candidate_rank) if built else None
    result = {
        "accepted": bool(best and best["accepted"]),
        "acceptance_basis": "tolerant metric checks plus an automated vision critic; no human review",
        "status": "designed" if best else "no-buildable-design",
        "object_id": evidence["object_id"],
        "best_attempt": best["attempt"] if best else None,
        "attempts": attempts,
        "thresholds": {"critic": ACCEPT, "metric": LIMITS},
        "evidence_sha256": file_hash(evidence["path"]),
        "usage": {k: provider.usage[k] for k in ("calls", "input_tokens", "output_tokens", "unknown_token_reserve", "cache_hits")},
        "active_seconds": round(provider.usage.get("active_seconds", 0), 1),
    }
    write_json(run / "result.json", result)
    if adaptive_kit and best and not result["accepted"]:
        from .adaptive import evolve_design

        evolved = evolve_design(run, run / "kit-evolution", settings, max_kit_cycles, max_tokens, provider=provider)
        result["kit_evolution"] = evolved
        result["accepted"] = evolved["accepted"]
        result["usage"] = {k: provider.usage[k] for k in ("calls", "input_tokens", "output_tokens", "unknown_token_reserve", "cache_hits")}
        result["selected_render"] = evolved.get("selected_render", str(run / f"attempt-{best['attempt']}"))
        write_json(run / "result.json", result)
    return result
