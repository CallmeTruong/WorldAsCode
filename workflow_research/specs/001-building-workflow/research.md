# Research: image-to-procedural building workflow

Date: 2026-11-11 (Asia/Saigon). Source: `../../../docs/wordflow_research.md`.

## Upstream pin and scope

Investigated repository: https://github.com/img2threejs/img2threejs

Pinned commit: `0c0c49bc168e648dbaf9c8c080474de0b3a941b6`.
Local source: `vendor/img2threejs/`. `SKILL.md` declares version 2.0.1; the npm installer package declares 0.2.0. Record the commit rather than treating these different version fields as interchangeable.

This research batch uses three public real-building photographs, direct-code versus structured-spec generation, and bounded targeted corrections. It does not implement continuous intake, claim held-out validation, or claim city-scale fidelity. The native eight-pass img2threejs baseline remains incomplete until its own evidence-backed pass gates have run. An experimental adapter completing its shorter graph must not be reported as completion of the native baseline.

## Decision: use LangGraph plus explicit self-hosted adapters

Rationale: `SKILL.md` and `docs/ARCHITECTURE.md` define a staged reconstruction skill, deterministic tools and host-provided visual judgment. They do not supply a complete self-hosted HTTP rendering service. Upstream `package.json` packages an installer CLI, not a runtime renderer. Build API adapters, persistence, bounded execution and the browser viewer in this project. Never call Codex/Claude Code CLIs from reconstruction jobs.

Alternatives considered: driving a coding-agent CLI violates the requested runtime architecture; using a fixed architectural template alone does not investigate LLM-authored procedural code; treating the upstream generator as a complete service omits rendering and vision judgment.

## Decision: generic profile with progressively loaded evidence

Buildings fit the built-in `generic` profile. There is no verified building-specific domain plugin in this checkout. Character, hair, humanoid rig and weapon-specific gates are inapplicable, with applicability reasons recorded rather than silently omitted. Load intake, geometry and review documents at their respective stages instead of copying the entire repository into every API request.

Sources: `SKILL.md`; `forge/_shared/domains/__init__.py`; `forge/_shared/workflow_state.py`; `grimoire/intake/image_analysis.md`; `grimoire/intake/surface_topology.md`; `grimoire/review/gates_reference.md`.

## Decision: retain upstream state and gate outcomes honestly

`forge/state.py` stores an atomic JSON checklist; `forge/next.py` reports the next ordered action and bounded correction status. Default bounds are three corrections per pass and six total. Keep this native checklist alongside LangGraph checkpoints. Only mark a native step done with its actual evidence; a smoke-test graph ending is not authority to mark all native passes done. Preserve blocking results and `partial` outcomes.

Canonical passes in `docs/ARCHITECTURE.md`: `blockout`, `structural-pass`, `form-refinement`, `material-pass`, `surface-pass`, `lighting-pass`, `interaction-pass`, `optimization-pass`.

`forge/_shared/workflow_state.py` documents an upstream rough edge: final `emission-target` can remain pending when no target is selected. Record this state rather than inventing completion.

Alternatives considered: duplicating native state without reconciliation risks contradictory completion; marking all steps done after a successful screenshot bypasses quality gates.

## Decision: distinguish the building research schema from ObjectSculptSpec

An application schema with components, materials, repetitions and uncertainty is useful model context, but is not automatically a valid upstream ObjectSculptSpec. Preserve its own schema identifier. Produce a separate upstream scaffold and map fields explicitly when exercising native validation.

Verified command signatures, run from `vendor/img2threejs` with absolute job artifact paths:

```powershell
python forge/state.py init --state <job>/.img2threejs/state.json --reference <job>/reference.png --profile generic --spec <job>/object-sculpt-spec.json
python forge/next.py --state <job>/.img2threejs/state.json
python forge/stage2_spec/new_pre_spec_assessment.py "Building name" --image <job>/reference.png --complexity moderate --domain generic --out <job>/assessment.json
python forge/stage2_spec/new_sculpt_spec.py "Building name" --image <job>/reference.png --assessment <job>/assessment.json --domain generic --out <job>/object-sculpt-spec.json
python forge/stage2_spec/validate_sculpt_spec.py <job>/object-sculpt-spec.json --json
python forge/stage2_spec/validate_sculpt_spec.py <job>/object-sculpt-spec.json --strict-quality --json
```

The assessment command also performs local BM25 evidence search. These commands create starter artifacts, not a finished building spec. Do not pass `--augmentation` unless a real domain augmentation artifact exists.

Mapping contract:

