# Implementation Tasks: District 1 Style Pilot

User authorization: 2026-11-12. Implementation replaces prior docs-only scope. Finite pilot: 12 API attempts, 180k tokens, 2400 active seconds; deterministic rendering watchdogs and validated inputs. Local research only; Google reference views are now explicitly authorized by the user.

## Phase 1 — Setup
- [X] T001 Persist the exact user attachment and style provenance in inputs/style-references/user-isometric/.
- [X] T002 Update specification, plan, contracts and dependencies for bounded implementation in specs/002-urban-grid-style/ and pyproject.toml.

## Phase 2 — Foundation
- [X] T003 Implement safe folder ingestion and real LLM StyleProfile extraction in src/building_workflow/urban/style.py.
- [X] T004 Normalize OSM polygons/holes/partial relations and coordinates, stable IDs/ownership, roads and data uncertainty in src/building_workflow/urban/data.py.
- [X] T005 Resolve licensed texture assets on the trusted host in src/building_workflow/urban/assets.py.

## Phase 3 — US1 data readiness
Independent validation: source metadata and derived city manifest identify incomplete relations, inferred heights and road widths.
- [X] T006 [US1] Produce versioned area/cell/object manifests and bounded source audit in runs/urban/district1-pilot/.

## Phase 4 — US2 visual procedural pilot
Independent validation: actual source executes in an isolated worker, real Three.js outputs show the same AOI across four cells.
- [X] T007 [US2] Generate free procedural building code via the API and preserve response/source under runs/urban/district1-pilot/.
- [X] T008 [US2] Build role/instance-aware sandbox worker and trusted urban renderer in runtime/urban-worker.mjs and runtime/urban-viewer.mjs.
- [X] T009 [US2] Implement persistent bounded research orchestration and CLI in src/building_workflow/urban/runner.py and cli.py.
- [X] T010 [US2] Render neutral/styled overview, grid, street and closeup views; inspect and refine using actual visual evidence under runs/urban/district1-pilot/.

## Phase 5 — US3 flexible reference style
Independent validation: arbitrary reference folder produces a hashed profile; style is material-only, geometry identical.
- [X] T011 [US3] Bind extracted profile and physical-scale textures independently of geometry in runtime/urban-viewer.mjs.
- [X] T012 [US3] Report contact sheet, extracted attributes, paired renders and separate structural/style reviews in reports/urban/.

## Phase 6 — US4 continuity and reuse
Independent validation: canonical road union equals tiled union; object owners unique; style-only and unchanged cell reruns retain geometry hashes.
- [X] T013 [US4] Validate seams, ownership, holes, deterministic inputs and style-only reuse in tests/test_urban.py.
- [X] T014 [US4] Measure actual draw calls/frame timing/geometry resources and cache behavior under runs/urban/district1-pilot/.

## Phase 7 — Validation and delivery
- [X] T015 Run meaningful geometry/browser/integration checks and existing regressions in tests/.
- [X] T016 Open the local viewer, inspect saved images and finalize measured findings, limitations and reproducible commands in reports/urban/findings.md and README.md.

Dependencies: setup -> data/style/assets -> source worker -> render -> review/refinement -> reuse/performance -> findings. Data preparation and style extraction can proceed independently; no implementation task is claimed complete by a proposed design. Native eight-pass equivalence, unseen-facade fidelity and larger-area scaling remain separately tracked when not demonstrated by this pilot.

## Completion evidence and scope

T001?T016 completed for the bounded pilot on 2026-11-12. See `reports/urban/findings.md` and `validation.md`, selected run `district1-final-v4`, and retained failed/refinement experiments. T013 proves canonical surface topology, unique ownership and input/material cache invalidation; it does not establish runtime cell streaming. T014 records CPU submission/resource measurements, not guaranteed FPS or large-area throughput. T016 inspection found significant visual defects, so delivery remains partial in fidelity. Additional per-object branch observes one licensed Opera House photograph and composes bespoke code; 35 buildings remain inferred.

## Quality correction authorized after user visual review

The previous pilot's technical completion did not meet the user's visual target. The [quality audit](../../reports/urban/quality-audit.md) is the baseline for these changes. Style must be clear descriptive guidance, without a prescribed palette or rigid material limits.

- [X] T017 Replace palette schema with descriptive artistic intent; separate executable presentation experiments and preserve per-object material identity.
- [X] T018 Remove grayscale texture override, bind appropriate per-surface PBR maps and physical-scale mapping, retain native albedo and material slots.
- [X] T019 Add configurable AOI/grid and a smaller photo-backed cluster; analyze part plans and generate separate object modules. Keep unknown context as explicit proxies.
- [X] T020 Inspect every observed object with dedicated front/top renders; bounded visual refinement and quality state distinct from runtime validity.
- [X] T021 Correct factual-image/dependency hashing, remove arbitrary procedural streetscape saturation and unsupported lane markings.
- [X] T022 Run regressions, inspect actual images/browser, document measured improvements and remaining visual defects. Do not declare fidelity achieved from passing tests.

