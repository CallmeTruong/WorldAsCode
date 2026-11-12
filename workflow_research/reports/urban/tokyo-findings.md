# Tokyo small-area experiment

Active AOI: Marunouchi / Mitsubishi Ichigokan / Brick Square, longitude 139.76310, latitude 35.67845, 220 ? 220 m, four 110 m cells. The user changed the test location from HCMC because detailed Google building meshes were unavailable in that probe.

## Verified inputs

- Existing Cesium ion token successfully streams Google Photorealistic 3D Tiles using official CesiumJS 1.147.0. No additional provider key was required for this test.
- Six real Google reference views: `runs/urban/tokyo-google-reference/`. Coverage records 3,452 cumulative tile load events, zero tile failures and zero render errors. These are events, not unique assets or billing units. Visual inspection confirms elevated buildings, roofs and facades in this AOI; it does not establish citywide coverage.
- Bounded OSM snapshot: `inputs/geography/tokyo-marunouchi/`; Tokyo coordinate normalization uses EPSG:32654. The normalized AOI contains 14 building objects and eight OSM tree nodes. Heights lacking tags remain explicitly inferred.
- Mitsubishi Ichigokan (`way/306116935/0`): four camera headings and one overhead frame, with separate unclipped and footprint-clipped captures. Clipping can leave neighbor fragments and cut surfaces; those are excluded as architectural evidence. Camera headings do not guarantee that every facade is visible.
- The overhead vision call produced 51 canopy candidates. Fifty survive AOI/building/proximity filtering, yielding 58 total anchors including OSM nodes. These are approximate canopy locations with 5 m uncertainty, not surveyed trunk positions. Detection recall/precision has not been measured.
- Original user style image remains in `inputs/style-references/user-isometric/`. The workflow extracts descriptive style from arbitrary folder contents, independently of factual imagery. It imposes no global palette.

## Pipeline and evidence boundaries

AOI + OSM ? provider coverage check ? overview/overhead ? per-object camera capture ? multi-view LLM part analysis ? procedural TypeScript ? isolated execution and geometry checks ? trusted PBR renderer ? per-object visual review/refinement. Overhead canopy candidates enter a separate anchor manifest; seeded shape generation only varies geometry around each fixed anchor.

The current reconstruction test intentionally observes one museum individually. Thirteen other buildings are context proxies with OSM footprints and available heights. Google reference imagery and the procedural reconstruction are distinct outputs. Generic PBR brick/roof maps are surface assets, not photographed facade texture baking. Passing geometry tests cannot establish facade accuracy.

A technical defect in generic concave context extrusions triggered the native geometry gate. Model repair attempted footprint simplification; this was rejected. The local correction decomposes original polygons (including holes) into closed triangular prisms, preserving their footprint and height. Failed attempts and source history remain retained. This is an assisted research run, not evidence of unattended city-scale reliability.

## Provider strategy for scale

Use the working Google/Cesium provider as the initial visual source, with a visibility and mesh-height gate for each AOI. Schedule object-level jobs by stable identity; reuse source and observations across cells, and canonical roads across tile boundaries. Request supplemental street imagery only when occlusion or source resolution prevents the target fidelity. Mapillary/Planet catalog adapters exist but their credentials and Tokyo coverage are not validated; they are optional, not a prerequisite now. No Planet orders were placed.

Official implementation references: [CesiumJS Google tiles integration](https://cesium.com/learn/cesiumjs-learn/cesiumjs-photorealistic-3d-tiles), [Google Map Tiles API](https://developers.google.com/maps/documentation/tile). Exact AOI observations above come from local captures rather than provider marketing coverage claims.


## Completed procedural test

Run: `tokyo-multiview-v1`. Native geometry gate passes; runtime valid; style switches preserve geometry and material identity. Visual acceptance remains **false** after one bounded visual refinement. Direct inspection and the image reviewer identify insufficient roof/gable fidelity and smooth brick surfaces. The model failed to attach the supplied brick texture role to its materials, so availability of a PBR asset did not guarantee its use. Several context towers also occlude the default close view; use the object selector to isolate the museum. Anchor/plan alignment remains approximate.

The run used eight metered model calls, 84,568 input + 17,907 output tokens, with about 361 seconds of API waiting, excluding capture/preparation and local rendering/repairs. Gateway cost is unreported (`cost_usd: null`); no dollar estimate is asserted. This one-object result cannot support a city-scale time/cost extrapolation. Overhead canopy detection is a separate metered call in its capture folder.

Regression validation: **40 tests pass**. Styled overview measured 258 draw calls and 289,351 visible triangles; recorded render timings are CPU submission only, not FPS. There are zero lamp objects in this AOI manifest, so lamps are not claimed as reconstructed.

Local views: [Google reference](http://127.0.0.1:8767/), [procedural viewer](http://127.0.0.1:8765/tokyo-multiview-v1/viewer.html), [evidence report](http://127.0.0.1:8765/tokyo-multiview-v1/index.html).

Next fidelity work should enforce explicit material bindings, check generated object bounds/anchor against the source footprint, and compare every side using calibrated or matched cameras. Do not spend a whole-city generation budget until this one-object gate passes. Provider integration is working; object reconstruction quality is the remaining bottleneck.

Interactive browser validation passes: seed 0 to 42 changes geometry, retains all 58 IDs/anchor coordinates, and produces zero page errors. Object inspection camera now frames the emitted geometry bounds; updated captures are `interactive-object.png` and `interactive-overview.png`. This camera correction changes framing only, not reconstruction accuracy.
