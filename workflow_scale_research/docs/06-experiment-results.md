# Native img2threejs experiment and quality findings

**Run date:** 2026-11-12 (Asia/Saigon)  
**Scope:** one cropped Tokyo museum-like photogrammetry reference, one user style image, native img2threejs `blockout`, plus an independent semantic runtime fixture.  
**Outcome:** infrastructure was exercised; visual acceptance was **not** achieved. This experiment is not evidence of original-skill quality parity.

## What ran

The native path used the pinned img2threejs checkout at commit `0c0c49bc168e648dbaf9c8c080474de0b3a941b6`. GPT Sol (`gpt-6-sol`) through the configured OpenAI-compatible gateway completed observation, assessment, geometry/spec and material nodes. The workflow admitted the target and style image, created the native `ObjectSculptSpec`, passed native `--strict-quality`, generated the native TypeScript factory, bundled it with Three.js and rendered real browser captures. Input snapshots, prompts, outputs, native command logs, usage and the SQLite ledger are under `runs/native-museum-v2/`.

The native attempt exhausted its configured 12-call model budget before the first pass could be accepted or iteratively repaired. Two requests ended in HTTP 524 without a usable response. The workflow reserved 194,037 tokens for transport outcomes whose billing was unknown and stopped rather than retrying them. The provider reported 123,293 input and 30,611 output tokens, 1,103 seconds active time, and no USD cost (`cost_usd: null`): the custom gateway's price schedule was not configured, so a dollar amount cannot be calculated honestly.

## Image review

The native `blockout` output is visibly not a faithful reconstruction: the source shows an elongated, detailed, pitched-roof building while the first render reduces it to a few badly proportioned masses and long strips. The upstream deterministic review recorded silhouette IoU **0.307** against a required **0.85**, scale delta **0.591** against a maximum **0.08**, and aspect-ratio delta **0.252** against a maximum **0.05**. Its color check also reported a maximum Delta-E of **13.18**. The native state correctly remained at `blockout`; no later pass or final emission is claimed.

The comparison in `runs/native-museum-v2/blockout/attempt-0/comparison.png` is the unmodified failed attempt. `runs/native-museum-v2/blockout/attempt-0/gates.json` contains the deterministic gate results. The failure was preserved rather than relabeled as accepted.

## Material and texture-source audit

I inspected `runs/native-museum-v2/material-source-vs-albedo.jpg` and generated a machine-readable audit at `runs/native-museum-v2/material-source-audit.json`. The target is 882×555 px. Its six selected material crops are only 4–22 px wide and 20–31 px high. The native extractor expanded them into 1024×1024 maps and returned passing confidence values (0.701–0.768), even while reporting weak foreground isolation, tiny masks, low value range, or that single-image PBR cannot establish physical material. This is a quality-gate gap: a confidence threshold alone accepted maps with too little source detail.

The contact sheet shows the result directly: broad color smears and blocky tonal fields, not recovered stone, metal, glass, or roof texture. The generated maps do not contain new observed detail; they are algorithmic estimates from a few pixels. The screenshot is photogrammetry rendered through Google 3D Tiles, with baked illumination, perspective, occlusion and mesh/texture artifacts. It remains useful for broad material family, color placement, pattern direction and geometry across views; it is a poor source for clean neutral PBR. The provider is not categorically unsuitable. The mistake was treating this view and these tiny ROIs as detailed surface scans, then trusting the extractor's confidence as a resolution/quality gate.

The workflow now records original crop sizes and material provenance in `material-quality.json`, creates a source-vs-generated contact sheet, and labels low-resolution crops as material identity cues rather than final PBR. The critic must return a material score when synthesis is needed. A score below 0.75 routes to the bounded `refine-code` node (unless it calls stop/request-input). Critic and coder prompts explicitly review texture clarity/style and are instructed to create deterministic, tileable procedural Three.js surface detail that follows the requested style while retaining observed material identity and meaningful pattern direction. The source crop and the stylized output are separate concepts; the style image must not force a fixed palette.

This is a workflow and review change, not yet proof that the model authored an improved texture on this Tokyo asset. The current old run is preserved and was not relabelled. The explicit `stylePbr` material override and successful visual iteration remain open work; native extraction still supplies an initial compatibility proposal to upstream strict checks. We must not call that proposal an accepted final style texture. To prove the new route, a fresh bounded model run must produce the style-aware procedural edit, rerender it, and pass both material close-up review and the existing native gates.

## Root cause found in the upstream factory contract

