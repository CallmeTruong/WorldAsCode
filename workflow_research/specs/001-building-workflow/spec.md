# Feature Specification: Procedural Building Workflow Research

**Feature Branch**: none (workspace has no Git repository)
**Created**: 2026-11-11
**Status**: Accepted for implementation; quality conclusions require experiments
**Input**: docs/wordflow_research.md and user request for public samples, implementation and direct result inspection.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Reconstruct and inspect a real building (Priority: P1)
The researcher selects a publicly sourced building photo and obtains editable reconstruction source, five standard views and a comparison with the original.

**Why this priority**: Proves that the proposed system actually produces inspectable geometry from a real input.
**Independent Test**: Run one real photograph to completion, rerender its saved source, inspect all five images and the original beside the best matching view.
**Acceptance Scenarios**:
1. **Given** a readable sourced image and configured credentials, **When** a bounded job runs, **Then** its workspace contains reference, source, structured observations, mesh checks, five views, usage and review.
2. **Given** only one facade is observed, **When** results are reported, **Then** unseen sides are explicitly inferred and status remains partial until stronger evidence exists.

### User Story 2 - Correct a specific visible error (Priority: P2)
The researcher reviews a baseline and a corrected candidate, including rejected regressions and the reason refinement stopped.

**Why this priority**: Reconstruction quality depends on feedback that changes the actual source.
**Independent Test**: Run baseline and bounded correction on one input; compare retained and rejected candidates with targeted feedback.
**Acceptance Scenarios**:
1. **Given** facade or camera defects, **When** refinement runs, **Then** only explicitly selected source regions change and every candidate is rerendered and reviewed.
2. **Given** invalid geometry or a critical regression, **When** a new candidate is scored, **Then** it cannot replace a valid incumbent merely because of a higher overall score.

### User Story 3 - Compare reproducible experiments (Priority: P3)
The researcher compares direct generation with structured generation across a small diverse development set.

**Why this priority**: Avoid choosing a workflow from one attractive example.
**Independent Test**: Compare the same sourced samples under both strategies, with costs, latency, failures and before/after images.
**Acceptance Scenarios**:
1. **Given** multiple configurations, **When** results are aggregated, **Then** the report retains every trial and separates execution validity from visual quality.
2. **Given** provider pricing is unavailable, **When** costs are displayed, **Then** monetary cost is unknown and token/call counts remain visible.

### Edge Cases
- Unreadable/download-blocked reference: fail with source and retry instructions.
- Timeout/rate limit/malformed response: bounded retries, recorded usage, recoverable failure evidence.
- Unsafe code or runaway generation: reject before execution where possible; isolated execution with deadline otherwise.
- No aligned camera or verified reference mask: silhouette and image metrics unavailable, never fabricated.
- Refinement repeats or degrades: retain best valid candidate and stop within budget.
- No reliable view of the target or no evaluator output: insufficient_evidence/failed, never silently accepted.

## Requirements *(mandatory)*

### Functional Requirements
- **FR-001**: Accept finite local images and a manifest of sourced public samples; no background ingestion.
- **FR-002**: Record image source, author/license when available, crop, checksum and benchmark split.
- **FR-003**: Separate observed features, inferences and unknowns, each with confidence and provenance.
- **FR-004**: Produce editable procedural source, never replace it with a single fixed template or mesh dump.
- **FR-005**: Validate code and actual emitted geometry before rendering; reject nonfinite, empty, invalid or over-budget scenes.
- **FR-006**: Save front/back/left/right/isometric views and a reference comparison per rendered candidate.
- **FR-007**: Produce feature-level visual feedback, severity, likely cause and concrete correction targets.
- **FR-008**: Limit calls, tokens, total time, render time and correction count; preserve durable state and traces.
- **FR-009**: Isolate generated execution from credentials, host files and external network.
- **FR-010**: Retain best valid source and all failed/rejected attempts; do not hide critical defects behind average scores.
- **FR-011**: Compare configurations on identical development samples and label unrun held-out/city phases deferred.
- **FR-012**: Pin external runtime source and disclose any upstream gate not completed.
- **FR-013**: Provide a locally readable experiment report, source rerun instructions and explicit limitations.

### Key Entities
- **Sample**: sourced image, target building, split, metadata and provenance.
- **Observation/BuildingSpec**: hierarchy, repeated features, dimensions, materials, camera and uncertainty.
- **Run**: bounded job, model routing, strategy, checkpoint, prompt/skill versions, usage and status.
- **Candidate**: generated source, emitted meshes, deterministic checks, render set and structured review.
- **Experiment**: identical samples across named configurations, with all results and selection rationale.

## Success Criteria *(mandatory)*

### Measurable Outcomes
- **SC-001**: At least three public real-building samples have provenance and inspectable attempts; at least one completes all artifact stages without mocks.
- **SC-002**: Each rendered candidate has five distinct standard views and reference comparison; saved source can be rendered again without another model call.
- **SC-003**: At least one actual correction is rendered, evaluated and either retained or explicitly rejected using recorded evidence.
- **SC-004**: Same-input strategy comparison reports calls, tokens, elapsed time, validity and feature scores, including failures.
- **SC-005**: All claims identify unobserved geometry; uncalibrated quality scores never certify high fidelity.
- **SC-006**: Runtime checks demonstrate network denial, runaway-code timeout and rejection of invalid geometry.

## Assumptions
- Current scope is the smoke/development research round, not completion of all six long-term phases in the research document.
- Existing credentials authorize finite research API calls. Conservative default limits: 12 calls, 100k tokens, 15 minutes per run, two corrections; the batch is explicit and finite.
- No measured reference dimensions or ground-truth meshes are supplied; size and hidden sides are uncertain.
- Provider gateway may expose only some configured models; verify access rather than invent routing availability.
- Human-calibrated acceptance, segmentation/camera fitting, held-out generalization, city assembly and continuous ingestion remain separate future milestones.
