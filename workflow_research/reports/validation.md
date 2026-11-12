# Validation evidence

Validated locally on **2026-11-11, Asia/Saigon**, Windows, Python 3.13.15, Node 24.19.0 and Chromium 158.0.8127.18. Dependencies are captured in `requirements.lock.txt` and `package-lock.json`.

## Checks executed

| Check | Observed result |
|---|---|
| `.venv/Scripts/python -m pytest -q` | **15 passed in 26.90s** on the final implementation |
| `.venv/Scripts/python -m compileall -q src scripts` | Completed successfully |
| `npm audit --audit-level=low` | **0 vulnerabilities** after pinning esbuild 0.28.2 |
| `python .specify/scripts/python/check_prerequisites.py --json --require-tasks --include-tasks` | Resolved feature and all research/design/task artifacts |
| `building_workflow.cli doctor` | Selected model available; real browser launched with Chromium sandbox; exact upstream commit verified |
| API end-to-end experiments | Six primary sample/strategy combinations produced usable artifact sets; extra camera experiment completed; three earlier failed integration runs preserved |
| Saved source rerender | `render runs/smoke-rietveld-camera/iteration-01/generator.ts runs/rerender-rietveld` succeeded: 100 meshes / 1,284 triangles |
| Pixel reproduction | Front/back/left/right/isometric/reference-view PNGs all **byte-identical** to saved originals; no API call |
| Completed run replay | Same run ID/config returned existing result; usage unchanged and original config preserved |
| Real browser report check | Aggregate table has 10 run rows; Bauhaus report has 12 loaded images and **0 broken images** |
| Credential artifact scan | 413 text artifacts/source files scanned against configured key values; **0 matches**; actual keys never printed |

## Meaningful test coverage

The tests execute real Chromium/Three.js and the pinned upstream geometry code. A generated factory must emit actual measurable geometry and nonblank screenshots; test fixtures are explicitly synthetic boundary checks, not research reconstruction evidence.

- Reject missing/NaN rubric scores and unsafe source capabilities.
- Reject non-unique patch anchors.
- Preserve provenance through explicitly supported response-key aliases.
- Persist call-budget consumption across Provider recreation; unknown monetary price remains null.
- Prevent critical-defect/feature regressions from winning by a higher average score.
- Check actual closed BoxGeometry, five standard rendered views and distinct perspective output.
- Reject an open triangle through the actual upstream watertight gate.
- Verify architectural blade-wall names do not invoke a weapon-specific thickness rule while preserving topology checks and source part mapping.
- Terminate an infinite-loop generator through the process deadline.
- Deny obfuscated browser fetch under CSP/request denial.

## Direct visual inspection

Opened all three accepted source photos before final selection. Rejected the Villa Savoye interior-chair image and replaced it with the inspected Fallingwater exterior. Opened saved before/after comparison images for all six primary configurations plus camera-only variant; inspected five-view sheets of selected models. Opened the generated HTML report in Chromium and inspected [dashboard screenshot](dashboard-preview.png) and [run screenshot](run-preview.png).

Visible limitations confirmed: simplified/blank unobserved sides, wrong facade/massing proportions, overly regular Fallingwater stacking, camera hypotheses rather than calibrated matching and simplified materials. These are preserved in the [findings](findings.md), not hidden behind successful compilation.

## Limits of these checks

No high-fidelity certification, held-out benchmark, geometry ground-truth comparison, verified silhouette/SSIM, exact monetary cost, city assembly, GPU/VRAM profiling or production multi-tenant hard-quota security validation was performed. Process-tree RSS includes the renderer subprocess and browser; it does not profile total workstation memory or model-provider resources.

All retained reconstructions remain **partial**. Upstream canonical eight-pass/strict ObjectSculptSpec baseline remains **incomplete** and its state has not been marked complete. The 15 tests prove software boundaries and reproducibility of this local research adapter, not reconstruction accuracy.
