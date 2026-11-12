# Urban research CLI contract

Proposed implementation entry: `.venv/Scripts/python -m building_workflow.cli urban --style-dir PATH --run-id district1-pilot`.

Input defaults: previously saved OSM AOI snapshot, locally bounded coordinates and per-object metadata; user style directory explicit; no hardcoded reference palette. Missing/broken references error, absent style path uses neutral.

Outputs: `runs/urban/<id>/city.json`, `style-profile.json`, `style-references.json`, `style-contact-sheet.jpg`, generated `building-generator.ts`, sandbox-generated `buildings-scene.json`, geometry/boundary reports, trusted texture registry, neutral/styled render views and performance measurements, API prompts/responses/usage and local interactive viewer/report.

Generated code: `import * as THREE from 'three'; export function build(params:any={})`. Receives pure city data; returns building Object3D hierarchy. No URLs/network/host APIs; dedicated worker and request denial; geometry-only return, no arbitrary image/texture loading. Trusted renderer separately adds canonical OSM-derived roads/vegetation/lights and resolves licensed local textures.

Scene IDs/positions/footprints/floors and code-generated geometry remain identical between neutral/styled. Material bindings refer to semantic IDs. City metadata and stylization are not factual facade evidence. Missing data and synthesized decorations remain inferred.

Local viewer served only on loopback; no main Cesium/LLM token is embedded in assets. Provider model and spend estimates are reported separately from charges. Session only performs explicit finite operations; no continuous input or public deployment.


Implemented additions: `--object-refs inputs/object-references/manifest.json` maps factual photos to stable object IDs; `--reuse-run-id ID` reuses an existing API-authored parameterized source in a new experiment; `--rerender` reexecutes checkpointed graph with same configuration. Run with changed inputs must use a new ID. Scene currently assembled globally with per-cell ownership/manifests; no claim of cell-level streaming implementation.
