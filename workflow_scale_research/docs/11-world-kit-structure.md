# World kit: reusable tools, designs and scenes

## Meaning and current scope

`world-kit` names the intended Three.js authoring SDK. It is a library of parameterized construction operations, not a catalog of fixed buildings or a preset scene. An agent writes code using these operations, measured site facts and a separately extracted style sheet. Special features can use custom geometry; repeated useful constructions should become versioned reusable operations.

Today `runtime/kit.mjs` implements the building subset. It contains no Tokyo coordinates or museum ID. Its vocabulary and roof generator are strongest for low-rise pitched-roof architecture. Default dimensions are overridable fallback values; a model-generated script that assumes exactly three floors is a bespoke design, not proven family code. Building-kit improvements alone do not establish city-scale readiness.

## Target layout (not all implemented)

```text
runtime/world-kit/
  core/                    # metric frames, curves, extrude/loft, seeds, ownership
  materials/               # seeded surface recipes, texture/UV and state bindings
  buildings/               # wall, facade, roof, opening and roof-feature tools
  infrastructure/          # road cross sections, intersections, bridges, railways
  vegetation/              # trees, shrubs and growth variants
  streetscape/             # lights, signs and street furniture
  terrain/                 # terrain, water and ground cover
  mobility/                # vehicle, person and animal assets/runtime adapters
  state/                   # day/night, wetness, wind and environment controls

designs/
  families/                # recipes parameterized by site facts and variant/seed
  landmarks/               # distinctive architecture needing a bespoke recipe
styles/                    # transferable visual treatment, not object placement
scenes/                    # instance placement, road graph, grids and ownership
```

Use filenames such as `walls.mjs`, `roofs.mjs`, `trees.mjs` and `roads.mjs`. Do not create domain libraries named after a city or style reference. A style generally changes recipe parameters/material treatment rather than duplicating the SDK. Version the kit API and family recipes independently. Keep the current `kit.mjs` as an import facade if the implementation is later split, so persisted design scripts remain readable.

## Responsibility boundaries

- Kit: how geometry/materials are built; valid units, joints, UVs, semantics and seeds.
- Family design: how tools are composed for an architectural or object family. Must accept footprint changes, storey count, selected measured features and style parameters. Promotion to family code requires more than one site.
- Landmark design: exact arrangement of distinctive components for one site, with identity/provenance and explicit fallback assumptions.
- Scene/network: where instances belong and how paths/connectors continue across grids. Cells reference a global road/rail graph; they must not generate separate incompatible road splines.
- Runtime state: lights/emission, wetness, wind and motion. They should not rebuild fixed building footprints or road topology. Geometry seeds are stored on instances; environment state is separate.

## Example contracts

Existing building calls include `b.walls({material})` (measured footprint), `b.window(frame, options)` and `b.gable(frame, options)`. A future road contract could take `{path, crossSection, junctions, surface, seed}`; a future tree contract could take `{species, height, crown, seed}`. Road/tree examples are proposed contracts, not currently available methods in `kit.mjs`.

Network edges need stable IDs, world-distance stationing, shared junction geometry and deterministic ownership. Reusing the same asphalt recipe is insufficient for cross-cell continuity. Tree/vehicle populations need instance/LOD budgets in addition to procedural geometry. Novel object families require new capabilities; the agent should not approximate every unseen object by the nearest available prefab.

## Next proof points

First improve the real building pilot and inspect multiple views. Then run a parameterized family recipe on a second site and several synthetic footprints/storey counts; distinguish synthetic capability tests from factual fidelity tests. Only then compose neighbouring cells and measure seams, draw calls, memory, streaming and incremental updates. Current work is not yet proof of these scale properties.

## Authoring permission and kit evolution

Shared release lifecycle is now implemented for the building package: host-held scoped grants, fresh validation, incubating/stable gates, pinned snapshots, rollback and bounded API/runtime selection. See [docs/14](14-shared-kit-library.md). The directory/domain layout above remains a target; road/tree/rail packages are not implemented by this release mechanism alone.

The workflow now includes gap-triage and kit-developer nodes. They can propose changes to granted methods and add bounded new operations in an isolated run-local copy. They cannot write the shared kit, change measured walls or modify acceptance gates. Regression tests exercise both the old API and the new capability; a real-site render and critic must show balanced improvement before local activation. See [12-adaptive-agent-kit-evolution.md](12-adaptive-agent-kit-evolution.md) for actual permissions, commands and experiment results.

The extension route distinguishes bad usage, missing evidence and a missing library capability. Existing assets pin the former version and are not silently migrated. Novel architecture can stay bespoke; only proven repeated patterns should become family code or core library operations. Ambiguous evidence must remain explicit rather than being disguised by a new primitive. Global release, broad held-out benchmarking and automatic migration remain future work; local activation does not establish those properties.

Every author call includes the compact `kit-api.md`, site/style and images; full library source is not injected. The implemented capability registry supplies a small index to triage; the developer receives only granted methods. Dynamic retrieval across future road/tree domains remains to be implemented. Facts/style/compiled modules use explicit content/version caches; repeated prompt text does not guarantee a provider cache discount.
