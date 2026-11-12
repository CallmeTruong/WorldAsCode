# Urban pilot validation — 2026-11-12

> Current selected result: `district1-quality-v10` (220 m AOI, 3 photo-backed targets and 8 context proxies). Descriptive style preserves native materials; fidelity remains partial. See [quality correction results](quality-correction-results.md). Earlier v4/palette/36-building statements below are historical and superseded.

Selected evidence: `runs/urban/district1-final-v4`. Status: functional research pilot, **partial visual fidelity**.

| Check | Observed result |
|---|---|
| Full Python regression suite | `24 passed in 76.65s` using `.venv/Scripts/python -m pytest -q` |
| Python compile | `python -m compileall -q src`, exit 0 |
| Spec Kit prerequisites | `--json --require-spec --require-tasks`, exit 0; feature 002 resolved |
| Dependency audit | `npm audit --omit=dev`: 0 vulnerabilities reported |
| CLI | `urban --help`, exit 0; style folder, object refs, budget and reuse options present |
| Actual source execution | TypeScript compiled; generated source executed in network-denied Chromium worker; real geometry gate passed |
| Building coverage | 36 unique IDs, one owner per building; height contract passed, 32 heights inferred |
| Canonical surface continuity | Clipped-cell union symmetric difference below 1e-6 m²; unique object ownership |
| Material-only comparison | Actual neutral/styled geometry fingerprints equal, same seven camera views |
| Browser interaction | Loaded 36 buildings/350 trees/111 lamps, style switch preserved hash, grid/trees/lamps/landmark/overview controls exercised, zero page errors |
| Browser screenshot inspection | Opened saved overview, street, seam, landmark and interactive viewer preview; significant visual defects recorded in review |
| Credentials in artifacts | 244 source/report/manifest/run text files scanned against configured secret values: zero matches; key values not printed |

Evidence: [viewer checks](../../runs/urban/district1-final-v4/viewer-checks.json), [geometry checks](../../runs/urban/district1-final-v4/urban-geometry-checks.json), [boundary checks](../../runs/urban/district1-final-v4/boundary-checks.json), [performance](../../runs/urban/district1-final-v4/render-performance.json), [resource watchdog](../../runs/urban/district1-final-v4/urban-runtime-resources.json), [visual review](../../runs/urban/district1-final-v4/visual-review.json), [viewer screenshot](../../runs/urban/district1-final-v4/viewer-preview.png).

Tests cover partial/reversed multipolygon rings, courtyard holes, canonical road tiling, alternative style schema, folder bounds, texture hash/path validation, height units, saved real pilot output and cell input/material invalidation. These checks do not establish facade accuracy or production security.

Retained failures include the initial geometry serialization bug and the v5 roof/normals refinement. The latest roof geometry passes technical checks but does not improve the visual candidate; the report points back to v4. No held-out dataset, large-area throughput, measured GPU FPS, mobile-device benchmark, native eight-pass equivalence, terrain validation or independent-cell runtime streaming has passed. Style acceptance by the user is still unmeasured.