"""Bounded visual diagnostic experiment on a failed run; preserves native history."""

import argparse
import shutil
from pathlib import Path

from worldascode.adapters.rendering.browser import bundle, capture, comparison
from worldascode.config import Settings
from worldascode.evidence.georeference import load_evidence
from worldascode.experimental.native.workflow import Workflow, dump, read
from worldascode.kits.patches import text_edits
from worldascode.quality.evidence import metric_footprint_report
from worldascode.storage.artifacts import digest, file_hash, write_json


def audit(source, run):
    source, run = Path(source).resolve(), Path(run).resolve()
    if run.exists():
        raise ValueError("AUDIT_REQUIRES_NEW_OUTPUT_DIRECTORY")
    run.mkdir(parents=True)
    source_run = source.parent.parent
    inputs = read(source_run / "inputs.json")
    spec = read(source_run / "object-sculpt-spec.json")
    evidence = load_evidence(inputs["evidence"]["path"])
    for name in ("target.png", "object-sculpt-spec.json", "material-quality.json"):
        shutil.copy2(source_run / name, run / name)
    write_json(run / "inputs.json", inputs)
    workflow = Workflow(run, Settings.load(), max_calls=3, max_tokens=150000)

    # Diagnostic experiments do not resume or reset an exhausted native state.
    # Paid calls still use the shared provider budget and usage ledger.
    def diagnostic_node(name, prompt, images=(), max_output=7000):
        try:
            result = workflow.provider.call(name, prompt, images, max_output)
        except Exception as exc:
            write_json(
                run / "result.json",
                {
                    "accepted": False,
                    "status": "provider-failed",
                    "error_type": type(exc).__name__,
                    "note": "Request may have been billed; inspect usage unknown_token_reserve before any retry.",
                    "usage": workflow.provider.usage,
                },
            )
            raise
        write_json(run / (name + ".json"), result)
        return result

    workflow.node = diagnostic_node
    macro = [
        c
        for c in spec["componentTree"]
        if c.get("level") == "macro" and c.get("parent")
    ]
    names = [c["name"] for c in macro]
    length_units = max(
        max(c["dimensions"]["width"], c["dimensions"]["depth"]) for c in macro
    )
    length_m = max(max(w["length_m"], w["width_m"]) for w in evidence["wings"])
    metres_per_unit = length_m / length_units
    write_json(
        run / "metric-frame.json",
        {
            "metres_per_unit": metres_per_unit,
            "derivation": "Scale fixed once from longest macro wall dimension in original authored spec and longest evidence wing; not fitted independently for each candidate.",
            "source_spec_sha256": file_hash(source_run / "object-sculpt-spec.json"),
        },
    )
    baseline = run / "baseline"
    baseline.mkdir()
    for name in (
        "front.png",
        "rear.png",
        "side.png",
        "top.png",
        "camera-fit.json",
        "geometry-gate.json",
        "gates.json",
        "render-manifest.json",
        "divine-eye.json",
    ):
        if (source / name).exists():
            shutil.copy2(source / name, baseline / name)
    report = metric_footprint_report(
        read(source / "geometry.json"), evidence, names, metres_per_unit
    )
    write_json(baseline / "metric-footprint.json", report)
    diagnosis = workflow.visual_diagnosis(baseline)
    code = (source / "createObjectModel.ts").read_text(encoding="utf-8")
    contexts = [Path(v["path"]) for v in inputs["context"]]
    styles = [Path(v["path"]) for v in inputs["styles"]]
    patch = workflow.node(
        "evidence-grounded-code-revision",
        'Improve the actual Three.js building factory using this visual diagnosis and metric evidence. Return {"edits":[{"find":exact unique source substring,"replace":TypeScript}],"summary":...,"components":[IDs]}. Fix root causes comprehensively: preserve one east/up/south frame and fixed metres_per_unit; wall centre, length, width and rotation must match supplied wing coordinates. For wing local X/Z with rotation y, transform must match Three.js rotation convention. Wing positions are global under root, child transforms are parent-local; avoid double translation/scaling. Keep the two wings joined as evidenced. Replace broken roof primitives with flat-normal watertight pitched prisms that cover their walls, without coplanar roof/wall overlap or z-fighting. Multiple gables must be integrated volumes with plausible caps/trim, not giant unsupported triangles. Restore three-storey facade bay rhythm, pale masonry surrounds and restrained source-derived colors. Author detailed seeded brick and slate procedural textures at plausible spatial frequencies, using independent color/roughness/bump where appropriate. Style guides architectural illustration clarity and detail, not a fixed palette. Windows need glass/recesses and frames. Chimneys need real flue voids. Preserve runtime named nodes/metadata; invisible assembly carrier must have no renderable geometry. Keep source uncertainty documented; do not imitate photogrammetry damage. No external assets/network/imports. Do not change any gate or fake manifests. Image order: target, current front/top/rear/side, five context evidence images, style images.\nDIAGNOSIS: '
        + dump(diagnosis)
        + "\nFIXED METRES PER UNIT: "
        + str(metres_per_unit)
        + "\nGEO EVIDENCE: "
        + dump(
            {
                k: evidence[k]
                for k in ("frame", "footprint", "wings", "height_m", "tags")
            }
        )
        + "\nEDITABLE SOURCE:\n"
        + code,
        [
            run / "target.png",
            *[baseline / (v + ".png") for v in ("front", "top", "rear", "side")],
            *contexts,
            *styles,
        ],
        10000,
    )
    candidate = run / "candidate"
    candidate.mkdir()
    factory = candidate / "createObjectModel.ts"
    factory.write_text(text_edits(code, patch["edits"], digest(code)), encoding="utf-8")
    if (source / "assets").exists():
        shutil.copytree(source / "assets", candidate / "assets")
    # Assets are sometimes shared at the run root rather than under the pass.
    if (source_run / "assets").exists() and not (candidate / "assets").exists():
        shutil.copytree(source_run / "assets", candidate / "assets")
    bundle(candidate, native=factory)
    browser = capture(candidate, reference=run / "target.png")
    if "runtime_error" in browser:
        write_json(
            run / "result.json",
            {"accepted": False, "status": "runtime-failed", "browser": browser},
        )
        return
    comparison(
        run / "target.png", candidate / "front.png", candidate / "comparison.png"
    )
    metric = metric_footprint_report(
        read(candidate / "geometry.json"), evidence, names, metres_per_unit
    )
    write_json(candidate / "metric-footprint.json", metric)
    workflow.bridge.function_gate(
        "geometry", candidate / "geometry.json", candidate / "geometry-gate.json"
    )
    review = workflow.visual_diagnosis(candidate)
    write_json(
        run / "result.json",
        {
            "accepted": False,
            "status": "diagnostic-experiment-complete",
            "note": "Candidate preview with visual diagnosis and metric checks; native eight-pass acceptance remains required.",
            "baseline_metric": report,
            "candidate_metric": metric,
            "browser_passed": browser["passed"],
            "visual_diagnosis": review,
            "usage": workflow.provider.usage,
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    audit(args.source, args.run)
