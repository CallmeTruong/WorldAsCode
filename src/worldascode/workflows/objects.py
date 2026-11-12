"""Bounded object author/reviewer loop with additive, run-local pack development.

Georeferenced buildings keep their measured reconstruction route. This workflow
handles a described object or small composition, optionally with photo/style
references. Publication is deliberately a separate host-authorized operation.
"""

import json
import math
from pathlib import Path

from worldascode.adapters.llm.transport import Provider
from worldascode.adapters.rendering.browser import render_object
from worldascode.config import ACCEPT
from worldascode.contracts.execution import record_failure
from worldascode.kits import packs
from worldascode.kits.code import analyze_source
from worldascode.nodes.building import style_sheet
from worldascode.quality.evaluation import validated_scores
from worldascode.storage.artifacts import file_hash, write_json

HOST_API = """Host contract: export function design(site,b,style) {...}.
Units metres, X/Y/Z = east/up/south. Objects stand on y=0; +X is forward.
b.material(id,{color,roughness,metalness,opacity,glow,weather,surface:{type:'plain|brick|slate|panels|asphalt|concrete|bark|foliage|soil',scale},seed}) declares a material before use.
b.at(x,z,yaw=0) returns a placement frame. b.box(frame,{w,h,d,y=0,material}), b.cylinder(frame,{r,h,material}), b.cone(frame,{r,h,material}), b.add(THREE.Object3D,frame) are generic escape hatches. b.THREE exposes Three.js.
No walls or roof are required for a non-building object. For required_checks, attach returnedPart.object.userData.semanticChecks=[{component_id:actual named mesh, requirement:opening or air_path, axis:[x,y,z], centre:[x,y,z], length:positive, wall_probe:[x,y,z]}]. The centre ray must cross the real hole and wall_probe hit its actual shell; coordinates local to that named mesh. Use pack methods for reusable features. Keep placements and dimensions from the brief; vary only permitted features with site.seed. Do not invent a fixed style palette. Unknown source details are estimates, not measured truth."""


def _brief(brief):
    if (
        not isinstance(brief, dict)
        or not isinstance(brief.get("description"), str)
        or not brief["description"].strip()
    ):
        raise ValueError("OBJECT_DESCRIPTION_REQUIRED")
    kind = brief.get("kind")
    if (
        not isinstance(kind, str)
        or not packs.SLUG.fullmatch(kind.replace("_", "-"))
        or kind == "building"
    ):
        raise ValueError("OBJECT_KIND_REQUIRED_USE_DESIGN_FOR_BUILDINGS")
    if type(brief.get("seed", 1)) is not int:
        raise ValueError("OBJECT_SEED_MUST_BE_INTEGER")
    for value in brief.get("envelope", {}).values():
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError("OBJECT_ENVELOPE_MUST_BE_POSITIVE_METRES")
    if not isinstance(brief.get("required_checks", []), list) or any(
        check not in {"opening", "air_path"}
        for check in brief.get("required_checks", [])
    ):
        raise ValueError("OBJECT_PHYSICAL_CHECKS_INVALID")
    return {"seed": 1, **brief}


def _catalog(records):
    return [
        {key: p.get(key) for key in ("id", "version", "summary", "kinds", "parts")}
        for p in records
    ]


def publish_candidates(
    run, token, subject="workflow", channel="incubating", heldout_runs=()
):
    """Post-review workflow stage; the grant is supplied by the host, never AI."""
    run = Path(run).resolve()
    result = json.loads((run / "result.json").read_text(encoding="utf-8"))
    if result.get("execution_status") != "completed" or not result.get("accepted"):
        raise ValueError("PACK_PUBLICATION_REQUIRES_ACCEPTED_OBJECT")
    winner = next(
        item for item in result["attempts"] if item["attempt"] == result["best_attempt"]
    )
    calls = set(winner["metrics"].get("part_calls", {}))
    published = []
    for record in result.get("activated_packs", []):
        candidate = packs.load(record["folder"])
        if (
            candidate["sha256"] != record["sha256"]
            or not set(candidate["parts"]) & calls
        ):
            raise ValueError("PACK_PUBLICATION_UNUSED_OR_CHANGED_CANDIDATE")
        release = packs.promote(
            candidate["folder"], token, subject, channel, heldout_runs
        )
        published.append({key: release[key] for key in ("id", "sha256", "folder")})
    receipt = {
        "published": published,
        "channel": channel,
        "quality_basis": "accepted object plus fresh pack fixtures",
        "host_subject": subject,
    }
    write_json(run / "publication.json", receipt)
    return receipt


