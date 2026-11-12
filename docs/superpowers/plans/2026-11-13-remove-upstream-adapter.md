# Independent WorldAsCode runtime

> Implement inline using superpowers:executing-plans. User approved removing the adapter and reorganizing reusable code.

**Goal:** Remove the img2threejs runtime dependency and its parallel experimental workflow.

**Architecture:** Keep the measured-evidence → author → browser → critic → refinement/kit lifecycle. Retain geographic checks, physical opening probes, seeds, batching and runtime states. Replace upstream-specific factory signatures/metadata with a small owned `createModel(options)` contract. Do not copy dead upstream schemas or state machines into core.

**Tech stack:** Existing Python, Three.js, Playwright and esbuild; no new service or dependency.

## Constraints

- Preserve historical research, old run artifacts, existing release bytes and user changes.
- No API calls or new grants required. No automatic conversion of old native artifacts.
- Keep generic jobs/storage and active kit functionality; remove only adapter-only code and tests.
- No root initializer restoration. Existing approval to push dev continues.

## Tasks

- [x] T1: Add independent CLI/import/factory tests; observe failures. Remove native/native-pin/status CLI, experimental package, adapter diagnostic, native schema patches and obsolete tests.
- [x] T2: Own factory integration (`createModel`, `origin=factory`, semantic probes by object name); remove upstream-specific renderer metadata and update batching/probe consumers. Verify browser, topology, composition and kit tests.
- [x] T3: Update architecture, README, SpecKit and migration notes. Build a fresh wheel, install outside repo and verify demo plus kit fixtures; run lint/full suite. Review diff, commit and push dev.

## Review focus

No installed upstream files/imports; invalid factory bindings fail; factory metadata cannot bypass physical void checks; existing kit snapshot/release hashes are not rewritten; CLI help reflects removed commands.

## Rulings

- Continue in the existing checkout: preserve the user-deleted initializer and research images.
- Do not retain schema-specific material extraction/compiler helpers as unused core files. The active workflow already handles procedural styled materials and review; geometry probes and footprint checks remain.
- Old `origin=native` artifacts remain historical and require explicit conversion to the owned factory contract; no silent relabeling.

- T1/T2 evidence: independent contract tests were observed failing against old CLI/imports/signature. Owned plain-JS factory, missing-map rejection, named probes, placement/seed and filled-hole checks now covered. A scaled-factory probe failed before correcting local-to-world length. Full verification pending.

- Final: 105 tests passed (no skips), Ruff check/format and JS syntax passed. Fresh wheel inspected and installed into a new venv, executed with -I outside repo: CLI help/doctor/demo, three subprocess kit fixtures and two-instance factory compose passed. Independent reviewer found a Mesh root naming collision; reproduced with a red browser test, corrected and reviewed again with no blockers. See docs/operations/independent-runtime-validation.md.
