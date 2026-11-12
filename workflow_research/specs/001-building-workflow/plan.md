# Implementation Plan: Procedural Building Workflow

**Branch**: none | **Date**: 2026-11-11 | **Spec**: [spec.md](spec.md)

## Summary
Build a finite research CLI: download three real references with attribution; LangGraph routes vision/spec, free procedural code generation, isolated geometry emission, deterministic gates, real Three.js rendering, structured review and bounded targeted corrections. Produce inspectable local HTML evidence and a measured strategy comparison.

## Technical Context
**Language/Version**: Python >=3.11 (local 3.13); Node >=20; browser ES modules/TypeScript.
**Primary Dependencies**: LangGraph, SQLite checkpointer, HTTPX, Pydantic, Pillow, NumPy, Playwright, Three.js, esbuild, TypeScript.
**Storage**: per-run artifacts, SQLite graph checkpoints, content-addressed API cache and append-only JSONL traces.
**Testing**: pytest for budgets/schema/selection and actual browser isolation/geometry/render integration; real API smoke runs.
**Target Platform**: Windows research workstation; portable Python/Node runtime.
**Project Type**: CLI and static local evidence report (no hosted site).
**Performance Goals**: bounded 15-minute job, 30-second generated execution, 50k-triangle and 1200-mesh ceilings; measure latency rather than assert it.
**Constraints**: no secrets in generated code; no generated Node execution; browser sandbox and network denial. Docker engine unavailable locally. One observed photo cannot prove exact 3D.
**Scale/Scope**: three development smoke samples; direct vs structured generation and up to two corrections. Held-out validation and city assembly deferred.

## Constitution Check
Pre-design and post-design: PASS with explicit limits. Code generation is unconstrained procedural Three.js, not a fixed parametric building template. Geometry and render gates run before visual review. All candidates retained; selection requires no critical regression. Monetary cost remains null unless configured prices exist. Upstream eight-pass completion is separately tracked and never claimed by the research adapter.

## Project Structure
```text
specs/001-building-workflow/{spec,plan,research,data-model,quickstart,tasks}.md
specs/001-building-workflow/contracts/cli.md
src/building_workflow/{cli,config,models,provider,samples,skills,runtime,workflow,report}.py
runtime/{bundle,worker,viewer}.mjs
tests/test_core.py
tests/test_runtime.py
data/samples.json
runs/<run-id>/                 # generated artifacts, ignored
reports/                      # durable research findings
vendor/img2threejs/            # pinned checkout, ignored
```
**Structure Decision**: One Python package and a trusted browser worker/viewer. LLM code is transformed without execution and bundled against only Three.js; it emits data in an isolated worker. The trusted viewer renders a validated serialized scene. API credentials remain solely in the Python process.

## Research Decisions
Use the configured compatible gateway after capability probing. Keep stage-level model routing optional. Reuse upstream image probe, state/next evidence, local-search context and actual geometry_integrity gate. Use an explicit building schema, not a falsely claimed ObjectSculptSpec. Preserve upstream strict validation and incomplete status as evidence until a full canonical baseline is implemented. No fabricated IoU/SSIM before segmentation and camera alignment.

## Complexity Tracking
Browser execution supplies a local isolation boundary without a running Docker daemon. It does not substitute for a production hardened container with OS resource quotas. Local prototype is bounded by process watchdog and scene limits; production multi-tenant service remains outside scope.
