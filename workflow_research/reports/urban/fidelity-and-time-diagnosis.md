# Fidelity and latency diagnosis — 2026-11-12

## Conclusion

The dominant failure is the allocation of work: a language model is asked to infer spatial measurements, select a narrow preset material set, implement geometry from scratch, and satisfy topology constraints in one response. More forceful prompts alone will not supply missing geometric correspondences or surface evidence. Data/tool integration and the representation/acceptance contracts must change together. A stronger model may help, but model capacity has not been isolated experimentally.

## Code-supported causes

1. **Images are available but not sufficiently actionable.** Legacy common views are not calibrated to the emitted meshes. Footprint IDs are supplied as a diagram and prose, not projected masks identifying the exact visible roof/facade. A few roof-height samples provide an envelope, not roof planes, ridge locations, curves or BuildingPart assignments. Full intersecting footprints extend beyond the requested AOI while ground is clipped to it.
2. **Materials are too restricted and insufficiently calibrated.** The resolver always offers the same asphalt/pavers/plaster/clay roof/granite/red-brick scans. There is no appropriate slate/metal roofing map, and the model therefore uses a plain roof material. A bound brick map can still be the wrong brick, scale or hue. The prompt's blanket WHITE multiplier rule fixed double tinting but also suppresses justified object-specific albedo adjustment. Road classification alone cannot describe lanes, curbs, repairs, paving boundaries or intersection topology.
3. **Macro/meso geometry remains wrong.** Roof gables, canopy curvature, dome proportions, reveal depths and facade bay hierarchy dominate identity. Repeated windows on a solid extrusion are not equivalent to the observed facade. Higher-resolution maps cannot repair these defects.
4. **Rendering flattens surfaces.** A strong hemisphere light plus an indoor RoomEnvironment is not a calibrated outdoor illumination model. Current shadow coverage is 800 m over 2048 texels (~39 cm/texel), with 12 cm normal bias: small architectural contact shadows cannot be resolved reliably. No AO/contact-shadow pass is present. Texture/output color-space declarations appear internally appropriate; there is no evidence yet that a global gamma bug is the main cause.
5. **Some constraints target the wrong representation.** Requiring every detail mesh to be a closed solid, restricting externally derived/generated textures, fixing a small material-role menu, enforcing one broad extrusion/height envelope and allowing only a small number of whole-source repairs favor cheap primitives. Keep sandboxing, identity, coordinate and resource checks. Use representation-specific checks for structural volumes, thin cladding, glazing, decals and vegetation. Do not simply disable all geometry checks.
The shared scene observation prompt also contained an inappropriate city-specific sentence prescribing a red museum and pointed gables. That sentence has now been removed from the generic workflow and replaced with evidence-specific identity guidance. This fixes a prompt bias for future areas; it does not retroactively repair the current geometry. Vegetation similarly preserves approximate XY but uses seeded default dimensions/green material rather than measured canopy size and observed seasonal appearance; adding more lobes alone is not a realism solution.

6. **Workflow acceptance is not strong enough.** Comments naming stages do not enforce staged review. Most measurements certify that code runs and assets are bound, not that the measured shape/material is correct. Critical visual rejection must trigger a targeted measurement, spec repair, geometry fit or a declared evidence gap; another broad prompt is not always the right action.

Orthographic/oblique composition is not inherently a defect: the user's reference also uses an elevated architectural view. Making everything darker, adding AO everywhere, or changing perspective is not proof of realism.

## Controlled rendering experiment

Artifacts: `runs/urban/tokyo-render-ablation/`; interactive comparison: `/tokyo-render-ablation/index.html`.

Three variants keep the same geometry, native material parameters, maps and camera. Browser audit reports zero errors and identical geometry/material fingerprints in every variant.

| Setting | Baseline | Lower fill + fitted shadow |
|---|---:|---:|
| Hemisphere intensity | 1.3 | 0.35 |
| Environment intensity | 1 | 0.35 |
| Sun / exposure | 2.5 / 1 | 2.5 / 1 |
| Shadow resolution | 2048 | 4096 |
| Shadow width | 800 m | ~344.5 m |
| Shadow texel | 0.391 m | 0.084 m |
| Normal bias | 0.12 m | 0.015 m |

Direct image inspection shows stronger material contrast and visible shadows without recoloring the objects. Roofs and openings remain incorrect. The experiment isolates a rendering contribution but does not calibrate true albedo, validate style correspondence, establish the optimum lighting settings, or prove all shadow defects are fixed. The 4.64× improvement is spatial shadow texel resolution, not total visual-quality improvement. Capture durations include cold/warm shader effects and must not be compared as FPS.

## Where time goes

Selected run main API waiting time: ~855.9 seconds; separate ground observation: ~46.8 seconds. Five sequential component code generations account for ~507.1 seconds; two visual refinements ~142.3 seconds; three whole-scene reviews ~121.4 seconds. This is summed API waiting, not overall wall time, and excludes rendering. The prior total remains 14 metered calls / 260,836 tokens.