Inspection of the pinned generator's `scale_vector()` showed that the presence of `transform.scale` takes precedence over `dimensions`. The spec author supplied meaningful measured dimensions for 19 components and also serialized the default identity scale `[1,1,1]`. The native factory therefore baked unit-sized geometry instead of the authored dimensions. Native strict validation does not reject this combination, so a semantically plausible, strict-valid spec can still produce a geometrically wrong factory.

The project now performs a recorded, lossless normalization: when a component has positive dimensions and exactly the default identity scale, remove only that default scale so the native factory consumes the declared dimensions. Explicit non-identity scales remain untouched. The normalization record includes before/after hashes and every changed component. This is a consumer-contract check derived from the pinned generator, not a modification to upstream or a fabricated review.

The same contract check converts only known factory field aliases for extrusion (`profile2D.outer` to `points`; descriptor depth to `profile2D.depth`) and validates numeric profiles, positive depth, hole polygons and executable repetition counts/placements before code generation.

## Controlled factory preview after the fix

To separate factory generation from the exhausted model budget, a separate preview spec was normalized and sent through the real pinned strict validator and factory generator. Both exited **0**. The real browser then loaded the PBR asset files, rendered the native factory and passed browser technical checks: no JavaScript errors or denied requests, and runtime state left mesh geometry unchanged. It had 5,224 triangles.

This preview still looks wrong compared with the source. Its bounded camera search scored only **0.346** silhouette overlap, it carries **zero semantic opening probes**, and it was only the `blockout` pass. It did not pass native visual gates; no texture or style fidelity acceptance is claimed. This establishes that fixing the silent unit-scale bug is necessary but insufficient. Remaining problems include weak camera/view registration, ambiguous axes and component placement, coarse macro decomposition, cropped/photogrammetry-damaged source areas, and absent multi-view evidence. These require a corrected observation/spec or a deterministic hard-gate-driven code repair and a fresh native review under available budget.

Open [the scale-fix comparison](../runs/native-museum-v2/scale-fix-preview/comparison.png) and [the preview front view](../runs/native-museum-v2/scale-fix-preview/front.png). The corresponding strict validation, factory generation, camera-fit and browser reports are beside them.

## Semantic/runtime capability fixture

The independent procedural `semantic-demo-v2` fixture rendered 18,336 triangles and passed its runtime checks. Its hollow flue probe reported `centreHits=[]` and `wallHits=1`, demonstrating a real through-void test rather than a painted circular mark or a solid cylinder. Day/night/wetness/seed operations retained geometry invariants. This is deliberately simple test geometry, **not** an img2threejs reference reconstruction or a quality showcase; see `runs/semantic-demo-v2/front.png` and `render-manifest.json`.

## Workflow changes from this experiment

- Compile against fields the pinned factory actually reads, not only fields accepted by the spec validator.
- Scope part-coverage checks to the current native pass; macro blockout must not fail because later meso/micro work is absent. The final pass continues to check the complete spec.
- Route Divine Eye hard failures through the pinned native correction-loop decision. Its hard-gate result selects `refine-code`; the downstream coding node must make a bounded source edit and keep native part/runtime contracts. `refine-spec` remains for evidence/spec defects.
- Keep deterministic hard gates ahead of image-critic calls. The fixed order is native: deterministic diagnostics, pass check, then—only if those pass—the AI critic and review append. A failed result is still appended and synchronization follows the real native state.
- Keep the original hard stop, pass order, per-pass and total correction limits, token circuit breaker, and uncertain-request no-blind-retry behavior.

The current experiment could not spend the next coding-node call because its model budget had already been consumed. The new route is covered by native function-gate tests; its correction output has **not** yet been observed on this Tokyo asset.

## Reproduction and status

From `workflow_scale_research/` run:

```powershell
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m worldscale.cli demo --run runs/semantic-demo-v2
.venv/Scripts/python -m worldscale.cli native `
  --reference inputs/reference/tokyo/museum-photogrammetry.jpg `
  --styles inputs/style-references/user-reference `
  --run runs/new-tokyo-pilot --max-calls 12 --max-tokens 360000
```

The pilot can use a paid model gateway. Set a finite per-run token/call budget; USD reporting requires the gateway's actual input/output prices. A fresh run is needed after changing the workflow/compiler contract; do not edit the old evidence in place and treat it as a new review.

Current local verification after the texture-audit and reviewer/coder prompt changes: **37 tests passed**, Ruff passed. Node syntax checks from the original package audit passed; the latest change only affects Python orchestration and prompts. A complete eight-pass accepted reconstruction, improved styled texture render and city-scale throughput remain unverified.