Quality-correction implementation evidence: `district1-quality-v10`, `reports/urban/quality-correction-results.md` and `quality-validation.md`. 34 regression checks pass and all three observed objects have individual review. Technical validity is true; visual acceptance is false. These checked tasks describe implemented corrections and verification, not completion of photographic fidelity, full native eight-pass compatibility or city-scale streaming. Research required retained manual technical corrections; do not claim fully autonomous success on unseen inputs.


## Tokyo provider and multi-view revision (2026-11-12)

The active test AOI is Marunouchi / Mitsubishi Ichigokan, Tokyo (139.76310, 35.67845), 220 m square, four cells. HCMC is retained as a failed detailed-coverage probe, not the active reconstruction target.

- [X] T023 Integrate the official CesiumJS Google Photorealistic 3D Tiles viewer using the existing ion credential; retain attribution and keep credentials out of artifacts.
- [X] T024 Validate actual Tokyo geometry in six captured views, not just endpoint HTTP status; retain coverage and failure counters.
- [X] T025 Parameterize OSM snapshot and choose UTM zone from AOI coordinates; Tokyo uses EPSG:32654.
- [X] T026 Capture four side views plus overhead for an individual object; record camera, provenance and clipping limitations. Analyze the combined factual views separately from arbitrary style references.
- [X] T027 Detect approximate overhead canopy anchors; merge with OSM tree nodes and instance deterministic seeded tree shapes without moving anchors.
- [X] T028 Complete the Tokyo procedural render, inspect actual images and record visual acceptance separately from geometry validity.
- [X] T029 Run regressions and verify interactive seed changes preserve anchor positions.

Scaling requirement: run a coverage/visibility gate per AOI, then schedule per-object observation and reconstruction by stable OSM identity. Cache factual observations, source, texture assets and style independently. Context proxies must never be counted as successfully reconstructed facades. Runtime streaming, photographic texture baking and city-scale throughput remain unproven.

Tokyo completion evidence: `runs/urban/tokyo-multiview-v1/result.json`, `quality-review.json`, `interactive-validation.json`, and `reports/urban/tokyo-findings.md`. 40 tests pass; browser seed variation changes geometry while preserving all 58 anchors, with zero page errors. Camera framing now uses actual object bounds. Visual acceptance remains false; this is not complete AOI reconstruction.


## Scene reconstruction implementation

- [X] T030 Document the code-level root causes, candidate workflows, experiment protocol and acceptance boundaries.
- [ ] T031 Add hashed shared-scene inputs, full camera metadata and joint observations with complete stable object IDs.
- [ ] T032 Generate cached local component modules with host-owned placement and geometric alignment checks.
- [ ] T033 Enforce explicit material binding and metric/directional mapping; label evidence versus substitute textures.
- [ ] T034 Supply actual style references to generation/review and evaluate factual/style acceptance separately.
- [ ] T035 Run and directly inspect the complete small Tokyo block; retain bounded refinement/failure evidence.
- [ ] T036 Run meaningful regressions and browser checks, record usage/results and remaining work honestly.


T030?T036 implementation evidence: `reports/urban/scene-implementation-results.md`, selected `tokyo-scene-v2`, geometry/placement/material checks, `scene-review-02.json` and browser audit. 49 tests pass. The tasks record implemented mechanisms and an executed assisted experiment; factual/style visual acceptance remains false. Explicit texture rotation is supported; automatic road-segment/curve UV layout is not demonstrated. The new combined evidence stage was assembled after the incremental run, not validated by a second fresh full run.

## Remaining fidelity research gates

- [ ] T037 Resolve multi-level mesh height profiles and footprint/part association without treating OSM tags or sparse maxima as universal building heights.
- [ ] T038 Reconstruct the curved canopy, glazed dome and nonrepetitive museum roof/opening systems; validate source-matched views.
- [ ] T039 Infer/validate road lane topology, crossings, directional paving and curb boundaries from calibrated shared overhead evidence.
- [ ] T040 Demonstrate native img2threejs staged architectural compatibility and a fresh end-to-end run with independent held-out validation.
- [ ] T041 Reach separately accepted factual reconstruction and style correspondence before scaling to adjacent blocks.


## Fidelity/latency diagnosis follow-up

- [X] T042 Profile real API stages and isolate rendering with identical geometry/material/camera ablations; retain six screenshots and a browser comparison page.
- [X] T043 Discover and probe official PLATEAU Chiyoda 2025 building/road sources and inspect actual AOI views; disclose incomplete road texture coverage and an unsettled close view.
- [X] T044 Remove the hardcoded red-museum prescription from generic scene observation prompts; existing results are not regenerated by this change.
- [ ] T045 Replace text-only inferred geometry with camera-associated part measurements, source-guided parameter fitting and representation-specific geometry tools.
- [ ] T046 Expand evidence-driven roof/street material selection, source-local UVs and calibrated outdoor lighting/contact shading; benchmark quality and runtime separately.

