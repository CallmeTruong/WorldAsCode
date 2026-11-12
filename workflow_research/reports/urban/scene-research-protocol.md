# Research protocol: scene-informed procedural urban reconstruction

Date: 2026-11-12. Implementation follows `specs/002-urban-grid-style/scene-revision.md`.

## Evidence and hypotheses

Local source inspection confirms no museum texture bindings, no group translation to its footprint anchor, one observed building versus 13 proxies, lighting-only executable style, and assumed road widths/scans. These are implementation failures, not proof that Google coverage is unsuitable. Google describes its product as textured 3D mesh, not semantic building/PBR assets: https://developers.google.com/maps/documentation/tile/3d-tiles.

Hypothesis A: joint scene observation improves context/placement and reduces redundant image calls. Hypothesis B: host-owned anchors and required surface bindings remove deterministic failures before visual review. Hypothesis C: staged component generation plus actual reference-style review improves identity and presentation. No hypothesis is marked validated before measured execution.

The pinned local img2threejs implementation is the reproducible process reference. Its review guidance distinguishes spec, code, camera and evidence failures and requires rendered comparison evidence: `vendor/img2threejs/grimoire/review/self_correction.md`; upstream https://github.com/img2threejs/img2threejs. Adapt its process deliberately; do not label a custom urban sequence as native compatibility.

## Candidate approaches

| Approach | Strength | Limitation | Decision |
|---|---|---|---|
| Independent fixed views and code for every object | Focused detail | Redundant captures, weak global consistency | Supplemental only |
| One unrestricted code response for the whole area | Fast composition | Hard to repair/cache; local details compete for context | Do not use as the sole architecture |
| Shared scene observations + stable component modules | Shared context, targeted repair, caching | Needs identity/placement/material contracts | Initial implementation |
| Direct textured mesh display | Preserves available source appearance | Not the requested editable procedural reconstruction | Keep as reference/control |
| Project/bake source photographs | Potentially closer appearance | Baked shadows, occlusion, UV seams, unseen faces | Separate future experiment |

## Experimental sequence

1. Preserve the previous rejected run. Prepare a 120 m sub-block with the same geo/provider/style sources. Report changed extent; do not call this a pixel-controlled comparison against 220 m renders.
2. Capture shared unclipped overhead/oblique views. Save position, orientation, projection/view matrices, viewport and coordinate origin; Cesium documents these camera quantities at https://cesium.com/learn/cesiumjs/ref-doc/Camera.html. Reserve one view for final validation. Legacy images lacking full matrices are not calibrated ground truth.
3. Observe all scene components jointly, then generate individually cached components. Distinguish visible evidence from priors. Inspect roofs and facade opening systems before spending tokens on tiny ornaments.
4. Apply exact placement/material checks. Resolve PBR assets on the trusted host. Record declared versus bound maps and fallback scans. Do not derive intrinsic albedo directly from shaded source pixels.
5. Render actual outputs. Compare scene footprint/height/roof, material identity/texture visibility, shared road continuity and reference-style treatment. Use separate judgment fields; geometry passing must not imply visual passing.
6. Perform bounded repairs only for evidence-backed failures. Retain source versions, error traces, usage and images. Stop with a specific unresolved issue rather than marking incomplete fidelity as successful.

## Measurements and scale decision

Record calls/tokens/wall time and reported cost (unknown if gateway does not report it), per-object evidence and generation coverage, missing map count, bounds failures, geometry failures, visual issues and tree anchor invariance. Do not extrapolate a city budget from one block. After fidelity passes, test cache invalidation, a neighboring block, canonical roads across the boundary and then streaming/LOD. Concurrency is a future measured optimization, not an assumed linear speedup.
