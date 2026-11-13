"""Area observation, addressed critique, source tools and scoped local code repair."""

import json
import re
import shutil
from pathlib import Path

from playwright.sync_api import Error as BrowserError

from worldascode.adapters.geospatial.inspection import EvidenceTools, label_evidence
from worldascode.adapters.llm.transport import Provider
from worldascode.adapters.rendering.browser import render_region
from worldascode.config import ACCEPT, paths
from worldascode.contracts.execution import record_failure
from worldascode.contracts.region import (
    Defect,
    Region,
    validate_feedback,
    validate_request,
)
from worldascode.evidence.region_focus import union_bounds
from worldascode.evidence.region_selection import (
    evidence_ledger,
    identity_supported,
    select_evidence,
    usable,
)
from worldascode.kits import packs
from worldascode.kits.code import analyze_source
from worldascode.kits.context import context
from worldascode.nodes.building import style_sheet
from worldascode.quality.evaluation import validated_scores
from worldascode.storage.artifacts import digest, file_hash, write_json
from worldascode.workflows.objects import HOST_API, develop_pack
from worldascode.workflows.region_massing import (
    BuildingDetails,
    baseline_scripts,
    compile_changes,
)


def apply_changes(scripts, changes, writable):
    if not isinstance(changes, list) or not changes:
        raise ValueError("ENTITY_CHANGES_REQUIRED")
    ids = [c.get("entity_id") for c in changes]
    if len(set(ids)) != len(ids) or not set(ids) <= set(writable):
        raise ValueError("ENTITY_CHANGE_OUTSIDE_WRITABLE_SET_OR_DUPLICATE")
    if any(
        not isinstance(c.get("code"), str)
        or not c["code"].strip()
        or len(c["code"]) > 64000
        for c in changes
    ):
        raise ValueError("INVALID_ENTITY_SCRIPT")
    return {**scripts, **{c["entity_id"]: c["code"] for c in changes}}


def _prompt(instruction, data):
    return instruction + "\nDATA:\n" + json.dumps(data, ensure_ascii=False)


def component_context(components, defects=(), limit=40):
    """Progressive disclosure; the full host index remains in metrics.json."""
    required = {d.component_id for d in defects if d.component_id}
    ordered = sorted(
        components,
        key=lambda k: (
            k not in required,
            components[k].get("kind")
            not in {"walls", "roof", "curtainWall", "volume", "dormer"},
            k,
        ),
    )
    selected = ordered[: max(limit, len(required))]
    return {k: components[k] for k in selected}


def evidence_context(records):
    result = []
    for e in records:
        q = e.get("quality", {})
        result.append(
            {
                "id": e["id"],
                "request": e["request"],
                "image_sha256": e.get("image_sha256"),
                "quality": {
                    **{
                        k: q.get(k)
                        for k in [
                            "usable",
                            "tiles_complete",
                            "likely_occluded",
                            "warning",
                        ]
                    },
                    "entity_visibility": {
                        i: {
                            "sampled": v.get("sampled", 0),
                            "matched": v.get("matched", 0),
                        }
                        for i, v in q.get("entity_visibility", {}).items()
                    },
                },
                "entity_screens": {
                    i: v.get("screen")
                    for i, v in e.get("projected_entities", {}).items()
                },
                "uncertainty": e.get("uncertainty"),
                "source_kind": e.get("source_kind", "photogrammetry"),
                "surface_id": e.get("surface_id"),
                "captured_at": e.get("captured_at"),
                "camera_calibrated": bool(e.get("camera")),
                "identity_binding": q.get("identity_binding"),
            }
        )
    return result


def _overview(region, heading, pitch=-35):
    boxes = [e.world_bounds() for e in region.entities]
    return {
        "entity_ids": [e.id for e in region.entities],
        "purpose": "Regional overview: relationships and complete source context",
        "roi": {
            "min": [min(b.min[i] for b in boxes) for i in range(3)],
            "max": [max(b.max[i] for b in boxes) for i in range(3)],
        },
        "heading": heading,
        "pitch": pitch,
        "mode": "context",
    }


