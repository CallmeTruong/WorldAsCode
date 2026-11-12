# Tokyo revision: provider-backed multi-view reconstruction

## Objective

Validate the same extensible urban workflow on a small Tokyo AOI with actual elevated Google 3D meshes, before increasing object count or area. The target remains editable procedural geometry, with factual geometry evidence separate from user style references.

## Inputs and contracts

- AOI longitude, latitude, size, grid; local OSM snapshot path; automatic UTM zone and hemisphere.
- Existing Cesium ion credential loaded from `.env`, never copied to reports.
- Any style reference folder: content-hashed image set, LLM descriptive extraction, no palette constraints.
- Per-object multi-view manifest: stable OSM ID, images, camera metadata, hashes, provider attribution and visibility limitations.
- Optional overhead canopy observations: lon/lat, confidence and positional uncertainty. Fixed anchors, separate deterministic shape seed.

## Acceptance

1. Inspect actual provider side and overhead images and verify non-flat building meshes. Endpoint availability alone is insufficient.
2. Match the normalized AOI to the correct coordinate system and preserve original footprint holes.
3. Render one photo-backed target plus honest context proxies; inspect front/overhead against multiple factual views. Technical validity and visual acceptance are separate.
4. Seed changes vary tree geometry while preserving anchor coordinates; no invented survey accuracy.
5. Preserve failed source attempts, model usage and review findings. An assisted fix is not an autonomous reliability result.

## Scale design

Area job performs source coverage, canonical roads, spatial indexing and ownership. Object jobs receive local footprints, neighboring context and relevant views, independently cached by source hash. Shared asset libraries and deterministic instancing serve vegetation and street furniture. Style changes invalidate presentation/style-dependent planning only; source updates invalidate affected objects and cells. New areas require their own visibility gate. Runtime streaming, multi-AOI throughput, full photographic texture baking and calibrated image-based fidelity remain future acceptance work.

## Reproduce

From `workflow_research`, run the local reference service:

```powershell
.venv/Scripts/python -m building_workflow.urban.reference_server --port 8767 --longitude 139.76310 --latitude 35.67845
```

Then open `http://127.0.0.1:8767/`. For procedural reconstruction:

```powershell
.venv/Scripts/python -m building_workflow.cli urban --style-dir inputs/style-references/user-isometric --object-refs inputs/object-references/tokyo-multiview-manifest.json --run-id tokyo-multiview-v1 --size 220 --longitude 139.76310 --latitude 35.67845 --grid 2 --osm-snapshot inputs/geography/tokyo-marunouchi/snapshot.osm --tree-observations inputs/object-references/tokyo-museum/tree-crown-candidates.json --max-calls 12 --max-tokens 220000 --max-seconds 1800 --max-visual-refinements 1
```

The existing run is checkpointed. Implementation changes require explicit `--resume-code-update`; changed factual inputs should use a new run ID. Serve `runs/urban` locally on port 8765 to inspect `/tokyo-multiview-v1/viewer.html` and `/tokyo-multiview-v1/index.html` after finalization.
