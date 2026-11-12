# Scene-informed Tokyo block: implementation and research results

Date: 2026-11-12. Selected run: `tokyo-scene-v2`. This replaces `tokyo-multiview-v1` as the current implementation experiment. **Technical validity passes; factual and style acceptance remain false.**

## What is implemented

The workflow now supports hashed shared-scene manifests, a joint observation plan, individually cached code modules for every intersecting building, host-owned world anchors, explicit placement/material checks, style images supplied to generation and review, and bounded component repair. Newly captured views record camera position/orientation, view/projection matrices and viewport. A depth heuristic can retry a camera that is too close to an occluding surface; it is not a visual acceptance metric.

Optional `--reference-url` adds an evidence stage before generation: sparse Google roof/road height sampling and one common overhead observation of crossing extents and physical surface appearance. Ground observations project through the actual rendered mesh; paint polygons are clipped to canonical AOI road surfaces. Style can increase seeded canopy cluster detail without changing tree anchors. No fixed style palette is introduced.

Material binding is verified on meshes, not inferred from downloaded assets. Natural scan albedo is preserved with explicit tint handling; painted plaster retains intrinsic paint. Metric mapping is continuous in world coordinates and supports explicit material texture rotation. Automatic per-segment curved-road UV layout and location-specific texture baking are not implemented.

## Actual experiment

- Requested AOI: 120 m square, four cells, centered at 139.76310 / 35.67845. Five full OSM footprints intersect it and are retained intact, so building geometry extends outside the ground AOI. This is not an equal-extent quantitative comparison with the previous 220 m run.
- All five buildings have generated component modules; none is an empty context extrusion. Scene evidence is still partial for several objects. A generated component is not an accepted reconstruction.
- Thirty-six tree anchors remain from OSM and approximate overhead crown observations. The provider's geometry does not establish exact trunks or species.
- Sparse mesh samples place the museum roof about 19.34 m above the median sampled road surface, correcting the earlier inferred 10.8 m. A second inferred neighbor changes to about 18.89 m. The 170 m tagged tower agrees with a sampled maximum of about 169.88 m.
- One complex footprint has a 12 m OSM height tag while samples span roughly 9–35 m above the road. The tag is retained and the conflict is recorded. A multi-level building needs part-level interpretation; stretching its whole volume to the highest sample would be unjustified.
- Eight crossing candidates were detected in the larger overhead frame: two rejected by confidence/geometry checks, five outside the AOI road mask, and one retained as 21 stripe polygons. Crossing extent is observed approximately; stripe spacing is procedural, not measured. Lane arrows and a complete lane graph remain absent.
- Road/pavement scan multipliers are separately estimated from factual imagery, with uncertainty; they are not a style palette or calibrated reflectance.

## Verification and measured usage

- 49 tests pass, including complete scene IDs, image-content invalidation/path containment, placement drift detection, mesh-height origin/conflict handling, road-mask clipping, seeded fine canopy detail, and held-out routing.
- Actual native geometry, placement and declared material-binding checks pass. Real renderer audits confirm brick albedo/normal/roughness binding. The interactive browser audit is saved in `interactive-validation.json`.
- Final styled overview: 293 draw calls and 715,224 visible triangles, including trusted vegetation/environment. Generated building geometry is separately bounded. CPU submission median about 4.4 ms is not GPU time or a display-FPS guarantee.
- Main run: 13 metered model calls; shared ground observation: one additional call. Combined: **14 calls / 260,836 metered tokens**. Summed reported API wait durations: approximately 903 seconds; stages overlapped, so that is not total wall time. Gateway dollar cost is unreported. Cached style requests are reported separately, not counted as new billed inference.
- This was an assisted experiment. Technical model failures required retained source repairs for a scope error, concave extrusion handling, a nonconforming roof mesh and dome cap winding. No claim of unattended reliability or native img2threejs eight-pass completion is made.

## Research conclusions

| Question | Result |
|---|---|
| Can placement/material failures be caught deterministically? | Yes for the implemented bounds, identity and binding contracts. These do not prove detailed fidelity. |
| Can shared context generate all AOI building components? | Demonstrated for five intersecting footprints; some evidence remains ambiguous. |
| Does this prove reduced per-city cost? | No controlled same-extent cost comparison or scale trial was run. |
| Does multi-view code generation now match the source and style? | No. Massing/material coverage improved, but the actual visual reviews reject the result. |
| Can generic PBR maps reproduce local street appearance? | Only approximately; crossings help, but lane topology, paving boundaries and material calibration remain incomplete. |

Remaining major visual findings: the tower podium canopy is too planar; the historic neighbor's glazed dome/rounded projection is not sufficiently legible; museum bays/gables/openings are still repetitive; roads lack their full marking hierarchy; surface/planting treatment still falls short of the supplied style. These findings are retained in `scene-review-02.json`.

The older implementation exposed the designated held-out image during early reviews. Consequently this run is **not an independent held-out evaluation**. Routing is now corrected and tested so new runs reserve that image until final validation. Existing legacy source images also lack complete camera matrices; capturing matrices now does not retrospectively calibrate them.

## Next research gate

Do not increase area yet. Resolve multi-level height profiles and footprint-to-visible-part association; rebuild the curved canopy and dome using source-guided section measurements; derive a lane/surface graph from calibrated overhead evidence; then compare source-matched crops and the real style references at appropriate detail scale. Run the native img2threejs staged architectural compatibility experiment separately. Every proposed improvement requires new rendered evidence, not a checked implementation task alone.

## Inspect and reproduce

Serve `runs/urban` locally and open `/tokyo-scene-v2/index.html` or `/tokyo-scene-v2/viewer.html`. Select an object to isolate it; tree variation changes shape while preserving anchors. Saved `interactive-overview.png` and `interactive-museum.png` show the actual viewer.

For a new complete scene-mode run with the evidence service available:

```powershell
.venv/Scripts/python -m building_workflow.urban.reference_server --port 8767 --longitude 139.76310 --latitude 35.67845
```

In another terminal:

```powershell
.venv/Scripts/python -m building_workflow.cli urban --style-dir inputs/style-references/user-isometric --scene-refs inputs/scene-references/tokyo-block-shared/manifest.json --reference-url http://127.0.0.1:8767/ --run-id tokyo-scene-next --size 120 --longitude 139.76310 --latitude 35.67845 --grid 2 --osm-snapshot inputs/geography/tokyo-marunouchi/snapshot.osm --tree-observations inputs/object-references/tokyo-museum/tree-crown-candidates.json --max-calls 20 --max-tokens 350000 --max-seconds 2400 --max-visual-refinements 1
```

The selected experiment was built incrementally, with derived evidence added during diagnosis and a final re-render; the newly assembled automatic evidence stage has component/live-service verification, not a second fresh end-to-end run. Additional ground-observation calls have their own bounded usage file and are included in aggregate reporting. Use a new run ID when factual inputs or run configuration change.