def _develop(provider, run, brief, catalog, feedback, cycle, initial_pack=None):
    folder = run / "pack-candidates" / f"cycle-{cycle}"
    seed_pack = None
    seed_report = None
    if initial_pack:
        seed_pack = packs.load(initial_pack)
        seed_report = packs.validate(initial_pack, folder / "seed-validation")
        if seed_report["passed"]:
            if any(p["id"] == seed_pack["id"] for p in catalog) or set(
                seed_pack["parts"]
            ) & set(packs.part_names(catalog)):
                raise ValueError("PACK_CANDIDATE_COLLISION")
            candidate = packs.load(folder / "seed-validation/pinned")
            write_json(
                folder / "decision.json",
                {
                    "activated": True,
                    "sha256": candidate["sha256"],
                    "folder": candidate["folder"],
                    "scope": "run-local",
                    "source": "validated initial pack",
                },
            )
            return candidate, {
                "action": "reuse-validated-pack",
                "reason": "Existing generated code passed fresh fixtures; no regeneration needed.",
            }
    plan = provider.call(
        "kit-gap-object-" + str(cycle),
        'Diagnose a missing reusable operation from actual object requirements and the catalog. Return {"action":"fix-design|develop-pack|need-evidence","reason":string,"capability":string,"required_checks":["opening" or "air_path" when needed]}. '
        "Develop a missing reusable domain abstraction, not a parameter fix. Generic Three.js availability does not mean a tested reusable operation already exists. Never replace host methods.\n"
        + json.dumps(
            {"brief": brief, "catalog": _catalog(catalog), "feedback": feedback}
        ),
        max_output=1600,
    )
    write_json(folder / "plan.json", plan)
    if plan.get("action") != "develop-pack":
        return None, plan
    contract = """Create an additive reusable part pack. Return JSON {"id":unique-lowercase-slug,"parts":[names],"source":ES-module-code,"api":Markdown-call-signatures,"fixture":{"materials":{"materialId":material-spec},"calls":[{"part":declared-part-name,"frame":[x,z,yaw],"options":part-options}]},"summary":string}.
Module exports `export const parts={name(host,frame,o={}) {...}}`. Only import * as THREE from 'three'. Services: host._material(id), host._surface(id,{type,scale},seed), host._box(w,h,d,x,yBottom,z,materialId), host._prism(profile,depth,materialId), host._world(frame,x,z), host._add(object,kind,frame), host.at, host.roofY, host.site.seed, host.THREE. No other host fields, IO/globals/timers/dynamic imports or host mutations. Each part must add real geometry through host._add. The host is frozen.
For physical openings: host._add returns {object,pivot,id}. Attach returned.object.userData.semanticChecks=[{component_id:actual named mesh,requirement:'opening'|'air_path',axis:[x,y,z],centre:[x,y,z],length:positive,wall_probe:[x,y,z]}]. Coordinates local to the named mesh. Centre ray crosses real void; wall_probe must hit surrounding material. Axis crosses the full thickness. Place plates and objects on y=0, not floating. Three.js Shape/ExtrudeGeometry can model actual holes. Never label paint as a hole.
Fixture declares material IDs before use, calls every declared part, and must exercise the new operation. Include two size/shape variants when appropriate, with nonoverlapping frames. All parameters in metres. Three.js primitive conventions: CylinderGeometry is along Y, ExtrudeGeometry along Z, TorusGeometry lies in XY with its normal along Z. A horizontal ring around Y must be rotated appropriately. Geometry bounds and renders in diagnostics are authoritative. No place names, hardcoded object IDs or fixed style palettes in reusable code. Fixture/API colours are illustrative. Keep source below 12000 characters. Correct the actual diagnostic if this is a revision; preserve valid signatures."""
    previous = {}
    diagnostics = {}
    feedback_images = []
    if initial_pack:
        seed_pack = seed_pack or packs.load(initial_pack)
        previous = {
            "id": seed_pack["id"],
            "parts": seed_pack["parts"],
            "source": Path(seed_pack["module"]).read_text(encoding="utf-8"),
            "api": seed_pack["api"],
            "fixture": seed_pack["fixture"],
        }
        diagnostics = seed_report or packs.validate(
            initial_pack, folder / "seed-validation"
        )
        feedback_images = [
            p
            for p in (
                folder / "seed-validation/seed-1/front.png",
                folder / "seed-validation/seed-1/side.png",
            )
            if p.is_file()
        ]
    for revision in range(2):
        proposal = provider.call(
            f"kit-developer-object-{cycle}-{revision}",
            contract
            + "\n"
            + json.dumps(
                {
                    "brief": brief,
                    "plan": plan,
                    "existing": _catalog(catalog),
                    "previous": previous,
                    "diagnostics": diagnostics,
                }
            ),
            images=feedback_images,
            max_output=6500,
        )
        attempt = folder / f"revision-{revision}"
        write_json(attempt / "proposal.json", proposal)
        try:
            candidate = packs.create(
                attempt / "pack",
                proposal["id"],
                [brief["kind"]],
                proposal["source"],
                proposal["api"],
                proposal["parts"],
                proposal["fixture"],
                {"summary": proposal.get("summary", "")},
                required_checks=sorted(
                    set(
                        brief.get("required_checks", [])
                        + plan.get("required_checks", [])
                    )
                ),
            )
            if set(packs.part_names(catalog)) & set(candidate["parts"]) or any(
                p["id"] == candidate["id"] for p in catalog
            ):
                raise ValueError("PACK_CANDIDATE_COLLISION")
            report = packs.validate(candidate["folder"], attempt / "fixtures")
            feedback_images = [
                p
                for p in (
                    attempt / "fixtures/seed-1/front.png",
                    attempt / "fixtures/seed-1/side.png",
                )
                if p.is_file()
            ]
            if not report["passed"]:
                diagnostics = report
                raise ValueError("PACK_CANDIDATE_FIXTURES_FAILED")
            write_json(
                folder / "decision.json",
                {
                    "activated": True,
                    "sha256": candidate["sha256"],
                    "scope": "run-local",
                    "revision": revision,
                    "folder": candidate["folder"],
                },
            )
            return candidate, plan
        except (KeyError, ValueError, RuntimeError) as error:
            diagnostics = {**diagnostics, "error": str(error)}
            write_json(attempt / "rejection.json", diagnostics)
            previous = proposal
    write_json(folder / "decision.json", {"activated": False, "reason": diagnostics})
    return None, {"action": "fix-design", "reason": diagnostics}


