# Workflow system extraction

Status: implemented; see [validation](../../docs/operations/refactor-validation.md).

## Problem

The research package mixed writable state, packaged resources, orchestration, provider capture and kit lifecycle. Repo-relative paths and forwarding modules would make deployment and maintenance fragile.

## Requirements

1. Install `worldascode` independently of either research directory.
2. Group code by responsibility without one-file forwarding layers.
3. Centralize editable endpoint/model/routing/budget/capture/path settings in TOML; keep secrets in environment or an explicit dotenv file.
4. Keep model author/reviewer/kit developer nodes inside the workflow; preserve measured evidence and quality contracts.
5. Preserve release hashes and protected methods; require host grants for shared publication. Load relevant kit context only.
6. Distinguish execution completion from visual quality acceptance; retain failure tracebacks and accounting.
7. Package rendering/capture resources; run independently of img2threejs, upstream scripts, skills and locks. Support owned Three.js factories through an explicit createModel contract.
8. Validate with mocked providers, existing regression tests, isolated wheel installation and real browser fixtures.

## Scope and limits

This is a system refactor, not evidence of improved city reconstruction quality or distributed execution. Existing research remains immutable history. No implicit migration of old grants or releases. Node dependencies and Chromium remain deployment prerequisites.

## Acceptance

See [architecture](../../docs/architecture/system-refactor.md), [implementation plan](../../docs/superpowers/plans/2026-11-13-system-refactor.md), and [tasks](tasks.md).
