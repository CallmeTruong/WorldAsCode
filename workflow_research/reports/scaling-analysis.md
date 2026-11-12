# Model, cost and small urban-area scaling analysis

Date: 2026-11-11, Asia/Saigon. Derived from the existing three-building smoke benchmark; no new inference calls made for this analysis.

## Actual integration and models

Upstream checkout is `vendor/img2threejs`, pinned at `0c0c49bc168e648dbaf9c8c080474de0b3a941b6`. Adapter: `src/building_workflow/skills.py`. Reused: selected stage guidance, image probe, state/next evidence and real geometry integrity gate. LangGraph, model calls, free code generation, worker execution, renderer and research evaluator are implemented by this project. Native eight-pass strict ObjectSculptSpec baseline is incomplete; existing measurements do not estimate that unimplemented baseline's cost.

Current configured vision/code/refinement/review model is `gpt-6-sol` through `https://api.modelapi.vn/v1`. `gpt-6-luna` was used for one independent pair review. These are gateway request/response IDs; no independent underlying model identity audit was performed. Anthropic credentials are not used by the implemented provider adapter.

## Per-building figures

Means across three direct runs and three repaired-adapter structured runs, each allowing one correction. All results remain partial. Output includes source, scene, geometry checks, rendered views, comparison and review, not certified high fidelity.

| Strategy | Mean input tokens, equivalent uncached | Mean output tokens, equivalent uncached | Mean calls, equivalent uncached | Time | API price estimate |
|---|---:|---:|---:|---|---:|
| Direct | 15,279 | 9,980 | 4.00 | 214.1s mean observed, no local cache | $0.117 |
| Image -> spec -> code | 23,059 | 12,086 | 4.67 | 255.3s reconstructed uncached estimate | $0.150 |

Structured mean observed wall time is 190.5s but includes cache reuse. The 255.3s estimate sums original successful API durations consumed by each run (238.4s mean) and that run's observed deterministic overhead (16.9s mean). It is not a separately measured cold execution. Direct range observed: 186.5-230.9s. Single rendering attempts averaged roughly 7.6-8.3s in these jobs; observed renderer process-tree RSS peak was below 0.73GiB.

## Pricing verification and assumptions

Newly checked the gateway's public pricing API and actual browser model-details page. Snapshot: [pricing-snapshot-2026-11-11.json](pricing-snapshot-2026-11-11.json). Sources: https://modelapi.vn/api/pricing and https://modelapi.vn/pricing.

For `gpt-6-sol`, standard tier base input/output is $2/$10 per million tokens, with public default group multiplier 0.9: **$1.80 input / $9 output per million**. Long tier applies when input length exceeds 272k and has different rates; the tested calls are below this boundary. `gpt-6-luna` standard default-group input/output is $1.80/$10.80 per million.

Price estimates assume the key is billed in default group and all counted prompt tokens are ordinary input (no upstream prompt-cache discount). Local API response cache avoids the request entirely and is handled separately. These are nominal USD estimates, not reconciled ledger charges or the cash paid after recharge discounts.

Structured estimate: `(23059.33 * 1.8 + 12085.67 * 9) / 1e6 = $0.15028/building`.

The entire historical research round consumed 132,350 input and 70,541 output tokens over 30 attempts, including failed integration trials and one Luna review. At the same assumed current public rates, approximate nominal cost is **$0.875**. This is an estimate using current pricing, not a retroactively verified bill. Historical result files keep cost_usd null; their observed data is not overwritten.

## Small-area extrapolation

Assume each building behaves like these structured single-image smoke jobs, one correction, independent references, no local response-cache reuse across unrelated buildings. No data acquisition, manual annotation, quality rework, georeferencing or city-viewer assembly included.

| Buildings | Input/output tokens | Sequential generation | Ideal 4-worker generation | Nominal API estimate |
|---|---|---|---|---:|
| 20 | 0.461M / 0.242M | 85.1min | 21.3min | $3.01 |
| 50 | 1.153M / 0.604M | 212.7min | 53.2min | $7.51 |
| 100 | 2.306M / 1.209M | 425.5min | 106.4min | $15.03 |

Four-worker figures are mathematical division, not measured throughput. Gateway rate limits, output-token throughput, latency variance, contention and retries can make actual time longer. The CLI currently runs individual jobs; no batch scheduler or shared quota governor is implemented. At this projected four-worker rate the average demand is approximately 4.4 requests/minute and 33k total tokens/minute, with burst behavior differing by stage.

## Scaling work still required

1. Data: building IDs, finite batch manifest, reference matching, multi-view input, measured footprints/heights and coordinate provenance.
2. Orchestration: queue, bounded worker pool, global gateway token/request limits, per-building and whole-batch budgets, retry categories and checkpoint recovery.
3. Quality: calibrated acceptance, unseen buildings, repeated trials and explicit unresolved status. Current 6/6 geometry-valid primary configurations do not establish high-fidelity success rate; Fallingwater retains severe errors.
4. City assembly: common metric units, geographic local coordinate conversion, orientation, elevation and footprint collision checks. None implemented yet.
5. Rendering/export: merge compatible geometry or use instancing, LOD and visibility culling; provide model export and a city viewer. Current selected examples contain 100, 778 and 410 meshes (1,284 / 9,660 / 4,920 triangles). Naively scaling to 100 similar buildings gives roughly 10k-77.8k mesh objects, potentially many draw calls, despite modest triangle counts. No city-viewer frame-rate benchmark exists.
6. Storage: full selected example run directories are approximately 6.3-15.7MB each, including source, traces, checkpoint, renders and debug artifacts. At unchanged artifact retention, 100 comparable jobs would use roughly 0.63-1.57GB, excluding dependencies/reference acquisition and additional iterations. Scene.json alone is much smaller. These are simple projections.

The next useful milestone is a 20-building measured batch after completing native baseline compatibility and improving acceptance evidence. Scaling the present system directly would produce a collection of approximate per-building artifacts; it would not yet produce a validated, georeferenced urban reconstruction.
