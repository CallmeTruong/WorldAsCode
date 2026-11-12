# Quality improvements for the measured-site design route

The current `design` route remains the main workflow. These changes target the museum pilot's observed weak gables, generic facade and flat materials; they are reusable kit capabilities, not a separate hardcoded museum generator.

## Geometry and materials

- Material channels: seeded synthetic albedo, roughness and height/bump maps for brick, slate and panels. Course/unit dimensions are measured in metres; tile size no longer implies the size of one brick. Box and sloped roof UVs account for physical dimensions. Maps do not claim source PBR recovery.
- Dormer cheeks sample the host roof at front/back; a frame-aligned opening is subtracted from the underlying triangulated roof shell. Cut-edge UVs are interpolated from the host. This is a local shell opening, not a full solid boolean union or complete roof graph.
- Gables support sloped trim/cornices, a locally cut host opening and a roof tail blended down to sampled host height. The author is explicitly told to distinguish tall wall gables from dormers/turrets using images, because height-field blob labels are uncertain.
- `b.window` supplies modeled jambs, lintel, sill, mullions, pediment and keystone. Glass is a separate surface above the wall; actual wall recesses are not claimed.
- Chimney shafts/caps contain extruded holes and pots are open cylinders with annular rims. This replaces the prior solid-cylinder shortcut.
- Site/style are deeply frozen copies, builder internals are not exposed through the authoring API, exactly one wall assembly is required, and the wall mesh's transform/vertices are checked after script execution. The height tolerance is enforced at wall construction. Arbitrary added decoration remains possible and needs render/semantic checks.

## Feedback and evaluation

The author/critic receive matching detail sheets cropped from source-derived camera rectangles, alongside full multi-view sheets. Upper/lower crops are image regions, not asserted semantic segmentations. They reveal roof joins, gable proportions and facade relief that full-scene thumbnails conceal.

Style extraction describes transferable treatment of colour/value/materials and shadow rather than named object colours or a hex palette. Scene ground is selected by the design; the style schema no longer requires a green or other specific ground copied from the reference.

Ranking prioritizes accepted status and metric correctness, then the weakest normalized visual score before likeness and total score. Invalid/non-finite critic scores are rejected. Large likeness regressions cause the next revision to start from a retained best script. This uses noisy model estimates; it does not establish human-level quality acceptance. Each script's reuse on a second building remains unverified.

Site confidence records identify registered OSM, inferred or sampled heights, uncertain feature identity and material colour cues. Input manifests record evidence, optional height field, style, kit and surface versions.

## Validation and pilot

Browser tests exercise independent channels, repeatable material seeds, real holes in the chimney shaft/cap, and rejection of site/wall mutations and duplicate walls. Candidate ranking and score validation have regression tests. The real museum run is `runs/design-ichigokan-v2-quality` with a bounded three-revision allowance; its result and directly inspected images determine visual status, not the software test count.

Still needed: continuous ridge/valley topology for complex roofs, proper facade openings, stronger semantic collision/attachment checks, held-out building types, family-script reuse and district composition.

## Observed pilot results

`runs/design-ichigokan-v2-quality` completed four attempts (initial + three revisions), using 9 model calls, 113,371 input tokens and 14,712 output tokens in 1,111 seconds. All four passed the current tolerant metric gates; none met visual acceptance. The retained attempt was 2: mean oblique IoU 0.8873, plan IoU 0.9129, 24,480 triangles; critic likeness/style/detail 0.58/0.49/0.42. Attempt 3 scored 0.53/0.67/0.36: increasing style while losing likeness/detail did not make it the best.

The old v1 image was re-reviewed with the same detail-aware critic: 0.46/0.55/0.38 (`baseline-review/review.json`, one additional call, 12,565 input + 688 output tokens). This common reviewer is more useful than comparing to older critic scores, but remains noisy. Runtime changed during the supervised experiment; per-attempt `runtime-versions.json` records actual bundled module hashes. This is iterative engineering evidence, not a controlled one-variable A/B test.

Direct inspection of full and detail sheets still shows generic facade composition, thin fin-like roof ends, weak ridge/valley junctions and broad simplified roof planes. Surface maps and hollow chimneys improved implementation correctness; they did not solve architectural fidelity. Do not label this pilot accepted or ready for city-scale replication.

The next implemented branch lets workflow nodes develop isolated kit candidates and reject regressions themselves. See [12-adaptive-agent-kit-evolution.md](12-adaptive-agent-kit-evolution.md).
