# Evidence-compiled massing

Date: 2026-11-12. Subject of the measurements: Mitsubishi Ichigokan Museum (`way/306116935`), Tokyo Marunouchi snapshot.

## Why earlier runs did not look like the building

Runs v2 to v8 asked a language model to author coordinates (a component tree, then TypeScript edits) and compared one render against one screenshot through a searched camera. Three things followed.

1. **Geometry was written, not derived.** The footprint, heights and roof were prose in a prompt. A correction could move a wing (v7) and nothing structural prevented it.
2. **The comparison camera was a guess.** The silhouette score mixed camera error with shape error, so the correction loop had no reliable gradient. Blockout never passed in six attempts.
3. **Only screenshots were used.** The photogrammetric surface behind those screenshots has heights. A silhouette constrains an outline; it cannot place a ridge, a hip or a tower.

## What the workflow does now

| Stage | Input | Output | Model calls |
|---|---|---|---|
| Evidence bundle (`georef.build_evidence`) | OSM outline, capture manifest, views | Metric footprint, one camera per view, scope masks | 0 |
| Parametric fit (`massing.fit`) | Bundle | Registration, total height, roof form, eave line | 0 |
| Detail parameters (`pipeline.author_details`, optional) | Views + fitted facts | Storeys, bay spacing, window proportions, dormer/chimney spacing, sunlit colours | 1 |
| Height field (`dsm.capture`, optional) | Running reference viewer | Grid of surface heights in the footprint's principal frame | 0 |
| Roof planes (`dsm.fit_roof`) | Height grid | Planes with rectangular plan regions | 0 |
| Compile (`massing.compile_parts`) | Programme (+ roof planes) | World IR: `loft` walls and trim, `roof_planes` or parametric roof | 0 |
| Review (`pipeline.run_massing`) | World IR | Renders through each evidence camera, per-view IoU, difference images | 0 |

The model can only fill whitelisted programme fields, each validated by the schema. It cannot return a coordinate. `--program` overrides are restricted to the same detail fields.

Cameras come from the capture's recorded position and look-at target plus the capture SDK's default frustum. They were audited by drawing the footprint at ground and roof height over each view. The browser renders with the same pose (`worldscale.pose`), so reference and render share one projection. Browser IoU and the Python rasteriser used for fitting differed by at most 0.005 on the parametric model.

## Measured results on the museum

Scores are silhouette IoU against the scoped reference in the four oblique evidence views. The earlier numbers used a searched camera and are not strictly comparable; they are listed because they were the acceptance signal at the time.

| Run | Roof | Mean IoU | Min IoU | Triangles | Model tokens |
|---|---|---|---|---|---|
| `native-museum-v2` attempt 0 | model-authored | 0.307 (one view, searched camera) | n/a | 5,224 | 153,904 + 194,037 unknown reserve |
| `museum-v8-fixed-frame-preview` | model-authored, wings re-posed | 0.486 (one view, searched camera) | n/a | n/a | inherited |
| `massing-ichigokan-v1` | parametric fit | 0.885 | 0.852 | 76 | 0 |
| `massing-ichigokan-v3` | parametric fit + detail parameters | 0.881 | 0.837 | 1,162 | 10,609 |
| `massing-ichigokan-v6-measured-roof` | planes from height field | 0.923 | 0.892 | 6,132 | 10,609 (cached reply) |

Height-field statistics for v6: 10,848 samples at 0.6 m in 94 s; 185 planes, 637 rectangles; mean absolute error 0.15 m and 90th percentile 0.33 m against the samples; 85 cells of a neighbouring tower removed; plane fitting took about 1 s. A full massing run took 65 to 110 s, most of it browser capture.

Direct inspection of `runs/massing-ichigokan-v6-measured-roof/evidence-contact-sheet.jpg`: the L plan, wall height, steep slate slopes, hip ends, ridge, dormer and chimney positions agree with the views. What is still wrong:

- Roof edges are stepped at the 0.6 m grid, and small planes add clutter that the real roof does not have.
- Faces above the eave all use a roof-side material. Brick gable ends and tower walls are not distinguished.
- Walls are one flat plane per footprint edge with a repeated window tile. Projecting bays, the entrance, arches, quoins and storey differences are absent.
- The OSM outline has six vertices; the west end is about 1 m too long after registration.
- Wall colour is a vision estimate because the facades are in baked shadow. Roof colour is sampled.
- `accepted` stays false. The 0.85 / 0.75 thresholds gate massing only and are provisional until calibrated on more buildings.

## District draft

`worldscale district` compiles every closed building way of an OSM snapshot in one metric frame. Buildings with a fitted run use it; the rest get a programme from tags. On the Marunouchi snapshot: 14 buildings, 1 fitted, 0 model calls, 36 s including capture (`runs/district-marunouchi-v1`). Multipolygon relations, roads, terrain and trees are not included, and tag-derived buildings are placeholders with their source recorded in `buildings.json`.

## Rejected during this work

Registering the outline against the height field in plan dragged the footprint 3.5 m toward a neighbouring mass and lowered mean IoU from 0.915 to 0.815. It was removed; registration stays on multi-view silhouettes.

## Commands

```powershell
# one building, parametric only
.venv/Scripts/python -m worldscale.cli massing --evidence inputs/evidence/<id> --run runs/<name>
# add one bounded vision call for detail parameters
.venv/Scripts/python -m worldscale.cli massing --evidence inputs/evidence/<id> --run runs/<name> --vision-details
# measured roof: start the reference viewer, sample once, then run massing again
..\workflow_research\.venv\Scripts\python -m building_workflow.urban.reference_server --port 8767 --longitude <lon> --latitude <lat>
.venv/Scripts/python -m worldscale.cli heights --evidence inputs/evidence/<id>
# whole snapshot
.venv/Scripts/python -m worldscale.cli district --osm <snapshot.osm> --run runs/<name> --fitted runs/<massing run> ...
```

`heights.json` sits beside `evidence.json`; when present, `massing` uses it automatically.

## Open work

1. Merge coplanar neighbours and trace plane boundaries as polygons instead of grid rectangles, to remove stepping and cut triangle count.
2. Classify each face above the eave as wall, roof or trim from the views.
3. Derive the wall outline from the height field where the OSM outline is too coarse, with a neighbour-safe mask.
4. Facade structure per edge from rectified view crops: storey lines, bay rhythm, entrances.
5. Run the same pipeline on several building types to calibrate thresholds and find failure cases. One building is not a benchmark.
6. Batch evidence capture for a district, so more than one building is fitted to imagery.
7. Decide how the native img2threejs passes use this output. The compiled massing could seed the native spec's macro level as locked components; that bridge is not built.
