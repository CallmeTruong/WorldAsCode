# Evidence-grounded reconstruction feedback

## Observed failure, 2026-11-12

V5 had no OSM/evidence in its manifest. V6 and V7 did contain an approximate six-point OSM footprint, two wing descriptions, a 19.34 m sparse-photogrammetry roof height and five images. Their code correction nodes did not consistently receive these facts or the context views. Prompt delivery alone did not constrain the implementation. In V7 a correction moved a wing to the opposite side to follow a camera fit. The result is structurally different from the input.

An independent ground-plane check of V7 attempt 5 scores **0.4352 footprint IoU** in the declared east/up/south frame. This check fixes the original spec's unit conversion once; it does not align or rotate each candidate to improve its score. It measures projected convex macro wall hulls, so concave footprints within one wall mesh may be overestimated. Missing wall names fail the check. This is a useful diagnostic against approximate OSM, not a survey-grade accuracy claim.

Other defects observed directly: roof/wall coplanar overlaps causing striped z-fighting; smooth roof normals; oversized disconnected gables; incomplete facade/storey rhythm; flat materials; damaged photogrammetry surfaces interpreted as architectural features. The low silhouette score includes camera/framing error as well as geometric error.

## Workflow changes

1. Keep deterministic acceptance gates, but run a diagnostic VLM even when those gates fail. It may describe defects and code fixes; it cannot accept the candidate or override a failed gate. Persist its response with the exact attempt and pass it to the code author.
2. Send the same georeferenced facts and all context images to every code correction. Image ordering distinguishes target, output, context and style. Preserve one coordinate convention and one fixed metres-per-unit value across iterations.
3. Add `metric-footprint.json` to render diagnostics and acceptance prerequisites for runs with georeferenced evidence. Report footprint IoU and relative maximum roof-height error. Initial thresholds are IoU >= 0.8 and height error <= 20%, reflecting approximate input. These must be calibrated on a broader benchmark before city-scale acceptance claims.
4. Fit camera direction and framing independently of geometry. Preserve source aspect ratio by letterboxing it into the render aspect. Search framing scale as well as camera direction. Pose remains an estimate until capture matrices and local coordinates are actually bound to rendering.
5. Capture a real map-stripped clay render for blockout diagnostics. Export only nonempty mesh geometry; empty hidden carrier meshes must not cause topology failures or camera bounds.
6. Hash the PNG actually written by `build_evidence`, not the source file before Pillow re-encoding. This fixes the source of the hash mismatch without disabling integrity verification.

## Bounded diagnostic experiment

`python -m worldscale.quality_audit --source runs/native-museum-v7-extended/blockout/attempt-5 --run runs/<new-name>` runs diagnostic VLM -> code revision -> browser captures -> metric and topology checks -> diagnostic VLM. It retains the failed run's history and uses a separate output directory; it does not restart its exhausted native correction counter. Calls and token budget are capped. A diagnostic preview always has `accepted: false`: complete eight-pass acceptance is separate work.

Synthetic appearance is allowed by the user, but neither source-image PBR claims nor style fidelity can be established by schema validation alone. The inherited approximation policy currently carries broad upstream quality warnings; the final renderer, metric tests and visual review must still prove geometry and appearance. A stricter warning allowlist remains desirable.

## Scale requirements

Before generating more buildings, make the coordinate frame, metres-per-unit and immutable footprint constraints explicit inputs to the asset compiler. Save separate wall, roof and decoration parameters. A camera or material correction must not silently change wall coordinates. Give each attempt a manifest of facts/images, code hash, metric results and visual feedback. Reject regressions and retain the best candidate rather than accepting the last iteration. Benchmark several building shapes and imperfect source captures before increasing throughput.

## Verification

43 repository tests passed after the changes, including metric translation/scale failure cases, fail-closed node binding and self-contained evidence loading. Ruff and viewer syntax checks passed. Successful software checks do not establish that the building meets visual quality requirements.

## Measured follow-up result

`runs/museum-v8-evidence-feedback-audit-1` failed on the first diagnostic provider request: connection aborted (`ReadError`) after 171.266 seconds, before response headers. No response/usage was returned. Its usage file carries an unknown reserve of 66,310 estimated tokens, not measured consumption. No blind retry was made.

A separate deterministic experiment `runs/museum-v8-fixed-frame-preview` binds the original wing node poses to the evidence centres/rotations with a fixed 24.9564 metres per model unit. Footprint IoU improved from 0.4352 to **0.9950**. This is projected macro wall plan overlap only, not total visual fidelity. Maximum mesh height is 20.963 m vs a source estimate of 19.34 m, a relative difference of **8.39%**. Neither result is a survey accuracy claim.

The browser rendered the actual patched factory; source/render comparison, overhead view, clay render and frame-binding record are retained. Direct inspection still finds roof z-fighting, smooth shading, implausible gables, missing facade/storey structure and low-detail materials. `accepted` remains false. This experiment proves that executable geographic binding repairs the wrong plan even without another paid coding call; it does not prove the final asset is satisfactory.

The binding currently targets native named macro wing nodes directly under root, paired by descending wing length. Ambiguous counts, missing anchors and nested macro parents fail closed. More complex buildings need explicit IDs mapping measured parts to compiler nodes and full footprint-extrusion constraints before this can generalize to a city.
