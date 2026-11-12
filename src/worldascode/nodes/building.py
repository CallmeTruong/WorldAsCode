"""Focused service extracted from the reconstruction workflow."""

import json
from pathlib import Path

from PIL import Image

from worldascode.config import ROOT
from worldascode.storage.artifacts import write_json

KIT_API = ROOT / "runtime/kit-api.md"


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


def author(
    provider, node, site, style, images, previous=None, feedback=None, kit_api=None
):
    from worldascode.kits.context import context

    api_path = Path(kit_api or KIT_API)
    selected = context(api_path, site, previous, feedback)
    prompt = (
        "You design ONE building as a short JavaScript script written in a building kit. "
        "Measured facts fix where the building is and how big it is; you decide what it is made "
        "of and how it looks, in the requested style. Be inventive with parts, rhythm and "
        "ornament where the photos are vague, and stay faithful where they are clear.\n\n"
        "Use SITE.observations as an evidence-led architectural plan; distinguish confirmed features from uncertain guesses. "
        "Prioritise observed massing, roof hierarchy, facade bays and material scale before microdetail. "
        "Use architecture-appropriate tools: flat-roof offices must not acquire historical gables, turrets or brick by default. "
        "Features derived from height blobs have uncertain identity: confirm gable vs dormer vs turret in photos. "
        "Use b.window for real framed panes; add pediments only when observed. Use b.gable for tall wall-plane features, "
        "and vary dormers by observed scale and roof type. Do not turn all tall projections into turrets. "
        "Use physical brick/slate dimensions (surface.scale is tile size, not brick width). "
        "Avoid copying the style reference's ground/vegetation colours. "
        "No hardcoded object name, edge IDs or world coordinates for unmeasured features: select edges by semantic attributes. "
        "Derive floor loops, bay spacing and repeated geometry from site parameters so the recipe can be tested at a second site. "
        "Keep individual silhouette-defining features distinct rather than mapping every projection to the same primitive.\n"
        + selected["text"]
        + "\nKIT DOCUMENT INDEX (request IDs only if you need omitted API): "
        + json.dumps(selected["index"])
        + "\n\nSITE (measured): "
        + json.dumps(site)
        + "\n\nSTYLE SHEET: "
        + json.dumps(style)
        + "\n\nIMAGES: first, a sheet of rendered photogrammetry views of the real building "
        "(order: "
        + ", ".join(site["views"])
        + "; blurry, shadowed and partly melted — read "
        "them for composition, storeys, window rhythm, roof character, materials). Then the "
        "style reference image(s): take treatment from them, never architecture or location."
        " A source detail sheet follows the style image(s); it shows upper/lower crops of each camera in order. "
        "Upper/lower are image regions, not ground-truth roof/facade segmentations."
    )
    if previous:
        prompt += (
            "\n\nYOUR PREVIOUS SCRIPT:\n"
            + previous
            + "\n\nREVIEW OF ITS RENDER (fix these; keep what worked): "
            + json.dumps(feedback)
            + "\nThe last image is a sheet of your previous render from the same cameras as the "
            "reference sheet, then a free view."
        )
    prompt += (
        '\n\nReturn JSON {"code": the complete script as a string, "intent": one sentence, '
        '"used_measurements": [site fields you anchored to]}.'
    )
    if hasattr(provider, "run"):
        write_json(
            provider.run / "kit-context" / f"{node}.json",
            {k: v for k, v in selected.items() if k != "text"},
        )
    reply = provider.call(
        node,
        prompt
        + '\nIf a required API is missing from this context, return {"request_kit_docs":[document IDs]} instead of guessing. One additional retrieval turn is allowed.',
        images,
        7000,
    )
    if reply.get("request_kit_docs"):
        requested = reply["request_kit_docs"]
        if (
            not isinstance(requested, list)
            or len(requested) > 3
            or not all(isinstance(k, str) for k in requested)
        ):
            raise ValueError("KIT_DOC_REQUEST_LIMIT")
        extra = context(api_path, site, previous, feedback, requested=requested)
        if hasattr(provider, "run"):
            write_json(
                provider.run / "kit-context" / f"{node}-retrieval.json",
                {k: v for k, v in extra.items() if k != "text"},
            )
        expanded = prompt.replace(selected["text"], extra["text"], 1)
        reply = provider.call(
            node + "-kit-docs",
            expanded
            + "\nRequested API is included above. Return the complete code now; no more retrieval turns.",
            images,
            7000,
        )
    if "code" not in reply:
        raise ValueError("KIT_AUTHOR_DID_NOT_RETURN_CODE")
    return reply


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
        "Judge the actual architecture: gables, brick, dormers, pediments and towers are not requirements for buildings that do not have them. "
        "Kit window surrounds, local roof openings and hollow chimneys already exist; distinguish poor use from a missing capability. "
        "Request observable output corrections rather than assuming an API is absent.\n"
        "The goal is NOT a pixel match. Judge: would a person recognise it as this building, "
        "rendered in that style, with enough architectural detail?\n"
        "MEASURED SITE: "
        + json.dumps(
            {
                k: site[k]
                for k in ("storeys", "eave_m", "ridge_m", "roof", "features", "tags")
            }
        )
        + "\nSTYLE SHEET: "
        + json.dumps(style)
        + "\nMETRIC CHECKS: "
        + json.dumps(
            {
                k: metrics[k]
                for k in ("checks", "mean_oblique_iou", "height_ratio", "triangles")
            }
        )
        + '\nReturn JSON {"likeness": 0-1, "style": 0-1, "detail": 0-1, '
        '"checklist": [{"feature": architectural feature visible in the reference, '
        '"status": "present"|"weak"|"missing"|"wrong"}] (6-12 items), '
        '"defects": [what looks broken, floating, intersecting or implausible], '
        '"fixes": [concrete instructions phrased in kit terms, most valuable first, max 8], '
        '"keep": [what works and must not be lost], '
        '"component_reviews": [{"component":"roof|facade|materials|attachments", "confidence":0-1, "defect":string, "correction":string}]}. Score strictly; 0.7 means clearly '
        "recognisable and coherent."
    )
    return provider.call(node, prompt, images, 2200)