def run_region(
    region,
    run,
    settings,
    styles=(),
    max_rounds=2,
    max_tokens=220000,
    max_captures=12,
    max_pack_cycles=1,
    tools=None,
    extra_packs=(),
    initial_evidence=(),
    max_cell_span=80,
    initial_scripts=None,
    initial_observation=None,
    initial_building_plans=None,
    massing_evidence=None,
    reference_photos=None,
):
    region = region if isinstance(region, Region) else Region.model_validate(region)
    massing_report = {}
    if massing_evidence:
        if initial_scripts:
            raise ValueError(
                "MASSING_FIT_REQUIRES_NEW_DESIGNS; do not reuse scripts across a geometry change"
            )
        from worldascode.evidence.region_massing import fit_region_massing

        region, massing_report = fit_region_massing(region, massing_evidence)
    if len(region.entities) > 5:
        raise ValueError(
            "REGION_TOO_MANY_FOCUS_TARGETS; run region-plan to split into cells of at most five entities"
        )
    if not 20 <= max_cell_span <= 300:
        raise ValueError("FOCUS_CELL_SPAN_INVALID")
    bounds = union_bounds(region.entities)
    if (
        len(region.entities) > 1
        and max(bounds.max[i] - bounds.min[i] for i in [0, 2]) > max_cell_span
    ):
        raise ValueError(
            "REGION_FOCUS_TOO_WIDE; run region-plan to keep each job close to at most five nearby entities"
        )
    if (
        not 0 <= max_rounds <= 6
        or not 2 <= max_captures <= 24
        or not 0 <= max_pack_cycles <= 3
    ):
        raise ValueError("REGION_WORKFLOW_LIMIT_INVALID")
    run = Path(run).resolve()
    run.mkdir(parents=True, exist_ok=False)
    provider = Provider(
        settings,
        run,
        max_calls=6 + 5 * (max_rounds + 1) + 3 * max_pack_cycles,
        max_tokens=max_tokens,
        max_seconds=3600,
    )
    tools = tools or EvidenceTools(
        region, paths().cache_dir / "region-evidence", max_captures=max_captures
    )
    write_json(run / "region.json", region.model_dump(mode="json"))
    write_json(run / "massing-fit.json", massing_report)
    write_json(
        run / "initial-state.json",
        {
            "script_hashes": {i: digest(c) for i, c in (initial_scripts or {}).items()},
            "observation_sha256": digest(initial_observation)
            if initial_observation
            else None,
            "evidence_ids": [e.get("id") for e in initial_evidence],
        },
    )
    evidence = []
    events = []
    attempts = []
    scripts = {}
    components = {}
    defects = []
    best = None
    last_built = None
    activated = []
    cycles = 0
    catalog = packs.discover(extra_packs)
    selected = []
    writable = set(region.index())
    diagnosis = {}
    active_revision = None
    baseline, building_plans = baseline_scripts(region)
    building_plans.update(initial_building_plans or {})
    write_json(run / "building-details.json", building_plans)
    capture_requests = set()

    def pin_evidence(record, imported=False):
        from worldascode.evidence.georeference import Frame

        if not re.fullmatch(r"[a-zA-Z0-9-]{1,80}", record.get("id", "")):
            raise ValueError("INVALID_EVIDENCE_ID")
        expected = Frame(
            region.origin.longitude,
            region.origin.latitude,
            region.origin.ground_height_m,
        ).describe()
        if imported and record.get("frame") != expected:
            raise ValueError("EVIDENCE_REGION_FRAME_MISMATCH")
        validate_request(region, record["request"], components)
        actual = file_hash(record["image"])
        if record.get("image_sha256", actual) != actual:
            raise ValueError("EVIDENCE_SOURCE_HASH_MISMATCH")
        if record["id"] in {e["id"] for e in evidence}:
            return
        dest = run / "evidence" / record["id"]
        dest.mkdir(parents=True)
        shutil.copy2(record["image"], dest / "source.png")
        record = label_evidence(
            {**record, "image": str(dest / "source.png"), "image_sha256": actual},
            region,
            dest,
        )
        write_json(dest / "evidence.json", record)
        evidence.append(record)

    def source_views(requests, allowed=None):
        if not isinstance(requests, list) or len(requests) > 3:
            raise ValueError("EVIDENCE_TOOL_REQUEST_LIMIT")
        for request in requests:
            try:
                q = validate_request(region, request, components)
                if q.component_id and q.revision != active_revision:
                    raise ValueError("STALE_COMPONENT_EVIDENCE_REQUEST")
                if allowed is not None and not set(q.entity_ids) <= set(allowed):
                    raise ValueError("EVIDENCE_TOOL_OUTSIDE_DEFECT_SCOPE")
                # A different description/revision is not a new source pose.
                signature = digest(
                    {
                        k: v
                        for k, v in q.model_dump(mode="json").items()
                        if k not in {"purpose", "revision", "component_id"}
                    }
                )
                if signature in capture_requests:
                    raise ValueError(
                        "SOURCE_POSE_ALREADY_REQUESTED; choose a different pose or supply an independent photo"
                    )
                capture_requests.add(signature)
                record = tools.capture(q.model_dump(mode="json"), components)
                pin_evidence(record)
                events.append(
                    {
                        "tool": "source_view",
                        "ok": True,
                        "evidence_id": record["id"],
                        "request": q.model_dump(mode="json"),
                    }
                )
            except (ValueError, RuntimeError, TimeoutError, BrowserError) as error:
                events.append(
                    {
                        "tool": "source_view",
                        "ok": False,
                        "request": request,
                        "error": str(error),
                    }
                )
        write_json(run / "tool-events.json", events)
        # Release the source city scene before launching another renderer/model stage.
        # Source images are pinned; keeping both WebGL worlds alive can exhaust RAM.
        tools.close()

    def evidence_info():
        return evidence_context(evidence)

    def images():
        return [Path(e.get("labeled_image", e["image"])) for e in chosen_evidence()]

    def chosen_evidence():
        selected_views = select_evidence(evidence, writable or region.index())
        write_json(
            run / "evidence-selection.json",
            evidence_ledger(region, evidence, selected_views),
        )
        return selected_views

    def image_order():
        return [e["id"] for e in chosen_evidence()]

    try:
        baseline_metrics, baseline_error = render_region(
            run / "baseline", baseline, region, {}, [], []
        )
        write_json(
            run / "baseline.json",
            {
                "metrics": baseline_metrics,
                "error": baseline_error,
                "appearance": "unobserved; non-building entities are bounds proxies",
                "accepted": False,
            },
        )
        if baseline_metrics:
            last_built = {
                "attempt": "baseline",
                "render": str(run / "baseline"),
                "metrics": baseline_metrics,
                "evaluation": "unreviewed",
                "accepted": False,
                "script_hashes": {i: digest(c) for i, c in baseline.items()},
            }
        if initial_evidence:
            for record in initial_evidence:
                pin_evidence(record, imported=True)
        if reference_photos:
            from worldascode.evidence.region_photos import load_region_photos

            for record in load_region_photos(reference_photos, region):
                pin_evidence(record, imported=True)
        if not initial_evidence and not all(
            any(identity_supported(e, entity.id) for e in evidence)
            for entity in region.entities
        ):
            initial = [_overview(region, h) for h in [35, 125, 215, 305]] + [
                _overview(region, 0, -85)
            ]
            for start in range(0, min(len(initial), max_captures), 3):
                source_views(initial[start : min(start + 3, max_captures)])
        if not chosen_evidence():
            # Retry with two higher poses before spending tokens on an unseen scene.
            source_views([_overview(region, h, -65) for h in [80, 260]])
        if not chosen_evidence():
            raise RuntimeError(
                "NO_USABLE_REGION_SOURCE_EVIDENCE; baseline retained. Supply clearer calibrated views; inspect evidence-selection.json and tool-events.json"
            )
        observer = initial_observation or provider.call(
            "region-observer",
            _prompt(
                "Observe the whole region. Entity IDs, local facts, anchors and world bounds are authoritative addresses. Source images are in the evidence manifest order. "
                "Only registered entities are generation targets; other source objects supply context. Select pack parts needed for these targets, not every visible tree or car. Yellow source labels are projections of registry priors, not semantic segmentation or a guarantee that the target is unoccluded. "
                "Never confirm identity/material from whatever lies inside a projected box. Check quality.entity_visibility matched samples. Without consistent samples, mark identity unresolved and prefer a top-down or less occluded source pose, rather than describing the foreground neighbor as this entity. "
                "A depth match only establishes a surface inside a prior volume, NOT the semantic identity of a post box/phone/tree. Distinguish OSM-tag identity from visually confirmed identity; tiny street objects can be absent from photogrammetry even with matched ground/canopy samples. "
                "Interpret material identity and roof/facade relationships; do not treat fitted roof labels or baked shadows as measured architecture. "
                "Uncalibrated photos are explicitly user-bound to a named entity/surface; describe visible appearance, but never infer metric geometry or camera alignment from them. Different dates may explain conflicting appearance. "
                "Return {observations:[{entity_id,confirmed,uncertain}],parts:[existing catalog names],evidence_requests:[requests]}. "
                "Request at most two targeted source views when a specific ROI is unresolved. Request schema: "
                + json.dumps(validate_request.__annotations__)
                + " entity_ids, purpose, roi:{min:[x,y,z],max:[x,y,z]} in REGION coordinates, optional component_id, heading degrees, pitch negative degrees, range_m, mode context/detail.",
                {
                    "region": region.model_dump(mode="json"),
                    "world_bounds": {
                        e.id: e.world_bounds().model_dump() for e in region.entities
                    },
                    "catalog": [
                        {k: p.get(k) for k in ["id", "summary", "parts", "kinds"]}
                        for p in catalog
                    ],
                    "evidence": evidence_info(),
                    "source_image_order": image_order(),
                },
            ),
            images(),
            2600,
        )
        write_json(run / "observation.json", observer)
        requested = observer.get("parts", [])
        if not isinstance(requested, list) or not set(requested) <= set(
            packs.part_names(catalog)
        ):
            raise ValueError("REGION_OBSERVER_UNKNOWN_PACK_PART")
        selected = packs.select(catalog, requested)
        if not initial_observation:
            source_views(observer.get("evidence_requests", []))
        style, style_images = (
            style_sheet(provider, styles, run)
            if styles
            else (
                {
                    "summary": "Preserve source material identity with clear detailed architectural surfaces."
                },
                [],
            )
        )
        write_json(run / "style.json", style)
        for iteration in range(max_rounds + 1):
            if iteration:
                evidence_defects = [d for d in defects if d.category == "evidence"]
                source_views(
                    [
                        d.view_request.model_dump(mode="json")
                        if d.view_request
                        else {
                            "entity_ids": d.entity_ids,
                            "component_id": d.component_id,
                            "revision": active_revision,
                            "purpose": d.correction,
                            "roi": d.roi.model_dump(mode="json"),
                            "heading": 215 if iteration % 2 else 125,
                            "pitch": -70,
                            "mode": "detail",
                        }
                        for d in evidence_defects[:2]
                    ],
                    writable,
                )
                capability = [d for d in defects if d.category == "capability"]
                if capability and cycles < max_pack_cycles:
                    brief = {
                        "kind": "region_component",
                        "seed": region.seed,
                        "description": "Reusable capability needed in addressed scene defects: "
                        + json.dumps([d.model_dump(mode="json") for d in capability]),
                        "required_checks": [],
                    }
                    candidate, diagnosis = develop_pack(
                        provider,
                        run,
                        brief,
                        catalog,
                        {
                            "defects": [d.model_dump(mode="json") for d in capability],
                            "components": components,
                        },
                        cycles,
                        evidence_images=[
                            Path(e.get("labeled_image", e["image"]))
                            for e in select_evidence(
                                evidence,
                                {i for d in capability for i in d.entity_ids},
                                limit=3,
                            )
                            if set(e["request"]["entity_ids"])
                            & {i for d in capability for i in d.entity_ids}
                        ][-3:],
                    )
                    cycles += 1
                    if candidate:
                        catalog.append(candidate)
                        activated.append(candidate)
                        selected.append(candidate)
            api = context(
                paths().runtime_dir / "kit-api.md",
                site={"entities": [e.site() for e in region.entities]},
                previous="\n".join(scripts.get(i, "") for i in writable),
                feedback=[d.model_dump(mode="json") for d in defects],
                max_chars=20000,
            )
            data = {
                "region": region.model_dump(mode="json"),
                "world_bounds": {
                    e.id: e.world_bounds().model_dump() for e in region.entities
                },
                "observations": observer,
                "style": style,
                "writable_entity_ids": sorted(writable),
                "base_revision": active_revision,
                "previous_scripts": {i: scripts[i] for i in writable if i in scripts},
                "building_details_schema": BuildingDetails.model_json_schema(),
                "building_plans": {
                    i: p for i, p in building_plans.items() if i in writable
                },
                "baseline_scripts": {
                    i: c for i, c in baseline.items() if i in writable
                },
                "components": component_context(components, defects),
                "component_index_omitted_count": max(
                    0, len(components) - len(component_context(components, defects))
                ),
                "defects": [d.model_dump(mode="json") for d in defects],
                "evidence": evidence_info(),
                "source_image_order": image_order(),
                "tool_events": events[-5:],
                "capability_diagnosis": diagnosis,
                "kit_document_index": api["index"],
            }
            instruction = "You author coordinated 3D objects for ONE region, using separate local entity recipes. Return {changes:[{entity_id,code}],tool_requests:[optional source-view requests]}. "
            instruction += "Each code exports function design(site,b,style). site is the ENTITY LOCAL site: X east,Y up,Z south before its anchor/yaw. NEVER put regional or geographic coordinates into local b.at calls. Preserve site footprint/height. Do not modify other entities or export region composition glue. "
            instruction += "BUILDINGS use changes:[{entity_id,building:{bounded parameters from building_details_schema},detail_code:optional string}]. The host has ALREADY compiled the footprint, wall height and roof shell. Never return code for a building. building sets materials, bay/window proportions and a supported roof_form; it cannot change coordinates, heights or storeys. Optional detail_code exports function design(site,b,style) and ONLY adds attached details/pack calls; walls,roof,roofPlanes are unavailable there. Use __shell_wall,__shell_roof,__shell_trim,__shell_glass material IDs for details or declare new IDs. Provide evidence_ids for observations and uncertainty for every estimate. Non-buildings retain {entity_id,code}. Baseline props are bounds proxies, not source-confirmed designs. "
            instruction += "Changes may touch ONLY writable_entity_ids; initially provide every entity. Use feedback component IDs and world ROIs to identify the exact part, then transform into that entity local frame to edit. Do not fix a neighboring object because it looks similar. "
            instruction += "Source views are evidence of appearance, not intrinsic colors: distinguish baked lighting and clipping artifacts. There is no fixed palette. Material arguments glass/frame/louvers must be declared material IDs, not booleans. Prefer measured/observed roof hierarchy over generic fitted roof-form labels. "
            instruction += "When OSM provides a small object's type and position but source appearance is unresolved, create a plausible detailed estimate and label the uncertain features; do not block the entire cell on unobservable tiny texture details. Preserve measured outlines and do not present estimated appearance as source-confirmed. "
            instruction += "If evidence is insufficient, return only tool_requests (max 2) with entity_ids,purpose,roi WORLD min/max,heading,pitch,mode and optional component_id. A component request MUST include revision equal to base_revision; component names are revision-bound. Host executes them and resumes you. No arbitrary URLs, JS evaluation or provider keys. "
            instruction += (
                HOST_API
                + "\nBUILDING API:\n"
                + api["text"]
                + "\nSELECTED PACK API:\n"
                + packs.api_text(selected)
            )
            reply = {
                "changes": [
                    {"entity_id": i, "code": c}
                    for i, c in (initial_scripts or {}).items()
                ]
            }
            for turn in range(0 if iteration == 0 and initial_scripts else 3):
                data["tool_turns_remaining"] = 2 - turn
                turn_instruction = instruction
                if turn == 2:
                    turn_instruction += "\nSource tool turns are exhausted. Return changes now using measured geometry and observed common features; clearly record uncertain surface detail. If identity or basic geometry truly cannot be established, return {needs_evidence:reason} rather than issuing more tool requests."
                reply = provider.call(
                    f"region-author-{iteration}" + (f"-tools-{turn}" if turn else ""),
                    _prompt(turn_instruction, data),
                    [*images(), *style_images],
                    11000,
                )
                if reply.get("needs_evidence"):
                    raise RuntimeError(
                        "NEEDS_EVIDENCE: " + str(reply["needs_evidence"])
                    )
                if not reply.get("tool_requests"):
                    break
                if turn == 2:
                    raise ValueError("REGION_AUTHOR_TOOL_ROUND_LIMIT")
                source_views(reply["tool_requests"], writable)
                data = {
                    **data,
                    "evidence": evidence_info(),
                    "source_image_order": image_order(),
                    "tool_events": events[-5:],
                }
            try:
                if iteration == 0 and initial_scripts:
                    scripts = apply_changes(scripts, reply.get("changes"), writable)
                else:
                    compiled, next_plans = compile_changes(
                        region, reply.get("changes"), building_plans, image_order()
                    )
                    scripts = apply_changes(scripts, compiled, writable)
                    building_plans = next_plans
            except ValueError as invalid:
                reply = provider.call(
                    f"region-author-{iteration}-contract-repair",
                    _prompt(
                        instruction,
                        {
                            **data,
                            "invalid_reply": reply,
                            "validation_error": str(invalid),
                            "instruction": "Return only valid changes inside the writable set, without additional tool requests.",
                        },
                    ),
                    [*images(), *style_images],
                    11000,
                )
                compiled, next_plans = compile_changes(
                    region, reply.get("changes"), building_plans, image_order()
                )
                scripts = apply_changes(scripts, compiled, writable)
                building_plans = next_plans
            if set(scripts) != set(region.index()):
                raise ValueError("REGION_INITIAL_DESIGNS_INCOMPLETE")
            # Select additional pack APIs actually referenced, without loading all code.
            try:
                calls = set().union(
                    *(
                        set(analyze_source(code)["api_methods"])
                        for code in scripts.values()
                    )
                )
            except ValueError:
                # Renderer returns an entity-addressed syntax diagnostic for repair.
                calls = set(packs.part_names(selected))
            selected = packs.select(
                catalog, list(calls & set(packs.part_names(catalog)))
            )
            revision = digest(
                {
                    "scripts": scripts,
                    "packs": [(p["id"], p["sha256"]) for p in selected],
                }
            )
            active_revision = revision
            folder = run / f"attempt-{iteration}"
            write_json(run / "building-details.json", building_plans)
            metrics, error = render_region(
                folder, scripts, region, style, evidence, selected
            )
            write_json(folder / "building-details.json", building_plans)
            if metrics:
                last_built = {
                    "attempt": iteration,
                    "render": str(folder),
                    "revision": revision,
                    "metrics": metrics,
                    "evaluation": "unreviewed",
                    "accepted": False,
                    "script_hashes": {i: digest(c) for i, c in scripts.items()},
                }
                write_json(folder / "evaluation-pending.json", last_built)
            review = {}
            scores = {k: 0 for k in ACCEPT}
            defects = []
            if error:
                # A build failure has no image to critique. Address the actual failing caller.
                ids = [i for i in writable if f"ENTITY {i}:" in error] or sorted(
                    writable
                )
                for n, i in enumerate(ids):
                    defects.append(
                        Defect(
                            id=f"build-{iteration}-{n}",
                            entity_ids=[i],
                            roi=region.index()[i].world_bounds(),
                            category="code",
                            description=error,
                            correction="Repair the exact API or syntax error in this entity; use documented argument types.",
                            confidence=1,
                            evidence_ids=[],
                        )
                    )
            else:
                components = metrics["components"]
                paired = (
                    json.loads(
                        (folder / "aligned-evidence.json").read_text(encoding="utf-8")
                    )
                    if (folder / "aligned-evidence.json").exists()
                    else []
                )
                review_images = [folder / "front.png"]
                mapping = [{"image": 0, "type": "region overview"}]
                review_sources = select_evidence(evidence, region.index(), limit=6)
                selected_ids = {e["id"] for e in review_sources}
                for pair in [p for p in paired if p["evidence_id"] in selected_ids]:
                    for key in ["source_labeled", "output_labeled"]:
                        mapping.append(
                            {
                                "image": len(review_images),
                                "type": key,
                                "evidence_id": pair["evidence_id"],
                                "entity_ids": pair["entity_ids"],
                            }
                        )
                        review_images.append(Path(pair[key]))
                for source in review_sources:
                    if not source.get("camera"):
                        mapping.append(
                            {
                                "image": len(review_images),
                                "type": "uncalibrated reference photo",
                                "evidence_id": source["id"],
                                "entity_ids": source["request"]["entity_ids"],
                                "surface_id": source.get("surface_id"),
                                "camera_aligned": False,
                            }
                        )
                        review_images.append(Path(source["image"]))
                critic_metrics = {
                    **metrics,
                    "components": component_context(components, defects),
                    "component_index_omitted_count": max(0, len(components) - 40),
                    "entities": {
                        i: {
                            "bounds": v["bounds"],
                            "component_count": len(v.get("component_ids", [])),
                        }
                        for i, v in metrics["entities"].items()
                    },
                }
                critic_data = {
                    "region": region.model_dump(mode="json"),
                    "revision": revision,
                    "metrics": critic_metrics,
                    "evidence": evidence_context(
                        [e for e in evidence if e["id"] in selected_ids]
                    ),
                    "image_manifest": mapping,
                    "style": style,
                    "building_plans": building_plans,
                }
                critic_instruction = "Review the COMPLETE region and matching source/output camera pairs. Yellow boxes/labels identify registry entity projections, not surveyed source bounds. Inspect shape, roof hierarchy, attachment, road/object relationships, material identity and requested style. "
                critic_instruction += "Evaluate registered entities only; unregistered surrounding source buildings/roads are context, not missing targets. Yellow boxes use expected registry projections rather than current generated geometry. A box can contain an occluder; use aligned views and world bounds to verify identity. "
                critic_instruction += "Reference photos marked uncalibrated are user-bound to an entity/surface, not camera pairs; compare architectural appearance only, never pixel alignment or geometric measurements. Account for different capture dates. A missing source detail is uncertainty, not proof that the generated feature is wrong. "
                critic_instruction += "Return {revision:exact supplied revision,likeness:0..1,style:0..1,detail:0..1,defects:[{id,entity_ids,component_id:optional,roi:{min:[x,y,z],max:[x,y,z]},category:evidence|geometry|material|style|capability|code,description,correction,evidence_ids,confidence:0..1}]}. "
                critic_instruction += "Use registry entity IDs and exact metrics.components keys. Every ROI is WORLD metres in the region frame and overlaps the addressed entity or its actual addressed component. Never use image-left/right alone to locate a defect. Cite only supplied evidence IDs. If source is occluded or blurry, request evidence instead of inventing geometry. API misuse is code, not a missing pack. Capability defects must identify a reusable operation actually absent from selected API. Defects must cover failed checks; give concrete measurable corrections. Scores do not override geometry gates."
                critic_instruction += " For an evidence defect you may include view_request:{entity_ids,purpose,roi,heading,pitch,mode,component_id?,revision?}. Choose a less occluded heading from the existing evidence, high oblique or overhead for roofs and a suitable oblique facade angle for facade defects. The request must target a subset of the defect entities. A component request must repeat the exact current revision. Do not use low street-level cameras through known occluders or request a cropped whole-object view."
                review = provider.call(
                    f"region-critic-{iteration}",
                    _prompt(critic_instruction, critic_data),
                    [*review_images, *style_images],
                    3600,
                )
                try:
                    defects = validate_feedback(
                        region,
                        review,
                        revision,
                        components,
                        [e["id"] for e in evidence if usable(e)],
                    )
                except ValueError as invalid:
                    review = provider.call(
                        f"region-critic-repair-{iteration}",
                        _prompt(
                            critic_instruction,
                            {
                                **critic_data,
                                "invalid_review": review,
                                "validation_error": str(invalid),
                            },
                        ),
                        [*review_images, *style_images],
                        3600,
                    )
                    defects = validate_feedback(
                        region,
                        review,
                        revision,
                        components,
                        [e["id"] for e in evidence if usable(e)],
                    )
                scores = validated_scores(review)
            coverage = all(
                any(identity_supported(e, entity.id) for e in evidence)
                for entity in region.entities
            )
            if metrics:
                for number, issue in enumerate(
                    metrics.get("structure", {}).get("issues", [])
                ):
                    component_id = issue.get("part", issue.get("id"))
                    component = components.get(component_id)
                    if component and not any(
                        d.component_id == component_id for d in defects
                    ):
                        defects.append(
                            Defect(
                                id=f"structure-{iteration}-{number}",
                                entity_ids=[component["entity_id"]],
                                component_id=component_id,
                                roi=component["bounds"],
                                category="geometry",
                                description=json.dumps(issue),
                                correction="Fix this exact component attachment or placement. Convert its world bounds through the entity anchor/yaw into local coordinates.",
                                evidence_ids=[],
                                confidence=1,
                            )
                        )
                for entity in region.entities:
                    verified = any(identity_supported(e, entity.id) for e in evidence)
                    if not verified and not any(
                        entity.id in d.entity_ids and d.category == "evidence"
                        for d in defects
                    ):
                        defects.append(
                            Defect(
                                id="source-unverified-" + digest(entity.id)[:12],
                                entity_ids=[entity.id],
                                roi=entity.world_bounds(),
                                category="evidence",
                                description="No usable source has a consistent spatial sample or explicit user photo binding for this entity.",
                                correction="Obtain an unobstructed overhead or high oblique view and verify source identity; do not copy foreground neighbors.",
                                evidence_ids=[],
                                confidence=1,
                            )
                        )
            accepted = bool(
                metrics
                and metrics["passed"]
                and coverage
                and not defects
                and all(scores[k] >= v for k, v in ACCEPT.items())
            )
            record = {
                "attempt": iteration,
                "revision": revision,
                "script_hashes": {i: digest(c) for i, c in scripts.items()},
                "writable_entity_ids": sorted(writable),
                "render": str(folder),
                "metrics": metrics,
                "error": error,
                "review": review,
                "scores": scores,
                "defects": [d.model_dump(mode="json") for d in defects],
                "source_coverage": coverage,
                "selected_packs": [
                    {k: p[k] for k in ["id", "sha256", "folder", "parts"]}
                    for p in selected
                ],
                "accepted": accepted,
            }
            attempts.append(record)
            write_json(folder / "review.json", record)
            (folder / "evaluation-pending.json").unlink(missing_ok=True)
            if metrics:
                rank = (accepted, metrics["passed"], min(scores.values()))
                if best is None or rank > best[0]:
                    best = (rank, record)
            if accepted:
                break
            writable = {i for d in defects for i in d.entity_ids}
            if not writable:
                # Never rewrite all neighbors to compensate for an unaddressed failure.
                events.append(
                    {
                        "tool": "review",
                        "ok": False,
                        "error": "UNADDRESSED_FAILED_GATE_OR_SCORE; no arbitrary entity rewrite",
                    }
                )
                break
        result = {
            "status": "region-complete",
            "execution_status": "completed" if best else "failed",
            "accepted": bool(best and best[1]["accepted"]),
            "quality_status": "accepted"
            if best and best[1]["accepted"]
            else "rejected"
            if best
            else "unreviewed",
            "selection_status": "retained" if best else "none",
            "best_attempt": best[1]["attempt"] if best else None,
            "selected_render": best[1]["render"] if best else None,
            "attempts": attempts,
            "activated_packs": [
                {k: p[k] for k in ["id", "sha256", "folder", "parts"]}
                for p in activated
            ],
            "evidence_ids": [e["id"] for e in evidence],
            "tool_events": events,
            "acceptance_basis": "automated regional critic, addressed defects and deterministic guards; not human acceptance",
        }
    except Exception as error:
        result = {
            "status": "region-interrupted",
            "execution_status": "failed",
            "accepted": False,
            "quality_status": "rejected" if best else "unreviewed",
            "selection_status": "retained" if best else "none",
            "best_attempt": best[1]["attempt"] if best else None,
            "selected_render": best[1]["render"] if best else None,
            "attempts": attempts,
            "activated_packs": [
                {k: p[k] for k in ["id", "sha256", "folder", "parts"]}
                for p in activated
            ],
            "failure": record_failure(run, error).model_dump(),
            "tool_events": events,
        }
        if not best and last_built:
            result.update(
                selection_status="retained",
                best_attempt=last_built["attempt"],
                selected_render=last_built["render"],
                quality_status="unreviewed",
                attempts=[*attempts, last_built],
            )
    finally:
        tools.close()
        provider.save()
    result["usage"] = provider.usage
    write_json(run / "result.json", result)
    return result
