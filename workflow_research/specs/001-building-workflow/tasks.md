# Tasks: Procedural Building Workflow

## Phase 1: Setup
- [X] T001 Record architecture investigation and source pin in specs/001-building-workflow/research.md.
- [X] T002 Configure dependencies, secret exclusions and environment loading in pyproject.toml, package.json and src/building_workflow/config.py.

## Phase 2: Foundation
- [X] T003 Implement bounded API calls, retries, durable usage and cache in src/building_workflow/provider.py.
- [X] T004 Define validated observations/reviews and candidate acceptance in src/building_workflow/models.py.
- [X] T005 Adapt pinned skill context, image probes and real geometry gate in src/building_workflow/skills.py.

## Phase 3: US1 - Real reconstruction (P1)
Independent test: one sourced photo -> generated factory -> mesh gates -> five inspected views and comparison.
- [X] T006 [US1] Download three attributed real references in src/building_workflow/samples.py and data/samples.json.
- [X] T007 [US1] Implement isolated worker, trusted scene renderer and watchdog in runtime/ and src/building_workflow/runtime.py.
- [X] T008 [US1] Implement checkpointed reconstruction graph and CLI in src/building_workflow/workflow.py and cli.py.
- [X] T009 [US1] Verify real end-to-end generated artifacts under runs/.

## Phase 4: US2 - Targeted correction (P2)
Independent test: a real correction changes source, rerenders and is retained or rejected with evidence.
- [X] T010 [US2] Implement reference/render structured evaluation in src/building_workflow/workflow.py.
- [X] T011 [US2] Implement exact-region patches, best-candidate retention and bounded stopping in src/building_workflow/workflow.py.
- [X] T012 [US2] Exercise browser isolation, invalid geometry and budget recovery in tests/test_core.py and tests/test_runtime.py.

## Phase 5: US3 - Experiment comparison (P3)
Independent test: identical sample ids across direct/spec strategies, all attempts included.
- [X] T013 [US3] Produce local visual reports and comparative plots in src/building_workflow/report.py.
- [X] T014 [US3] Execute real same-input strategy trials on public samples under runs/.
- [X] T015 [US3] Inspect saved comparisons and views; record findings and limitations in reports/findings.md.

## Phase 6: Validation and documentation
- [X] T016 Run required checks and record tested commands/results in reports/validation.md.
- [X] T017 Document measured recommendation, uncompleted native baseline and future research in README.md and reports/findings.md.

## Dependencies and Execution
T001-T005 -> US1 -> US2 -> US3 -> validation. Downloads and runtime implementation may proceed independently once the schemas are fixed; this round uses sequential implementation. Deliver an inspectable real run first, then compare strategies. Development smoke evidence does not satisfy held-out or city-pilot phases.

## Completion evidence

Bounded research-round tasks completed; see reports/validation.md and reports/findings.md. This does not mark the long-term native baseline, held-out benchmark or city phases complete. No .specify/extensions.yml exists, so pre/post extension hooks were not applicable.
