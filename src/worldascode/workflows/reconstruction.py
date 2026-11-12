"""Agent-authored building designs on measured sites.

Facts are measured (site brief), look comes from a style sheet read once per
style, and the agent writes a short design script in the building kit. The
script is rendered through the evidence cameras, checked against tolerant
metric limits, reviewed by a vision critic against the reference and the style,
revised a bounded number of times, and the best attempt is kept.
"""

import json
from pathlib import Path

import worldascode.evidence.georeference as georef
import worldascode.evidence.site_context as site_brief_module
import worldascode.geometry.massing as massing
import worldascode.geometry.surface_height as dsm
from worldascode.adapters.llm.transport import Provider
from worldascode.adapters.rendering.browser import render_attempt
from worldascode.config import ACCEPT, LIMITS, paths
from worldascode.contracts.execution import normalize_result, record_failure
from worldascode.evidence.images import detail_sheet, reference_sheet
from worldascode.nodes.building import author, critic, style_sheet
from worldascode.quality.evaluation import candidate_rank, validated_scores
from worldascode.storage.artifacts import digest, file_hash, write_json
from worldascode.workflows.massing import (
    detail_defaults,
)


def _run_design(
    evidence_path,
    styles,
    run,
    settings,
    max_revisions=1,
    max_tokens=220_000,
    adaptive_kit=False,
    max_kit_cycles=1,
    kit_version=None,
    publish_kit=False,
    kit_grant=None,
):
    run = Path(run).resolve()
    run.mkdir(parents=True, exist_ok=True)
    from worldascode.kits.evolution import copy_active_version, snapshot

    pinned_kit = run / "kit-versions/base/kit.mjs"
    if not pinned_kit.exists():
        pinned_kit = (
            copy_active_version(kit_version, pinned_kit.parent)
            if kit_version
            else snapshot(pinned_kit.parent)
        )
    evidence = georef.load_evidence(evidence_path)
    if adaptive_kit and not 1 <= max_kit_cycles <= 3:
        raise ValueError("KIT_CYCLE_LIMIT_MUST_BE_1_TO_3")
    provider = Provider(
        settings,
        run,
        max_calls=3
        + 3 * (max_revisions + 1)
        + (3 + 8 * max_kit_cycles if adaptive_kit else 0),
        max_tokens=max_tokens,
        max_seconds=3600 if adaptive_kit else 1800,
    )

    # Facts: zero model calls, and computed once per evidence bundle and fitter version.
    key = digest(
        [
            file_hash(evidence["path"]),
            file_hash(Path(massing.__file__)),
            file_hash(Path(georef.__file__)),
            file_hash(Path(detail_defaults.__code__.co_filename)),
        ]
    )
    cached = paths().cache_dir / "facts" / (key + ".json")
    if cached.is_file():
        stored = json.loads(cached.read_text(encoding="utf-8"))
        program = massing.BuildingProgram.model_validate(stored["program"])
        fit_report = stored["fit"]
    else:
        program, fit_report = massing.fit(evidence)
        program = massing.sample_appearance(
            evidence, detail_defaults(program, evidence)
        )
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
    observation = provider.call(
        "architecture-observer",
        "Observe the actual building from these calibrated photogrammetry views and matching detail crops. "
        "Return JSON {architecture:string, roof:{form:string, hierarchy:[strings], distinctive_features:[{description:string, view:string, confidence:number}]}, "
        "facades:[{view:string, storey_rhythm:string, bay_rhythm:string, depth_and_openings:string, confidence:number}], "
        "materials:[{region:string, identity:string, physical_pattern_scale:string}], priorities:[strings], uncertain:[strings]}. "
        "No style image is included: describe factual structure, not a desired style. Use measured footprint/heights as anchors. "
        "Do not identify every height blob as a turret or dormer. Describe roof-integrated shapes and facade relief; "
        "do not copy melted mesh, baked shadows or scan artifacts. Avoid unsupported hidden-side detail. "
        "For modern flat-roof architecture, do not impose historic ornaments. "
        "SITE: " + json.dumps(site),
        [references, source_details],
        2600,
    )
    site["observations"] = observation
    write_json(run / "observations.json", observation)
    write_json(run / "site.json", site)
    write_json(
        run / "input-manifest.json",
        {
            "evidence_sha256": file_hash(evidence["path"]),
            "evidence_path": evidence["path"],
            "height_field_sha256": file_hash(heights_path)
            if heights_path.is_file()
            else None,
            "styles": [file_hash(p) for p in styles],
            "kit_sha256": file_hash(pinned_kit),
            "surfaces_sha256": file_hash(pinned_kit.parent / "surfaces.mjs"),
            "site_sha256": digest(site),
        },
    )

    attempts, previous, feedback, extra_image = [], None, None, []
    for index in range(max_revisions + 1):
        folder = run / f"attempt-{index}"
        reply = author(
            provider,
            f"author-{index}",
            site,
            style,
            [references, *style_images, source_details, *extra_image],
            previous,
            feedback,
            kit_api=pinned_kit.parent / "kit-api.md",
        )
        code = reply.get("code", "")
        metrics, error = render_attempt(
            folder, code, site, style, evidence, kit_path=pinned_kit
        )
        record = {
            "attempt": index,
            "intent": reply.get("intent"),
            "code_sha256": digest(code),
        }
        if error:
            # A script that does not build is repaired by the next author turn.
            record["error"] = error
            previous, feedback, extra_image = code, {"build_error": error}, []
            attempts.append(record)
            continue
        review = critic(
            provider,
            f"critic-{index}",
            site,
            style,
            metrics,
            [
                references,
                folder / "render-sheet.jpg",
                *style_images,
                source_details,
                folder / "detail-sheet.jpg",
            ],
        )
        write_json(folder / "review.json", review)
        scores = validated_scores(review)
        prior_likeness = max(
            (a["scores"]["likeness"] for a in attempts if a.get("metrics_passed")),
            default=0,
        )
        likeness_regression = scores["likeness"] < prior_likeness - 0.030001
        record.update(
            {
                "metrics_passed": metrics["passed"],
                "mean_oblique_iou": metrics["mean_oblique_iou"],
                "scores": scores,
                "likeness_regression": likeness_regression,
                "accepted": metrics["passed"]
                and all(scores[k] >= v for k, v in ACCEPT.items()),
            }
        )
        record["rank"] = candidate_rank(record)
        attempts.append(record)
        if record["accepted"]:
            break
        best_so_far = max((a for a in attempts if "rank" in a), key=candidate_rank)
        regressed = likeness_regression
        previous_folder = (
            run / f"attempt-{best_so_far['attempt']}" if regressed else folder
        )
        previous = (previous_folder / "design.mjs").read_text(encoding="utf-8")
        feedback = {
            "scores": scores,
            "checklist": review.get("checklist"),
            "defects": review.get("defects"),
            "fixes": review.get("fixes"),
            "keep": review.get("keep"),
            "component_reviews": review.get("component_reviews"),
            "failed_metric_checks": [k for k, v in metrics["checks"].items() if not v],
            "regressed_likeness": regressed,
            "base_attempt": best_so_far["attempt"] if regressed else index,
            "revision_policy": "Preserve the best likeness; address the lowest normalized score first. A style/detail gain cannot compensate for incorrect architectural features.",
        }
        extra_image = [
            previous_folder / "render-sheet.jpg",
            previous_folder / "detail-sheet.jpg",
        ]

    built = [a for a in attempts if "rank" in a]
    best = max(built, key=candidate_rank) if built else None
    provider.save()
    result = {
        "accepted": bool(best and best["accepted"]),
        "acceptance_basis": "tolerant metric checks plus an automated vision critic; no human review",
        "status": "designed" if best else "no-buildable-design",
        "object_id": evidence["object_id"],
        "best_attempt": best["attempt"] if best else None,
        "attempts": attempts,
        "thresholds": {"critic": ACCEPT, "metric": LIMITS},
        "evidence_sha256": file_hash(evidence["path"]),
        "evidence_path": evidence["path"],
        "usage": {
            k: provider.usage[k]
            for k in (
                "calls",
                "input_tokens",
                "output_tokens",
                "unknown_token_reserve",
                "cache_hits",
            )
        },
        "active_seconds": round(provider.usage.get("active_seconds", 0), 1),
    }
    write_json(run / "result.json", normalize_result(result))
    if adaptive_kit and best and not result["accepted"]:
        from worldascode.workflows.refinement import evolve_design

        evolved = evolve_design(
            run,
            run / "kit-evolution",
            settings,
            max_kit_cycles,
            max_tokens,
            provider=provider,
            publish_kit=publish_kit,
            kit_grant=kit_grant,
        )
        result["kit_evolution"] = evolved
        result["accepted"] = evolved["accepted"]
        result["usage"] = {
            k: provider.usage[k]
            for k in (
                "calls",
                "input_tokens",
                "output_tokens",
                "unknown_token_reserve",
                "cache_hits",
            )
        }
        result["selected_render"] = evolved.get(
            "selected_render", str(run / f"attempt-{best['attempt']}")
        )
        write_json(run / "result.json", normalize_result(result))
    return result