def run_object(
    brief,
    run,
    settings,
    references=(),
    styles=(),
    extra_packs=(),
    max_revisions=1,
    max_tokens=100000,
    max_pack_cycles=1,
    initial_design=None,
    initial_pack=None,
):
    brief = _brief(brief)
    if not 0 <= max_revisions <= 8 or not 0 <= max_pack_cycles <= 3:
        raise ValueError("OBJECT_REFINEMENT_LIMIT_INVALID")
    run = Path(run).resolve()
    run.mkdir(parents=True, exist_ok=False)
    references = [Path(p).resolve() for p in references]
    if len(references) > 8 or any(not p.is_file() for p in references):
        raise ValueError("OBJECT_REFERENCES_INVALID")
    provider = Provider(
        settings,
        run,
        max_calls=3 + 3 * (max_revisions + 1) + 3 * max_pack_cycles,
        max_tokens=max_tokens,
        max_seconds=1200,
    )
    attempts = []
    best = None
    try:
        catalog = packs.discover(extra_packs)
        write_json(
            run / "input.json",
            {
                "brief": brief,
                "references": [str(p) for p in references],
                "catalog": _catalog(catalog),
                "styles": [str(p) for p in styles],
                "initial_pack": str(Path(initial_pack).resolve())
                if initial_pack
                else None,
                "initial_design": {
                    "path": str(Path(initial_design).resolve()),
                    "sha256": file_hash(initial_design),
                }
                if initial_design
                else None,
            },
        )
        observation = (
            {
                "parts": list(
                    {call["part"] for call in brief["recipe"]["calls"]}
                    & set(packs.part_names(catalog))
                ),
                "features": [brief["description"]],
                "uncertainties": ["explicit recipe; no inferred geometry"],
                "source": "explicit reusable recipe",
            }
            if brief.get("recipe")
            else provider.call(
                "object-observer",
                "Observe the requested object and any reference images. Select useful part names from the small catalog; do not request irrelevant packs. "
                'Return {"parts":[existing part names],"features":[physical requirements],"uncertainties":[unknown details],"missing_capabilities":[{description:missing reusable operation,reuse_reason:why several objects need it}]}. '
                "The brief fixes dimensions, kind and seed. Photos are evidence; without photos report the object as a design, not a faithful reconstruction.\n"
                + json.dumps({"brief": brief, "catalog": _catalog(catalog)}),
                references,
                1800,
            )
        )
        requested = observation.get("parts", [])
        if not isinstance(requested, list) or any(
            name not in packs.part_names(catalog) for name in requested
        ):
            raise ValueError("OBJECT_OBSERVER_UNKNOWN_PART")
        selected = packs.select(catalog, requested)
        developed = 0
        activated = []
        initial_feedback = {}
        if (
            observation.get("missing_capabilities") or brief.get("require_new_pack")
        ) and max_pack_cycles:
            candidate, diagnosis = _develop(
                provider,
                run,
                brief,
                catalog,
                {"observation": observation},
                developed,
                initial_pack,
            )
            developed += 1
            initial_feedback = {"capability_diagnosis": diagnosis}
            if candidate:
                catalog.append(candidate)
                activated.append(candidate)
                requested += candidate["parts"]
                selected = packs.select(catalog, requested)
        write_json(run / "observation.json", observation)
        style, style_images = (
            style_sheet(provider, styles, run)
            if styles
            else (
                {
                    "summary": "Use plausible detailed material treatment; preserve material identity."
                },
                [],
            )
        )
        write_json(run / "style.json", style)
        feedback = initial_feedback
        previous = ""
        for index in range(max_revisions + 1):
            folder = run / f"attempt-{index}"
            folder.mkdir()
            prompt = (
                HOST_API
                + "\nSELECTED PACK API:\n"
                + packs.api_text(selected)
                + "\n"
                + json.dumps(
                    {
                        "brief": brief,
                        "observation": observation,
                        "style": style,
                        "feedback": feedback,
                        "previous_code": previous,
                        "available_pack_index": _catalog(catalog),
                    }
                )
            )
            reply = (
                {
                    "code": packs.fixture_script(
                        {
                            "parts": list(
                                {call["part"] for call in brief["recipe"]["calls"]}
                            ),
                            "fixture": brief["recipe"],
                        }
                    )
                }
                if index == 0 and brief.get("recipe")
                else (
                    {"code": Path(initial_design).read_text(encoding="utf-8")}
                    if index == 0 and initial_design
                    else provider.call(
                        f"object-author-{index}",
                        prompt
                        + '\nReturn {"code":complete JavaScript module,"notes":[uncertainties]}. Or request {"request_parts":[existing part names]} for one extra API retrieval. Address reviewer feedback concretely; retain correct details.',
                        references,
                        7000,
                    )
                )
            )
            if reply.get("request_parts"):
                additional = reply["request_parts"]
                if (
                    not isinstance(additional, list)
                    or len(additional) > 8
                    or any(n not in packs.part_names(catalog) for n in additional)
                ):
                    raise ValueError("OBJECT_PART_DOC_REQUEST_INVALID")
                requested = list(dict.fromkeys([*requested, *additional]))
                selected = packs.select(catalog, requested)
                reply = provider.call(
                    f"object-author-{index}-docs",
                    prompt
                    + "\nREQUESTED API:\n"
                    + packs.api_text(selected)
                    + "\nReturn complete code now; no further retrieval.",
                    references,
                    7000,
                )
            code = reply.get("code")
            if not isinstance(code, str):
                raise ValueError("OBJECT_AUTHOR_CODE_REQUIRED")
            # A revision may request another existing pack; resolve from metadata
            # by actual static API usage, then expose its docs on the next turn.
            used = analyze_source(code)["api_methods"]
            selected = packs.select(catalog, set(used) | set(requested))
            metrics, error = render_object(folder, code, brief, style, packs=selected)
            if metrics and brief.get("require_new_pack"):
                metrics["checks"]["developed_pack_used"] = any(
                    set(p["parts"]) & set(metrics.get("part_calls", {}))
                    for p in activated
                )
                metrics["passed"] = bool(
                    metrics["passed"] and metrics["checks"]["developed_pack_used"]
                )
                write_json(folder / "metrics.json", metrics)
            review = {}
            if metrics:
                images = [
                    *references,
                    *[folder / name for name in ("front.png", "rear.png", "side.png")],
                    *style_images,
                ]
                review = provider.call(
                    f"object-critic-{index}",
                    "Strictly review the actual rendered object. Images: source references first ("
                    + str(len(references))
                    + "), then generated front/rear/side, then style references. "
                    "Judge form, dimensional plausibility, real volume/openings, attachments, grounded wheels/trunk/base, materials and requested style. Do not reward decorative noise. "
                    'With no source photos, likeness measures brief compliance, not real-world fidelity. Return {"likeness":0..1,"style":0..1,"detail":0..1,"defects":[specific observed problems],"fixes":[actionable coding instructions],"keep":[correct features],"missing_capability":null or {"description":string,"evidence":string}}. '
                    "Recommend a missing capability only if existing API and custom Three.js cannot reasonably express it. Never change gates.\n"
                    + json.dumps(
                        {
                            "brief": brief,
                            "observation": observation,
                            "style": style,
                            "metrics": metrics,
                        }
                    ),
                    images,
                    2600,
                )
                scores = validated_scores(review)
            else:
                scores = {key: 0 for key in ACCEPT}
            accepted = bool(
                metrics
                and metrics["passed"]
                and all(scores[key] >= minimum for key, minimum in ACCEPT.items())
            )
            item = {
                "attempt": index,
                "accepted": accepted,
                "metrics": metrics,
                "scores": scores,
                "error": error,
                "review": review,
                "render": str(folder),
            }
            attempts.append(item)
            write_json(folder / "review.json", item)
            rank = (accepted, bool(metrics and metrics["passed"]), min(scores.values()))
            if best is None or rank > best[0]:
                best = (rank, item)
            if accepted:
                break
            previous = code
            feedback = {
                "metrics": metrics,
                "error": error,
                "review": review,
                "design_code": code,
                "recent_reviews": [item["review"] for item in attempts[-2:]],
            }
            # Two rejected reviews trigger one diagnosis before more blind edits.
            stalled = index > 0
            if (
                index < max_revisions
                and (review.get("missing_capability") or stalled)
                and developed < max_pack_cycles
            ):
                candidate, diagnosis = _develop(
                    provider, run, brief, catalog, feedback, developed
                )
                developed += 1
                feedback["capability_diagnosis"] = diagnosis
                if candidate:
                    catalog.append(candidate)
                    activated.append(candidate)
                    requested += candidate["parts"]
                    selected = packs.select(catalog, requested)
        winner = best[1]
        result = {
            "status": "object-complete",
            "execution_status": "completed",
            "quality_status": "accepted" if winner["accepted"] else "rejected",
            "selection_status": "retained",
            "accepted": winner["accepted"],
            "best_attempt": winner["attempt"],
            "selected_render": winner["render"],
            "attempts": attempts,
            "pack_cycles": developed,
            "activated_packs": [
                {key: p[key] for key in ("id", "sha256", "folder", "parts")}
                for p in activated
            ],
            "evidence_basis": "reference photos plus brief"
            if references
            else "brief only; no factual likeness claim",
            "acceptance_basis": "automated critic plus deterministic checks; not human approval",
            "usage": provider.usage,
        }
        if not any(item["metrics"] is not None for item in attempts):
            result.update(
                execution_status="failed",
                quality_status="unreviewed",
                selection_status="none",
                selected_render=None,
            )
    except Exception as error:
        failure = record_failure(run, error)
        result = {
            "execution_status": "failed",
            "quality_status": "unreviewed",
            "selection_status": "none",
            "accepted": False,
            "failure": failure.model_dump(),
            "attempts": attempts,
            "usage": provider.usage,
        }
        if best and best[1].get("review"):
            retained = best[1]
            result.update(
                selection_status="retained",
                best_attempt=retained["attempt"],
                selected_render=retained["render"],
                accepted=retained["accepted"],
                quality_status="accepted" if retained["accepted"] else "rejected",
            )
    finally:
        provider.save()
    write_json(run / "result.json", result)
    return result