Research evidence: `reports/urban/fidelity-and-time-diagnosis.md`. The lighting probe changes no production defaults. Its darker output is not a factual/style acceptance claim. Optional PLATEAU is a geometry/semantic evidence candidate for Japan, not a replacement for globally available provider fallback.


## Global-provider measured compiler experiment

- [ ] T047 Implement bounded Google/OSM measurement capture and calibrated reusable views without PLATEAU dependencies.
- [ ] T048 Compile measured and regularized roof/wall surfaces with stable IDs, depth-tested source projection and explicit fallback coverage.
- [ ] T049 Adaptively capture additional evidence for inadequately covered objects instead of fixed views for every building.
- [ ] T050 Render and inspect matched experimental candidates, benchmark latency and resources, and evaluate a reserved source view.
- [ ] T051 Deliver the selected candidate, comparison viewer, regression evidence and an honest measured report.

## GPT Sol strict refinement revision

- [X] T052 Return critique and code generation to GPT Sol; stop additional Fable requests.
- [X] T053 Add calibrated source-camera rendering and identical target crops, with held-out evidence isolated from repair prompts.
- [X] T054 Implement per-dimension blocking acceptance, bounded target patches, technical validation, rollback and stagnation stopping.
- [X] T055 Execute and visually inspect the bounded pilot; record usage, failed hypotheses and held-out outcome.
- [ ] T056 Extend demonstrated improvements to the remaining buildings and shared street surfaces; achieve whole-block acceptance.

Design and constraints: `strict-sol-revision.md`. Implemented gates do not imply that photographic/style fidelity has passed.

- [ ] T057 Compare single full-AOI code generation against joint scene planning with context-aware modules under identical evidence and cost budgets.
- [ ] T058 Implement observation-first material requests and a retrieval/procedural/source-projection broker; retire reliance on the fallback texture list as an appearance constraint.
- [ ] T059 Validate shared road/sidewalk topology, continuous metric UVs and scene-wide regression after local repairs.

User-directed architecture revision and current implementation boundaries: `scene-first-materials-revision.md`.

T055 evidence: `reports/urban/gpt-sol-strict-results.md`, `runs/urban/tokyo-sol-workflow-review/index.html`, four rejected/stagnated target experiments and one shared-scene diagnosis. 59 tests pass. The final interactive browser audit has zero page errors and confirms that style switching preserves geometry/material identity and that mismatched roof albedo can be disabled while retaining normal/roughness. None of these target runs passed visual acceptance; T056–T059 remain open.

## Implement revised whole-scene workflow

- [X] T060 Generate one AOI program from shared multi-view evidence, numeric scene context and arbitrary style references.
- [X] T061 Remove compulsory texture assets/roles in the new branch; add optional procedural surface tools and shared appearance recipes.
- [X] T062 Implement usable-quality scene critique, joint source/material refinement, technical correction and rollback.
- [ ] T063 Execute, inspect and report actual scene results and held-out outcome; run regressions and interactive browser checks.

## Coordinated node feedback revision

- [X] T064 Separate evidence observer, feature/style critic, work-order routing, coding and technical-validation responsibilities, with persisted node artifacts.
- [X] T065 Supply numerical source-level evidence and registered detail pairs; prevent ignored identity/style features from passing aggregate scores.
- [X] T066 Add tested optional closed-roof/extrusion tools, deterministic context streetscape, and cached shadow invalidation.
- [X] T067 Execute the coordinated loop, inspect input/output artifacts, validate actual improvements and document the reserved-view result.

Contract and known limits: `coordinated-workflow.md`. Successful node plumbing is distinct from accepted visual quality.

T067 evidence: `runs/urban/tokyo-coordinated-v1`, including observer passes, per-feature/style reviews, work orders, coding responses, technical repair, publication recapture and held-out critic. Published source/camera/visibility/PNG hashes pass the evidence gate. Visual acceptance remains false: roofs/materials/style remain weak. `reports/urban/semantic-quality-diagnosis.md` records the actual solid-box chimney failure and the incomplete native img2threejs baseline.

- [ ] T068 Define semantic Scene IR and typed component contracts for cavities, openings, attachments and runtime capabilities; avoid a monolithic free-form city source as the long-term representation.
- [ ] T069 Add generator/semantic regressions for hollow shafts, framed openings, roof assemblies, rail/road connections and fixed-versus-runtime property invariants.
- [ ] T070 Run a native img2threejs baseline on the same bounded subject/input/model/budget before claiming equivalent workflow behavior.
- [ ] T071 Demonstrate a 2×2-cell reuse/continuity/day-night/weather vertical slice and measure accepted-output cost and performance.

Proposed scale architecture and explicit implemented/proposed distinction: `scalable-world-architecture.md`.

Implementation contract: `scene-first-implementation.md`. No quality success is implied by the checked implementation tasks.
