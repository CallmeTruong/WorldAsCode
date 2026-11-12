# Scene reconstruction revision — 2026-11-12

Implementation authorized by the user. This revision supersedes the original docs-only and HCMC scope. Active provider: Google Photorealistic 3D Tiles via Cesium ion. The original reference folder remains arbitrary user input, not a fixed preset.

## Problem and objective

The previous Tokyo run generated one approximate museum with unbound textures, misplaced local coordinates, thirteen blank context extrusions and generic roads. Technical tests passed while factual and style quality failed. The objective is a coherent small block reconstructed from shared scene evidence, with independently inspectable object modules and explicit uncertainty. Passing topology checks is insufficient.

## Research questions and experiments

1. Can common unclipped scene views identify all building masses/material systems and street surfaces? Analyze shared images once, associate findings with stable IDs, and request local evidence only for missing detail.
2. Can host-owned placement and explicit surface contracts prevent coordinate drift and silently missing maps? Enforce complete object coverage, measured bounds and material bindings before visual acceptance.
3. Does staged scene analysis plus component code improve roof/volume identity over the object-only run? Inspect massing, roof, openings, materials and composition separately; retain failed attempts.
4. Can descriptive style affect surface/detail treatment without palette constraints? Supply the actual style references to code generation and review; evaluate form, surface frequency, vegetation, lighting and composition separately from factual identity.
5. Which details require better imagery rather than more code? Record visibility gaps and stop inventing unseen geometry; source-matched cameras and an unused validation angle distinguish framing errors from reconstruction errors.

## Initial bounded implementation

Use a 120 m Tokyo sub-AOI from the already verified 220 m evidence set. Include every intersecting OSM building, shared roads and existing approximate tree observations. Full buildings clipped by the AOI boundary remain explicitly partial. Reuse common views; optional museum detail views supplement them. No fixed four-views-per-building requirement. No continuous input integration or public deployment.

## Contracts

- Scene input manifest: safe relative image paths, hashes, camera/viewport metadata where available, attribution and optional detail-to-object mapping. Style is a distinct image set.
- Scene observations: exactly one stable record per building, evidence image IDs, visibility/uncertainty, massing/roof/opening/material plans, plus common ground/surface observations. Unobserved details are labeled inferred.
- Local object functions: local footprint coordinates, host places group once at the canonical anchor. Host detects missing/duplicate IDs, geometry displaced outside expected footprint bounds and missing required material bindings. No silent automatic recoloring or material-name guessing.
- Material manifest: declared surface roles, natural versus painted albedo handling, metric scale and binding audit. Roads support direction-aware mapping; generic scans remain labeled substitutes.
- Review: separate geometry validity, scene coverage, factual visual acceptance and reference-style acceptance. Use source images, actual renders and actual style images. Any major defect prevents overall visual acceptance.

## Acceptance and limitations

Every AOI building has a generated component and an evidence status; no blank context proxy may count as finished. Object placement and declared textures pass executable checks. Real browser renders, saved comparisons and seed-anchor verification are required. Do not assert native img2threejs eight-pass completion, calibrated photogrammetric accuracy, full photographic baking or city-scale performance from this experiment. Exact camera capture is implemented for new views; older images without full matrices must remain marked uncalibrated.

Research evidence and sources: [root-cause audit](../../reports/urban/tokyo-pipeline-root-cause.md), [research protocol](../../reports/urban/scene-research-protocol.md).