| Building research field | ObjectSculptSpec destination and constraints |
| --- | --- |
| Components | `componentTree[]`: unique `id`, `name`, `level`, `parent`, `primitive`, `topologyClass`/rationale, dimensions with units/confidence, transform, material links, geometry descriptor, evidence refs; retain scaffold action/surface fields |
| Materials | `materials[]`: unique IDs, supported shader/PBR fields, independent albedo/roughness/metalness channels; component `material` and `materialLayers` reference valid IDs |
| Repeated facade elements | `repetitionSystems[]` with real component references and observed layout; do not invent repetition merely to satisfy a count |
| Observations/uncertainty | `viewEvidence`, component confidence/evidence refs and `assumptions`; distinguish hidden-side inference from observation |
| Quality requirements | assessment-derived `qualityContract`, subject-specific `featureReviewTargets`, `detailInventory` mappings and native `buildPasses` |
| Generated implementation | stored TypeScript plus measured part manifest and geometry; code existence does not prove spec coverage |

Do not lower complexity floors to force a pass. `new_pre_spec_assessment.py` defines moderate minima: 2 macro components, 3 meso components, 2 micro feature groups, 2 material layers, 3 review viewpoints and 6 inventory details. Complex minima: 3/8/5/3 respectively, one repetition system, 4 viewpoints and 10 details. Inventory details must map to real component/local-feature/material entries.

The upstream generator (`forge/stage3_build/generate_threejs_factory.py`) is a useful native baseline and refuses generation until strict-quality succeeds. It is not a substitute for the requested experimental LLM-authored code branch. Any comparison must label which implementation produced the geometry.

## Decision: browser-rendered evidence with local geometry export

`forge/stage4_review/render_bridge.py` manages manifests and checks evidence; it does not render. `scripts/capture_threejs_playwright.py` is an optional capture adapter. The project's actual Three.js viewer must expose ready evidence and a camera/capture API, as documented in `grimoire/build/python_threejs_render_bridge.md`:

```javascript
window.__IMG2THREEJS_READY__ = true;
window.__IMG2THREEJS_CAPTURE__ = {
  async setCamera({azimuthDegrees, elevationDegrees, target, distance, fovDegrees, near, far}) {},
  async capturePass({passId, mode}) {},
};
```

Capture front/back/left/right/isometric views and record camera, viewport, renderer version/settings, generated-source hash, screenshot hash and console diagnostics. Reopen saved screenshots with an image-capable tool; ready signals and compilation are insufficient evidence.

`SKILL.md` references `runtime/scripts/export_mesh_geometry.mjs`, but that runtime directory is not available in this checkout. Implement a project-owned export of mesh vertices, indices, normals, bounds and named parts. Feed actual measured data to upstream geometry checks, never synthetic success records.

## Decision: deterministic checks before visual critique

Reuse or adapt `geometry_integrity.py`, `self_intersection.py`, `attachment_anchor.py`, `check_part_coverage.py`, `turntable_gate.py` and multi-angle diagnostics. Record measurement coverage and unmeasured attachments. A named-part coverage pass proves the model contains specified parts; it cannot prove intake identified every real architectural feature.

Native pass acceptance uses `diagnose_render.py`, `orchestrate_passes.py`, comparison sheets and `append_review.py`. Blockout diagnostics require map-stripped render evidence. Visual acceptance also requires critical-feature scores, not merely a high global number. Exactly one action is recorded: continue, refine-spec, refine-code, request-input or stop. Preserve the best valid candidate when a correction regresses.

Sources: `grimoire/review/gates_reference.md`; `grimoire/review/self_correction.md`; `forge/stage4_review/append_review.py`; `forge/stage4_review/check_part_coverage.py`.

## Decision: do not misrepresent image metrics

The photo-versus-procedural caveat in `grimoire/review/self_correction.md` explicitly warns that background, framing, scale and illumination can dominate IoU, SSIM and edge scores. IoU is meaningful only after foreground extraction and camera/scale/translation alignment. Without the prerequisites, report the metric as unavailable with a reason. Do not optimize geometry to compensate for a wrong camera or lower native thresholds to force continuation.

Use observable architectural rubric items plus actual geometry validation and direct visual inspection in the smoke batch. Hidden-side render consistency is not evidence of agreement with an unseen real facade. VLM scores remain provisional until evaluator reliability and human agreement are measured.

## Remaining limitations and deferred validation

- Native eight-pass fidelity baseline requires genuine evidence and is not complete merely because the experimental smoke path runs.
- Three buildings and one or two correction rounds can reveal feasibility and failure modes, not establish an optimal model/workflow or held-out generalization.
- Provider availability, API pricing and usage accounting must be measured from the configured endpoint; unknown prices remain unknown.
- Building dimensions inferred from a photograph are relative unless trustworthy metric metadata exists.
- Continuous input integrations, full development/held-out benchmark, rigorous evaluator calibration, georeferenced city assembly and streaming are subsequent phases.
- Browser isolation, hard timeouts, memory controls and credential separation belong to the project's execution adapter; the upstream skill is not an OS sandbox.
