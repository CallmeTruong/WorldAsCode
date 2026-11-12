# Procedural Building Research Constitution

## Core Principles

### I. Evidence before claims
Only measured runs and inspected images support conclusions. Compilation alone is not reconstruction success. Missing views and ground truth remain unknown.

### II. Reconstruction by code
Generate editable procedural geometry from real references. No fixed building template may replace free code generation. Preserve geometry when changing style.

### III. Bounded execution
Generated code never receives secrets, host filesystem access or network access. Enforce per-call, per-render and per-run limits. Record failures and stop on repeated errors.

### IV. Reproducible research
Keep source provenance, skill commit, prompts, models, usage, timing, specs, generated code, views, reviews and every attempted candidate. Never discard failed trials from comparisons.

### V. Measured complexity
Use a small stateful workflow first. Add agents or optimization only with evidence. Compare identical inputs; separate development from held-out validation.

## Constraints
LangGraph orchestrates direct model APIs and local tools. No coding-agent CLI in the reconstruction runtime. Secrets stay in the existing parent .env and never enter reports or generated execution. Unknown monetary pricing is null, never zero.

## Development Workflow
Research upstream source, specify, plan, implement, run deterministic and integration checks, inspect actual renders, then document limits. Runtime errors require evidence and recovery strategy. Custom acceptance thresholds remain exploratory until calibrated.

## Governance
The user's scope controls the current research round: finite public samples, no continuous ingestion. Scope changes and deferred long-term phases must be explicit. Changes to these principles require a versioned rationale.

**Version**: 1.0.0 | **Ratified**: 2026-11-11 | **Last Amended**: 2026-11-11
