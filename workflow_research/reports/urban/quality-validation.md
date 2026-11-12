# Quality correction validation

Selected result: `district1-quality-v10`, 2026-11-12. Technical validity passed; **visual acceptance remains false**.

| Check | Evidence |
|---|---|
| Full regression suite | 34 passed in 44.70s; run without concurrent urban GPU rendering |
| Initial concurrent test run | Two legacy renderer timeouts; retained as resource contention evidence, no timeout inflation |
| Real generated source | TypeScript compile, restricted worker execution and img2threejs geometry gate passed |
| Exact geometry sharing | Regression verifies equal geometry deduplication, distinct material/transform preservation and baked attribute rotation |
| Object coverage | 11 IDs, 3 photo-backed candidates and 8 explicit proxies; unique ownership |
| Style extraction | Descriptive profile without palette, color thresholds or material overrides |
| Geometry/material invariants | Both unchanged across neutral/reference presentation in actual runtime and interactive browser |
| Surface binding | Tile albedo retained; painted plaster retains intrinsic material color with normal/roughness maps |
| Interactive controls | Presentation, grid, trees, lamps, all three target selections and overview exercised; zero page errors |
| Final static checks | Python compile, worker/viewer JavaScript syntax and Spec Kit prerequisites passed |
| Artifact scan | 548 source/report/input/run text files checked against configured credential values: zero matches; delivery document links resolved |
| Direct visual inspection | Actual overview and individual renders opened; Caravelle glazing occlusion fixed using scene raycast; identity/ornament defects remain |
| Final render | 189.4 s, peak RSS 1,167 MB, 341 draw calls, 133,619 visible triangles at overview |
| CPU timing | Styled median 6.4 ms, p95 8.9 ms; not GPU completion or guaranteed FPS |

Artifacts: [runtime](../../runs/urban/district1-quality-v10/urban-runtime-result.json), [geometry gate](../../runs/urban/district1-quality-v10/urban-geometry-checks.json), [browser](../../runs/urban/district1-quality-v10/viewer-checks.json), [resources](../../runs/urban/district1-quality-v10/urban-runtime-resources.json), [quality review](../../runs/urban/district1-quality-v10/quality-review.json), [source corrections](../../runs/urban/district1-quality-v10/source-history/), [API totals and caveats](quality-experiment-metrics.json).

Tests also cover factual image content hashing, referenced-object/furniture dependency changes, 18-edit object patches with unique anchors, actual gate errors surviving evidence summarization, code-only resume preserving inputs/budgets, final-module synchronization and all previously existing building-workflow checks.

No factual top-down roof imagery, calibrated camera/metric fidelity, large-area performance, native eight-pass equivalence, terrain or production streaming is established. Scene screenshots and test passes do not establish survey accuracy or user acceptance. Reproduction uses the CLI in the feature quickstart; the final validation run reused already observed/generated modules and therefore is not a cold-start experiment.
