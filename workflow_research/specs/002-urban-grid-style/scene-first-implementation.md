# Scene-first implementation, approximate materials

User direction: implement the revised pipeline; remove compulsory texture choices and exact texture fidelity, let the agent observe, evaluate and improve the scene to a usable quality level.

## Implemented architecture

`urban/scene_first.py` generates a single complete TypeScript scene from five shared Google 3D Tiles views, the actual style-image folder, OSM identity diagram, all footprints/heights, road network and camera metadata. Building IDs remain anchors for placement and diagnostics; they are not independent generation jobs. The generator reasons about roof systems and shared spatial relationships together. Existing roads, pavement, crosswalks and seeded vegetation remain shared host-owned infrastructure.

No previous building code, Poly Haven texture catalog, compulsory texture roles or inferred texture colour multipliers are inherited. The per-run asset registry is empty. Agent-authored MeshStandardMaterials may use any approximate observed colours and physical properties. Optional surface recipes provide procedural brick/slate/paving/asphalt/grass/noise at metric scale; they are convenience tools, not a required library. Flat painted surfaces, glazing, metal and geometric detail are also valid. The trusted renderer creates optional bitmap maps; generated code remains network-isolated. Shared streetscape recipes control appearance consistently across the AOI.

After rendering, GPT Sol sees matching source/output camera pairs and the style reference. It assesses layout, identity, roofs, streetscape, materials, style and coherence. 3/5 means usable with simplifications, 4 good, 5 excellent. Acceptance requires every dimension >=3, mean >=3.5, and no major or critical visible fault. Minor texture mismatches and unknown hidden details are explicitly acceptable. Scores are qualitative, not calibrated accuracy measurements.

The same scene agent patches the complete program and shared material recipes. A bounded technical correction uses compile/geometry/placement feedback when necessary. Runtime checkpoints restore the exact previously validated scene and screenshots if a candidate regresses. Held-out camera evidence is supplied only for final evaluation. The pilot allows two scene refinement rounds, at most ten API attempts, 300k recorded/reserved tokens and a 2100-second provider-active budget. All calls use GPT Sol through the configured base URL. Dollar cost requires configured gateway rates.

Follow-up mechanisms: optional `--seed-scene` reuses a previously jointly generated program without another generation request. `--expanded-context` rebuilds shared streets/pavements from the original OSM snapshot in a buffer covering the complete target footprints, preserving the original target building set. Known conflicts between tagged heights and sparse roof measurements become explicit bounded height envelopes; the agent can interpret multi-level parts instead of being forced to flatten the entire building. The original tag and conflicting evidence remain recorded. This is not a surveyed height correction or permission to stretch the whole footprint uniformly.

Scene critique uses projected object-ID labels and the OSM diagram to distinguish target buildings from unmodelled background towers. Labels are registration annotations, not measured source geometry. Refinement additionally receives up to three cached target-specific detail views selected from the current major-defect owners. These close views inform changes to the same joint scene program; they do not launch independent reconstruction jobs. Unknown background structures are not reassigned to low target buildings because of a visual resemblance.

## Scope and constraints

The current pilot uses the existing small Tokyo AOI and cached Google/OSM evidence. Its source views have blur, shadows and photogrammetry holes; these are not automatically physical passages or black materials. Building footprints and host placement remain checked; approximate materials do not waive geometry integrity. This experiment does not demonstrate city-scale throughput, road topology outside the AOI, surveyed facade accuracy or success on another city. Style remains an arbitrary input image folder, separate from factual data.

## Reproduce

```powershell
$env:PYTHONPATH='src'
.venv/Scripts/python scripts/run_scene_first_urban.py --run-id NEW_SCENE_RUN --parent tokyo-sol-strict-v4 --evidence tokyo-measured-v1 --repairs 2
# Reassess/refine an existing scene with buffered OSM streets and conflicting-height evidence:
.venv/Scripts/python scripts/run_scene_first_urban.py --run-id NEW_REFINEMENT_RUN --parent tokyo-scene-first-v1 --seed-scene --expanded-context --repairs 2
```

Results, per-round source/output pairs, source code, decisions, technical failures and usage are written into the new run folder. `scene-first-result.json` reports both training and held-out acceptance. A valid Three.js render alone is not visual acceptance.
