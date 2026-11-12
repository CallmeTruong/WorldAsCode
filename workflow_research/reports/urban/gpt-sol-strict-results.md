# GPT Sol strict-loop experiment ? 2026-11-12

Outcome: GPT Sol restored for observation, code and critique, using the existing configured base URL. No new Anthropic requests. Full-block fidelity remains **not accepted**.

Implemented matched source-camera crops, local footprint/edge/camera packets for repair, six-dimensional blocking acceptance, one bounded technical correction, held-out checks, transactional source rollback and runtime checkpoint restoration with source-hash verification. New strict runs disable automatic transport retries. Source material roles may extend the manifest, and individual materials may retain normal/roughness while opting out of inappropriate library albedo.

## Actual findings

- v1 and v2: proposed arch relief generated degenerate geometry. The technical agent's first attempted interval fix was itself arithmetically incorrect; both candidates were rejected. A host correction to subdivision arithmetic was explicitly recorded in v3 seed provenance. Do not call these autonomous successes.
- v3: material tint and roof proportions changed, but further local embellishment failed to demonstrate score improvement and was rolled back. The source still has oversimplified roof topology and facade repetition.
- v4: supplying actual local coordinates and camera poses did not by itself solve the reconstruction. A candidate lost detail and was rejected. The retained scene is a stable demonstration, not an accepted reconstruction.
- Some critiques confused shared/neighbor courtyard space inside a rectangular crop with the target component, or risked interpreting photogrammetry voids as actual passages. The latest prompt separates shared scene issues and requires corroboration of source holes. This prompt hardening followed the experiments and has not been validated by another full run.
- Dense measured/photo-projected variant was rejected after direct inspection: uncovered walls/ground and distorted roofs, with approximately 68?78% building-area texture coverage. Reusable calibrated images remain useful; that surface compiler is not the selected production geometry route.
- One new whole-area GPT Sol diagnosis used overhead/west/south imagery, current full-scene overhead, style reference and an OSM identity diagram. It identified shared courtyard ownership, road/sidewalk continuity, varied roof topology and source-shadow ambiguity as scene-level concerns. These are model observations/hypotheses, not independently measured truth or proof that full-AOI generation wins.

## User-directed architecture conclusion

Observe the whole area first and maintain one shared scene graph. Use modules for code/patch ownership, not isolated observation. Describe observed material requirements before retrieval or procedural/source-projection choices. A fixed fallback texture list must not be treated as factual appearance. The autonomous material broker and budget-matched full-AOI versus hierarchical generation experiment are still required; see `specs/002-urban-grid-style/scene-first-materials-revision.md`.

## Reproduction

```powershell
$env:PYTHONPATH='src'
.venv/Scripts/python scripts/run_strict_urban.py --run-id NEW_RUN_ID --object-id way/306116935/0 --repairs 1 --parent runs/urban/tokyo-sol-strict-v3 --components-parent runs/urban/tokyo-sol-strict-v3
```

Use a new run ID; the current implementation includes later prompt/checkpoint improvements and is not byte-for-byte the initial v1 experiment. Generic CLI `urban-refine --run PREPARED_ISOLATED_RUN --evidence CALIBRATED_EVIDENCE_DIR --object-id ID` supports a prepared scene without Tokyo-specific provider requirements.

## Recorded usage

```json
{
  "model": "gpt-6-sol",
  "anthropic_requests": 0,
  "experiments": [
    {
      "run": "tokyo-sol-strict-v1",
      "status": "technical_rejection",
      "accepted": false,
      "calls": 3,
      "cache_hits": 0,
      "input_tokens": 13638,
      "output_tokens": 4236,
      "api_seconds": 123.918,
      "active_seconds": 461.606,
      "cost_usd": null
    },
    {
      "run": "tokyo-sol-strict-v2",
      "status": "technical_rejection",
      "accepted": false,
      "calls": 1,
      "cache_hits": 3,
      "input_tokens": 7195,
      "output_tokens": 899,
      "api_seconds": 39.405,
      "active_seconds": 274.923,
      "cost_usd": null
    },
    {
      "run": "tokyo-sol-strict-v3",
      "status": "stagnated",
      "accepted": false,
      "calls": 4,
      "cache_hits": 0,
      "input_tokens": 18784,
      "output_tokens": 5286,
      "api_seconds": 118.355,
      "active_seconds": 428.165,
      "cost_usd": null
    },
    {
      "run": "tokyo-sol-strict-v4",
      "status": "stagnated",
      "accepted": false,
      "calls": 4,
      "cache_hits": 0,
      "input_tokens": 25287,
      "output_tokens": 6959,
      "api_seconds": 155.805,
      "active_seconds": 363.76,
      "cost_usd": null
    },
    {
      "run": "tokyo-sol-scene-context-v1",
      "status": "scene-wide diagnosis only",
      "accepted": false,
      "calls": 1,
      "cache_hits": 0,
      "input_tokens": 19653,
      "output_tokens": 2734,
      "api_seconds": 62.248,
      "active_seconds": 62.76,
      "cost_usd": null
    }
  ],
  "total_calls": 13,
  "total_input_tokens": 84557,
  "total_output_tokens": 20114,
  "total_api_seconds": 499.731,
  "cost_usd": null,
  "note": "Incremental target experiments and one scene diagnosis; not full-neighborhood regeneration or a city-scale benchmark."
}
```

Dollar cost is unknown without gateway rates. Counts exclude cached replay tokens and do not assert unmetered requests are free. Per-run active time includes local render work; summed API time is not overall elapsed time. A small target experiment is not a city-scale throughput benchmark.

Verification: 59 tests passed; direct image inspection included source/render pairs and rejected measured geometry. Interactive browser audit is recorded separately in the final run.
