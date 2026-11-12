# WorldAsCode System Refactor Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task. Execute inline; preserve user changes.

**Goal:** Install and run WorldAsCode independently of research directories while preserving reconstruction and kit workflows.

**Architecture:** Namespace Python package with grouped modules, explicit data/resource/toolchain paths, versioned policies and shared contracts. One canonical CLI/package; research inputs/releases remain historical artifacts.

**Tech Stack:** Existing Python/Pydantic/Playwright/Three.js/esbuild; JavaScript AST analysis through a pinned parser.

**Spec:** `docs/architecture/system-refactor.md`

## Global Constraints

- Do not recreate the user-deleted `src/worldascode/__init__.py`.
- Never rewrite existing content-addressed kit releases or implicitly migrate grants.
- No provider calls required for code relocation validation; paid requests are not retried.
- New runtime must not import application code from either research directory.
- Preserve historical research; document optional native adapter separately.

## Review Focus

1. Run after installation from unrelated cwd, with no research directory present.
2. Explicit missing stable channel must not silently resolve builtin.
3. Interrupted provider review cannot become quality acceptance or lose usage.
4. JS method parsing must survive formatting/comments and retain wall guards/dependencies.
5. Packaged render resources and Node dependencies must be available in an installed wheel.

## Tasks / deliverables

- [x] T1: Add tests for path settings, status/CLI outcomes, strict kit resolution and external imports; observe failure before implementation. Run original suite as baseline.
- [x] T2: Transfer module groups/resources, configure root packaging/toolchain, introduce namespace entrypoint without forwarding shims. Verify imports and test suite.
- [x] T3: Extract AI nodes, quality policy and regression worker; normalize outcomes and use explicit paths/cache manifests. Verify mocked workflow, recovery and permission tests.
- [x] T4: Package Cesium reference service and capture profile; make upstream explicit optional. Verify local HTTP behavior without exposing token.
- [x] T5: Implement AST-backed method/dependency extraction and versioned kit manifests; keep legacy release adapter. Verify formatting/dynamic-access rejection and protected code checks.
- [x] T6: Build/install wheel in clean environment, run browser smoke and baseline render, run tests/lint, update migration/operation docs and SpecKit, commit reviewable result.

## Execution ledger

- Initial state: branch dev at f1ea378; user deletion of root initializer and untracked imagery untouched.
- Ruling: Work in current checkout, preserving user changes — moving credentials and historical runs to an isolated worktree would complicate the explicitly requested root migration; commit only task-owned paths.
- Ruling: Historical research remains on disk. Latest user steering removes forwarding shims and merges tiny modules by responsibility; worldascode.toml/config.py own configuration.

- Final verification: 117 tests passed with explicit optional upstream, Ruff check/format passed (72 files), Node syntax check passed. Final wheel installed non-editably and executed with Python -I from unrelated cwd: doctor, demo and subprocess kit fixtures all passed. See docs/operations/refactor-validation.md.
