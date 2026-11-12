# Tokyo pipeline audit and proposed redesign

Status: diagnosis and proposed architecture, not an implemented replacement. The current run remains visually rejected.

## Confirmed implementation defects

- `urban/style.py:presentation_settings` translates style into lighting only; `urban-viewer.mjs:setCityStyle` changes lights/exposure and leaves materials untouched. Free-form style is passed to object code generation, but there is no corresponding visual style acceptance contract. Removing palette restrictions was incorrectly reduced to almost disabling surface/art-direction treatment.
- The selected generated museum source contains zero `textureRole` assignments. The renderer only binds native material maps through that field. A downloaded brick texture is therefore not evidence of visible brick texture.
- `object-observations.json` reports one observed object out of 14. The other 13 use explicit gray context extrusions. Their washed-out appearance is an intentional incomplete branch, not Google's missing building textures.
- The generated museum function uses local footprint coordinates but never translates its group to `b.center`. It also addresses particular ring vertices (`p[0]` through `p[5]`) as if their ordering encodes architectural parts. This is fragile and can distort placement/plan interpretation. The height/topology gate does not establish footprint alignment.
- Roads use OSM centerline buffers with fallback widths and assumed sidewalk offsets. Material assets are fixed asphalt/paving scans with assumed physical repeats. This does not reconstruct observed curb layout, surface changes, crossings or markings. Zero lamp objects were recorded; there is no evidence of complete street-furniture reconstruction.
- Fixed-direction, footprint-clipped Google views contain cut surfaces, blur and occlusion. Capture metadata records orbit parameters and position, but the object reconstruction/review does not use an exact shared projection/view transform. Generated inspection views are approximate; texture and facade comparisons are consequently ambiguous.
- Urban generation uses a bespoke part-plan/code/review branch, with one bounded visual refinement. It does not run the upstream img2threejs complete staged specification/build/review process. Reusing the geometry gate is not full upstream integration.

## Provider assessment

Google Photorealistic 3D Tiles supplies textured geospatial meshes, not a clean per-building semantic/PBR/BIM asset library. The Tokyo captures establish useful visible roofs/facades and context. They also show that close facade detail can be blurred or fused. Rendering these views is appropriate; discarding their spatial relationships and relying on loosely constrained text-to-code generation wastes much of their value.

Do not infer exact material albedo from imagery with baked shadows/reflections. Exact hidden geometry remains unknown; changing the camera cannot recover information absent from the source mesh/texture. Use supplemental street imagery selectively when source resolution/visibility fails the fidelity target.

## Recommended architecture: scene-level reasoning, component-level construction

1. Create an AOI evidence package: unclipped overview/overhead/oblique views, exact camera view/projection matrices, viewport, coordinate origin/axes, available picked depths/height samples, OSM footprints/roads and their uncertainty. Depth is geometric evidence, not semantic segmentation. Any depth/normal export beyond current point sampling requires implementation and validation.
2. Analyze the entire scene jointly. Produce a persistent scene graph with stable IDs, footprint/height/roof hypotheses, visible facades, road topology, surface regions, vegetation anchors, occlusion and source confidence. Bind observations to IDs rather than keeping only narrative summaries.
3. Plan cameras by coverage: reuse the same scene image for all visible objects; crop source images for adequate resolution. Add close views only for occluded/ambiguous roofs/facades. Four new images per building are not mandatory. A crop does not create missing pixels.
4. Build shared ground/roads/curbs/planting first in a canonical coordinate system. Derive repeated facade assemblies from evidence-based parameters. Generate custom object/part code only where a library cannot represent the observed identity. All buildings in the selected acceptance area must receive an explicit reconstruction status; proxies cannot count as finished coverage.
5. Adapt img2threejs's staged observation, specification, construction and visual review to architecture. Review massing/placement, roof, openings, surfaces, small details and composition before advancing. Native eight-pass compatibility must be demonstrated separately rather than asserted from an analogous urban sequence.
6. Use explicit material manifests: surface identity, evidence, intrinsic tint, texture role/asset, metric mapping, roughness and binding result. Fail material coverage checks when required maps are absent. Use directional UVs for roads and facade-local UVs for masonry; share continuous coordinates across cells. Generic PBR scans are a fallback, not location-specific texture reconstruction. Photo projection/baking is an optional separate research branch requiring visibility, shadow handling and seam checks.
7. Apply style as descriptive art direction: geometric detail hierarchy, edge treatment, surface-frequency control, vegetation structure, lighting/contrast and composition. Preserve semantic material/color identity without forcing a universal palette. Feed the actual style images into visual review, not just the extracted prose. Retain factual and styled renders independently.
8. Render source-matched cameras for geometric comparison, plus held-out views not used for reconstruction. Check footprint/height/anchor alignment, semantic part identity, visible texture coverage, complete-area coverage and style correspondence separately. Geometry tests alone cannot accept the result. Record unobservable facades explicitly; unsupported views cannot be scored as factual matches.
9. Cache source captures, scene observations, object modules and shared assets independently. Schedule repairs by failing object/part and source hash. Keep canonical roads and stable seeds across tile boundaries; introduce LOD/streaming only after small-AOI fidelity passes.

## Bounded next experiment

Use the existing Tokyo inputs to compare the current object-only baseline against scene-level observation with component modules, using the same AOI and source views. First fix coordinate/material contract failures. Then reconstruct a contiguous block with all its buildings and shared street surfaces; do not scale area while this block remains visually rejected. Record time, tokens, repair count, observed coverage and separate factual/style visual judgments. Add provider imagery only for specific unresolved visibility gaps.

## Primary references

- [Google Photorealistic 3D Tiles](https://developers.google.com/maps/documentation/tile/3d-tiles)
- [Cesium Scene picking and height APIs](https://cesium.com/learn/cesiumjs/ref-doc/Scene.html)
- [img2threejs upstream](https://github.com/img2threejs/img2threejs); local pinned source: `vendor/img2threejs/`, especially `SKILL.md` and `grimoire/review/self_correction.md`.
- [Tropical island showcase source](https://raw.githubusercontent.com/img2threejs/img2threejs-showcase/main/src/demos/tropical-island/createTropicalIslandModel.ts): this example explicitly documents offline measured prop surfaces and separate environment/shader modules. It does not demonstrate that our one-shot urban branch should achieve identical fidelity.