Highest-value optimizations:

- Observe the common scene once, then send only ID-associated visible crops, geometric evidence and relevant material examples to a component job. Repeated full-area views are expensive and distract from the selected object. Cropping cannot recover source resolution; move a camera closer when necessary.
- Compile measured roof/facade parameters through tested geometry operators. Ask the model for custom code only for genuinely novel forms; avoid paying it to repeatedly implement capping, normals, placement and window loops.
- Fit parameter values against depth/silhouette/edge observations; retain human/vision review for identity and style. Do not force the language model to be the numerical optimizer.
- Reuse the exact component, source evidence and material cache across runs/cells. Resolve/load only selected assets, rather than loading every texture class before observing the scene.
- Batch/parallelize independent component jobs under explicit request/token budgets, with separate usage writers and deterministic merge. Two-worker execution is a hypothesis to benchmark, not a promised speedup; current timings are serial.
- Review changed objects and affected regions first. Perform a complete scene/held-out review at finalization. Re-render only required views; preserve warm shader/texture caches when safe.

## Additional source research: PLATEAU

The current official PLATEAU catalog returns Chiyoda 2025 textured building LOD2 and road LOD3 datasets. Both tileset endpoints returned HTTP 200, and their root bounds include the test center. A bounded Cesium render of the actual AOI loaded overview and overhead views with zero tile failures; the close museum view did not fully settle within its bounded wait.

Artifacts: `reports/urban/provider-research/plateau-chiyoda-current-catalog.json`, `plateau-service-checks.json` and `runs/urban/tokyo-plateau-reference/coverage.json`.

Direct inspection shows useful cleaner building volumes, roof forms and rooftop imagery. The displayed road layer is largely white, and fine facade/canopy/dome detail is not automatically established. These are uncalibrated reference renders, not quality scores. A catalog `texture=true` must not be interpreted as complete target-object texture coverage. Validate semantic IDs, BuildingParts, capture epoch and vertical datum before combining with Google imagery. PLATEAU is an optional Japan capability, not the global provider replacement; Google/OSM remains the general fallback.

## Recommended reconstruction architecture

1. Resolve the best available semantic geometry, photogrammetric geometry and imagery separately per AOI. Validate coverage, detail and coordinate systems.
2. Construct a shared measured scene: stable IDs, camera poses, visible-face masks, roof/ground depth, part-height profiles, road/paving regions and confidence. Keep unknowns explicit.
3. Recover macro forms using source geometry and constrained roof-plane/curve fitting. Recover meso forms using facade bay measurements, window/recess masks and part-specific operators. Use custom procedural code where needed.
4. Build a material specification per actual surface: material family, suitable candidate assets, metric UVs, intrinsic tint, roughness/normal layers and evidence. Roof sheets, seams, flashing and rooftop units are not represented by a single gray color. Street shape/markings are separate from asphalt microtexture.
5. Keep a factual reconstruction branch authoritative. Apply descriptive style to detail hierarchy, surface-frequency treatment, vegetation and lighting without turning unmeasured simplification into factual geometry. Do not impose a shared palette.
6. Calibrate an outdoor lighting/reflection setup and contact shading. Compare source-matched views at useful crop resolution. Optimize geometry, material and lighting in separate passes to avoid compensating for one error with another.
7. Use object/part-level repairs, validate withheld views only at the end, and scale area only after the block passes factual and style acceptance independently.

## Options and boundaries

For editable procedural output, source-guided parametric geometry plus evidence-derived texture/material work is the primary candidate. A hybrid viewer that streams source tiles outside reconstructed hero regions can improve visual coverage quickly, but is a different output contract from generating the whole city by code. Gaussian splatting is worth considering for captured appearance, but does not directly supply the requested editable semantic architecture. Inverse-rendering methods show how geometry, materials and illumination can be fitted jointly; they require an additional calibrated-data/compute experiment and should not be installed or claimed effective here without testing.

## Primary sources

- [Three.js color management](https://threejs.org/manual/pages/color-management.html)
- [Three.js Scene environment intensity](https://threejs.org/docs/pages/Scene.html)
- [Three.js GTAO](https://threejs.org/docs/pages/GTAOPass.html): an available contact-shading candidate, with quality/performance tradeoffs; not implemented in this experiment.
- [PLATEAU official catalog API](https://docs.plateauview.mlit.go.jp/api/rest/operations/datacatalogplateau-datasets/) and [dataset conversion/LOD specification](https://docs.plateauview.mlit.go.jp/spec/visualization/)
- [NVIDIA nvdiffrec](https://nvlabs.github.io/nvdiffrec/): research precedent for fitting mesh/material/lighting from multi-view images, not proof that it solves this AOI.
- [gsplat](https://github.com/nerfstudio-project/gsplat): alternative appearance representation, not a substitute for semantic editable geometry.
