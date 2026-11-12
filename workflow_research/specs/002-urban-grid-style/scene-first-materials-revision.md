# Scene-first reconstruction and evidence-driven materials

User clarification, 2026-11-12: a fixed texture set must not constrain observed surfaces. Assess whether multi-view reconstruction of an entire AOI is better than reconstructing isolated buildings and assembling them.

## Current implementation versus desired behavior

Current `build_scene` jointly observes shared scene photographs, creates a plan for all footprint IDs, then generates local building components. Host code owns placement. The experimental strict loop evaluates one target using matched-camera crops. It does not yet perform a joint optimization of roads, sidewalks, plants and all building parts. Passing one target cannot establish full-scene fidelity.

Current material resolution starts with six fallback Poly Haven surfaces and allows per-run `surface-requests.json` additions/overrides. Registry role validation now accepts the actual manifest rather than a closed six-role list. Nevertheless, the LLM does not yet have an implemented autonomous material-search tool. Most existing components were generated with the fallback set. A declared role with loaded maps establishes binding, not visual correspondence. The brown slate experiment demonstrated that substituting a nominally correct material family can still change the observed roof color incorrectly.

The new per-surface `useAlbedoMap:false` option retains normal and roughness while using the component's own tint. This avoids forcing an inappropriate scan color, but it is still an estimated material, not recovered source texture or calibrated intrinsic albedo. Do not relabel it as exact texture reconstruction.

## Proposed pipeline contract

1. **Shared evidence:** obtain reusable overhead and oblique AOI observations with camera metadata; retain stable object IDs, geospatial footprints, heights/uncertainty, visibility and source provenance. Style imagery is a separate arbitrary folder, not factual scene data.
2. **Joint scene analysis:** establish road/sidewalk networks, building-part associations, courtyards, vegetation anchors, spatial relationships and visible material boundaries across the entire AOI. One coordinate frame and ground datum. Identify conflicts before writing geometry.
3. **Scene graph and code:** produce one coherent scene graph. Code may be modular, but modules consume shared scene facts and common generators. Roads, markings, curb continuity and shared surfaces have shared ownership; a building module cannot independently redraw them. Components are patch boundaries, not observation silos.
4. **Material observation:** describe each observed surface by material family, observed appearance, pattern scale/direction, weathering, confidence and source views. Keep style treatment separate from factual identity.
5. **Material broker:** retrieve candidate materials from broad providers only after observation; compare candidate previews to source evidence. Allow procedural PBR recipes, library normal/roughness with evidence-informed tint, or depth/visibility-checked source projection when geometry/calibration supports it. Preserve unresolved surfaces as uncertain. Generated texture is an approximation, never evidence of factual match.
6. **Shared UV and scale:** use global or road-network coordinates for continuous surfaces, object-local coordinates for facades, roof-plane coordinates for roofing. Material sharing must not force identical appearance across unrelated surfaces or restart a road texture at every grid boundary.
7. **Whole-scene render and critique:** assess topology, spacing, silhouette, material relationships and style from common source cameras. Then inspect failing regions at higher resolution and patch those regions against the unchanged shared context. Run scene-wide regression checks after local changes.
8. **Held-out validation:** reserve source angles from repair prompts, expose missing observations and reject major defects. Stop or request targeted evidence when progress stalls; repeated aesthetic embellishment is not structural correction.

## Required comparative research

Compare A: a single full-AOI generator from shared multi-view evidence, with B: joint scene planning plus context-aware modules and targeted repairs. Use the same source views, factual data, style folder, held-out cameras and total API/token/time budget. Evaluate whole-scene coherence and per-region distinguishing details separately. Report runtime, requests, tokens, actual configured gateway cost, coverage and critical errors. Full-AOI code generation may improve relationships but can lose small details or make local repairs expensive; modular generation may improve detail but must prove it preserves scene relationships. Neither claim is established by the current single-target pilot.

Recommended next experiment: a small block with a few buildings and one complete street intersection, not an entire district. Stage the common scene first; compare outputs under the same budget before increasing AOI size. Do not keep spending on isolated-window refinements while roof topology or scene ownership remains wrong.