def recover_design(run, error="Interrupted run; recover completed evaluations only"):
    """Recover saved artifacts without resubmitting any model request."""
    run = Path(run)

    def read(path, default):
        return (
            json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
        )

    existing = read(run / "result.json", {})
    if existing.get("status") == "designed":
        return existing
    manifest = read(run / "input-manifest.json", {})
    site = read(run / "site.json", {})
    records = []
    for folder in sorted(
        run.glob("attempt-*"), key=lambda p: int(p.name.split("-")[-1])
    ):
        if not (folder / "design.mjs").is_file():
            continue
        record = {"attempt": int(folder.name.split("-")[-1]), "accepted": False}
        metrics = read(folder / "metrics.json", {})
        review = read(folder / "review.json", {})
        try:
            scores = validated_scores(review)
        except ValueError:
            record.update(
                {
                    "evaluation": "unreviewed",
                    "metrics_passed": metrics.get("passed", False),
                    "error": "REVIEW_INCOMPLETE; no implicit retry",
                }
            )
        else:
            record.update(
                {
                    "evaluation": "reviewed",
                    "scores": scores,
                    "metrics_passed": metrics.get("passed", False),
                    "mean_oblique_iou": metrics.get("mean_oblique_iou"),
                    "accepted": metrics.get("passed", False)
                    and all(scores[k] >= v for k, v in ACCEPT.items()),
                }
            )
            record["rank"] = candidate_rank(record)
        records.append(record)
    reviewed = [a for a in records if "rank" in a]
    best = max(reviewed, key=candidate_rank) if reviewed else None
    result = {
        "accepted": False,
        "evaluation_complete": False,
        "status": "incomplete-run-retained",
        "error": error,
        "note": "Artifacts recovered without new model calls. Unreviewed renders are never promoted.",
        "object_id": site.get("object_id"),
        "evidence_sha256": manifest.get("evidence_sha256"),
        "best_attempt": best["attempt"] if best else None,
        "attempts": records,
        "usage": read(run / "usage.json", {}),
        "acceptance_basis": "Completed metric/critic artifacts only; incomplete run",
    }
    write_json(run / "result.json", normalize_result(result))
    return result


def run_design(
    evidence_path,
    styles,
    run,
    settings,
    max_revisions=1,
    max_tokens=220_000,
    adaptive_kit=False,
    max_kit_cycles=1,
    kit_version=None,
    publish_kit=False,
    kit_grant=None,
):
    run = Path(run)
    if (run / "result.json").exists():
        raise ValueError("USE_NEW_DESIGN_RUN; recovery never resubmits requests")
    try:
        return _run_design(
            evidence_path,
            styles,
            run,
            settings,
            max_revisions,
            max_tokens,
            adaptive_kit,
            max_kit_cycles,
            kit_version,
            publish_kit,
            kit_grant,
        )
    except Exception as exc:
        result = recover_design(run, type(exc).__name__ + ": " + str(exc))
        result["failure"] = record_failure(run, exc).model_dump()
        result = normalize_result(result)
        write_json(run / "result.json", result)
        return result
