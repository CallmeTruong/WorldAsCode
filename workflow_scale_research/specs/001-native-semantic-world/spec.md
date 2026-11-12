# Feature: Native-gated semantic world workflow

Created: 2026-11-12. Status: implementation and experimental validation. User requests a new independent workflow in workflow_scale_research, close to the original img2threejs skill, with semantic correctness and future scale.

## User Scenarios & Testing

### US1 ? Evidence-backed staged reconstruction (P1)
A researcher supplies factual views and arbitrary style images. Workflow nodes observe, author a native sculpt spec, run strict validation and build/review one unlocked pass at a time.
Independent test: an invalid/shallow spec cannot generate a native factory; a later pass cannot bypass the previous review; all commands and failures remain inspectable.
Acceptance: missing views produce request-input/pending, not invented confidence; critic and coder are separate nodes; code claims do not establish acceptance.

### US2 ? Structurally meaningful reusable assets (P1)
A hollow shaft, opening or roof assembly is represented by typed components with real geometry and semantic contracts.
Independent test: a filled shaft fails the opening contract while a proper annular wall passes; the same recipe can be placed at distinct locations without code changes.

### US3 ? Runtime variation without regeneration (P2)
Day/night/weather/seed channels alter only permitted state or inferred morphology.
Independent test: night changes emissions and wetness changes material response, while the same object's geometry/anchors remain stable; a shape seed does not change placement.

### US4 ? Spatial reuse and resumable jobs (P2)
Adjacent tiles reference a shared network and stable assets, and interrupted reconstruction resumes from persisted evidence.
Independent test: boundary ports/UV phases match, content-addressed assets are reused, and unverified source/render pairs cannot publish.

### Edge Cases
Unknown hidden parts; contradictory heights; source clipping; opaque caps mistaken for hollow outlets; stale screenshots after rollback; shader/material failures; partial upstream state; model truncation; uncertain billed transport; unsupported target/plugin; native hard stops.

## Requirements

FR-001: Keep a pinned canonical upstream checkout and execute native state/next/spec/pass/review tools; report capability completion honestly.
FR-002: Author observation, quality contract, detail mapping, topology and material applicability before generation; preserve native strict-quality floors.
FR-003: Run deterministic/semantic/camera evidence gates before visual acceptance; never fabricate native continue records.
FR-004: Preserve native correction limits and route continue/refine-spec/refine-code/request-input/stop inside workflow nodes.
FR-005: Store blueprint/version, instance/seed/provenance and runtime state separately; no compulsory texture catalog or style palette.
FR-006: Provide executable semantic generators/gates for hollow geometry, roof and facade components; permit bounded custom landmark modules.
FR-007: Maintain global graph identity, tile ownership/references and continuous stationing for roads/rails.
FR-008: Cache by dependency hashes and commit validated artifact manifests atomically. Resume retains usage and state.
FR-009: Use configured GPT Sol/base URL, protect credentials and enforce request/token/time limits.
FR-010: Capture actual browser multi-view output and actual style references; report technical/native/semantic/visual status independently.
FR-011: New code/package lives here without imports from the legacy implementation. The canonical pinned skill may remain shared.
FR-012: Preflight validates the exact pinned factory semantics (including transform-scale precedence, extrusion point/depth fields, and numeric executable repetition data), records lossless normalization, and keeps the original spec/evidence auditable. Deterministic hard-gate corrections follow the pinned correction-loop decision and limits.
FR-013: Separate source material observations from final authored appearance. Undersampled or illumination-contaminated image regions may establish material family, broad color placement and pattern direction, but cannot be presented as recovered high-resolution PBR. The workflow must let critic/coder nodes author deterministic, tileable procedural maps that creatively follow the requested style while retaining observed material identity, and must inspect those maps in rendered output.

FR-014: For the measured-site design route, permit bounded node-authored kit evolution in isolated, versioned copies. Distinguish evidence gaps, API misuse and missing capabilities. Protect measured walls/frames, cameras, shared source and acceptance policy; expose only relevant API/source to each role.

FR-015: A kit candidate must execute compatibility fixtures and an explicit exercise of its new capability on varied footprints, retain per-case failures for node feedback, and pass real-site metric/critic comparison before run-local activation. Pin dependencies, preserve rollback and verify hashes on reuse. Local activation is not global release, family generality or human visual acceptance.

FR-016: Evaluate held-out real sites using the same pinned kit. Distinguish kit reuse, unchanged recipe transfer and renderer replication; report visual acceptance separately from silhouette/build success.

FR-017: A failed provider review must preserve previously completed evaluations and billing uncertainty without resubmission. Unreviewed renders cannot replace reviewed results. Bounded fix-design routing must execute author/render/critic rather than silently terminate.

FR-018: Static scene batching must preserve geometry, UVs, transforms, material identity and instance ownership. Report draw calls and CPU geometry storage without claiming total GPU memory, device FPS or urban throughput.

## Key Entities
EvidenceBundle; WorldIR; AssetBlueprint; AssetInstance; SemanticComponent; RuntimeState; NetworkEdge/Port; NativeState; PassReview; BuildArtifact; JobLedger.

## Success Criteria
SC-001: All automated negative gate tests reject invalid pass order, filled shafts and stale evidence.
SC-002: Same seed/input/version reproduces the same geometry; day/night/rain state transitions do not rebuild it.
SC-003: A browser demo shows inspectable hollow geometry, independent material slots and state transitions.
SC-004: A real native bridge experiment produces command/state/spec/factory/gate artifacts, preserving failures and pending stages.
SC-005: No run is labelled skill-equivalent quality before all required native/visual gates have execution evidence.
SC-006: Adjacent-cell ownership and network seam fixtures pass; large-city throughput remains unclaimed until measured.
SC-007: Before generation, consumer-contract checks catch geometry fields that strict metadata validation accepts but the pinned factory ignores; identity defaults cannot silently override explicit dimensions, and each build pass checks only its promised components.
SC-008: Material evidence records original crop resolution and provenance; generated style maps are separately labelled, and visual review can route blurry or style-inconsistent materials to a bounded code-refinement node.
SC-009: Georeferenced wing reconstruction keeps a fixed metric frame, enforces evidence-derived macro node poses and reports camera-independent footprint/height errors; camera fitting may not translate wings.
SC-010: A failed render can receive diagnostic visual feedback without granting acceptance. Correction nodes receive original factual context and source views; pass acceptance still requires all render gates.

## Assumptions
Existing credentials and cached Google/OSM Tokyo images are available. Exact textures are not required. This release builds research infrastructure and bounded vertical slices; full traffic/animal simulation and city-wide fidelity are not implied by schema support.

## Current Validation Status

The native Tokyo experiment produced a strict-valid spec and factory, but stopped before a successful pass review when its configured 12-call model budget was consumed. The first render failed Divine Eye hard gates (silhouette IoU 0.307; scale delta 0.591). A separate native factory preview after identity-scale normalization still scored only 0.346 in the bounded silhouette-camera search and remains unaccepted. See `docs/06-experiment-results.md`; SC-005 and SC-006 are not yet satisfied.
