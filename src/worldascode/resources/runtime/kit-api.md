# Building kit API

Write one ES module: `export function design(site, b, style) { ... }`. No imports. Units are metres. Y is up.

## What you receive

`site` (measured, read-only):
- `eave_m` wall-top height, `ridge_m` main roof top, `top_m` highest feature, `storeys`
- `roof`: `{form, pitch_deg}` as measured (a hint; you choose the form). When a height field exists it also has:
  - `sections`: one per wing, `{id, centre_xz, rotation_y_rad, length_m, width_m, profile: [[offset across the wing, height]], ridge_m, hip_start_m, hip_end_m, form}` — the measured cross-section swept along the wing; a hip value of 0 means a vertical gable end.
  - `volumes`: masses standing above those sections, `{id, kind: 'pavilion' | 'roof_volume', x, z, rotation_y_rad, width_m, depth_m, base_m, shoulder_m, top_m, cap: 'flat' | 'pyramid' | 'gable'}` — position and heights are measured; what to call it (tower, cross gable, penthouse, plant room) is your reading of the views.
- `edges`: `[{id, length_m, facing, end}]` — `facing` is the compass side the wall looks at; `end: true` marks the short end of a wing
- `wings`: `[{length_m, width_m, centre_xz, rotation_y_rad, corners, confidence}]`; optional rectangular layout priors in the same registered frame. Corners retain precision; the protected footprint remains authoritative.
- `observations`: evidence-led roof hierarchy, facade rhythm, material identity and uncertain features from the observer node; these are visual interpretations, not surveyed facts.
- `features` (measured positions, may be missing): `dormers: [{edge, t, width_m, height_m}]`, `chimneys: [{x, z, height_m}]`. `t` is the 0..1 position along that edge. `towers` appears only when no `roof.volumes` could be measured.
- `colours`: `{wall, roof, trim}` sampled or estimated material colours
- `tags`: map tags such as architecture style

`style`: transferable treatment of materials, proportions, detail and lighting; never a fixed palette.

## Rules

- Call `b.walls(...)` exactly once, before the roof. The wall outline is the measured footprint and cannot be changed.
- Declare every material with `b.material(name, spec)` before using its name.
- Place parts with frames. A frame from an edge has local +X along the wall and local +Z pointing out of the building. Never compute world coordinates of walls yourself.
- Keep measured heights within about 15%. Exaggerate detail, colour and proportion of ornaments as the style asks, not the building's size.
- Use compact loops driven by measured dimensions/storeys. Include enough code for observed architectural differences; do not simplify distinctive forms just to meet a line-count target.

## Frames

- `b.edge(id).at(t, inset = 0)` → frame at fraction `t` along the edge, `inset` metres inside the wall line (negative = outside).
- `b.along(which, {count | spacing, margin = 1.5, inset = 0})` → array of frames. `which` is an edge id, an array of ids, `'all'`, `'long'` (non-end edges) or `'ends'`.
- `b.at(x, z, yaw = 0)` → free frame (use for `site.features` given as x/z).
- `b.roofY(x, z)` → roof surface height there (after `b.roof`).

## Materials

`b.material(name, {color, roughness = 0.8, metalness = 0, surface, glow})`
- `surface`: `{type: 'plain' | 'brick' | 'slate' | 'stripes' | 'panels', scale: metres per TILE (typically 2.4), course_m, unit_width_m, relief_m, color2}`. Brick defaults: 0.075 m courses and 0.23 m units. Slate: 0.24 m courses / 0.32 m units. Seeded synthetic color/bump/roughness channels, not source PBR. `seed` on material selects a reproducible variant.
- `glow`: emissive colour switched on at night.

## Main masses

- `b.walls({material, height = site.eave_m, storeys = site.storeys, bay = 3.2, window: {w, h, sill, arch, mullions: [cols, rows], frame, glass, glow}, course, windows = true})` — `bay` is window spacing in metres; `w`/`h`/`sill` are fractions of a bay/storey; `window.frame`, `window.glass`, and `course` accept CSS colours or declared b.material IDs for the facade texture. Other geometric APIs require declared material IDs.
- `b.band({y, height = 0.4, out = 0.25, material})` — horizontal band around the whole outline (cornice, plinth, string course).
- `b.roof({form: 'hip' | 'gable' | 'mansard' | 'flat', rise, overhang = 0.3, material, lowerFraction, lowerRun, parapet})` → `{ridgeY, eaveY}`. `rise` defaults to the measured ridge.
- `b.ground({material, margin = 3})` — pavement slab around the building.

## Measured roofs and roof-level masses

- `b.roofSections({material, endMaterial, overhang = 0.3, riseScale = 1, lift = 0})` → `{ridgeY, eaveY}` — builds every `site.roof.sections` wing roof from its measured cross-section, with gable-end walls (`endMaterial`) or hips as measured. Prefer this over `b.roof` whenever sections exist; `riseScale` 0.7–1.4 exaggerates or flattens the pitch.
- `b.volume(frame, {width, depth, y, shoulder, top, cap: 'flat' | 'pyramid' | 'hip' | 'gable' | 'cone' | 'dome', material, roofMaterial, glass, parapet, finial, overhang})` — a mass on or through the roof: walls from `y` to `shoulder`, cap from `shoulder` to `top`. For a measured volume `v`: `b.volume(b.at(v.x, v.z, v.rotation_y_rad), {width: v.width_m, depth: v.depth_m, y: v.base_m - 1, shoulder: v.shoulder_m, top: v.top_m, cap: v.cap, ...})`.
- `b.tier({inset, y, height, storeys, bay, material, window, windows})` → `{topY}` — upper storeys stepped back from the outline (tower on a podium, attic storey, crown). Call after `b.walls`; later tiers stack with a larger `inset`.
- `b.parapet({height = 0.9, thickness = 0.3, inset = 0, y, material})` — upstand around a flat roof or tier.
- `b.cornice({steps = 3, height = 0.9, out = 0.5, y, material})` — moulded cornice of stacked bands stepping outward.

## Facade systems (first argument selects edges: an id, an array, `'all'`, `'long'` or `'ends'`)

- `b.curtainWall(which, {glass, frame, spandrel, module = 1.5, floor, y = 0, top, mullionDepth, spandrelHeight})` — glazed wall with a mullion grid and optional opaque spandrel per floor. Use with `b.walls({windows: false})`.
- `b.ribbonWindows(which, {glass, frame, storeys, sill = 0.95, height = 1.7, module = 1.8, fromStorey, toStorey})` — continuous horizontal window bands.
- `b.fins(which, {material, spacing = 1.2, depth = 0.45, thickness, y, top, horizontal})` — vertical fins, or `horizontal: true` for louvres and sunshades.
- `b.frameGrid(which, {material, bay = 6, storeys, columnWidth, beamHeight, out})` — expressed columns and floor beams.
- `b.balconies(which, {material, railMaterial, rail: 'bars' | 'solid' | 'glass', depth = 1.2, spacing, width, fromStorey = 1, toStorey})` — one continuous balcony per storey, or separate ones every `spacing` metres.

## Street level and entrances

- `b.arcade(which, {material, roofMaterial, height = 4.5, depth = 2.4, spacing = 4, bays, pier, arch = true})` — arcade or colonnade in front of the facade.
- `b.storefront(which, {glass, frame, fasciaMaterial, height = 3.6, bay = 3, base, fascia})` — glazed shopfront with stall riser and fascia.
- `b.columns(which, {material, count | spacing, radius, height, out = 1.2})` — free-standing columns.
- `b.canopy(frame, {width, depth, y = 3.2, thickness, material, posts})`, `b.awning(frame, {width, depth, y, drop, material})` — entrance cover.
- `b.stairs(frame, {width, steps, rise, tread, material})`, `b.sign(frame, {width, height, y, material})`.

## Rooftop (frames from `b.at(x, z)`; height defaults to the roof at that point)

- `b.mechanical(frame, {width, depth, height, material, louvers})` — plant unit. `material` and optional `louvers` are declared string material IDs; `louvers: 'frame'` adds louvers using that material, omit/false disables them. Never pass `louvers: true`. `b.tank(frame, {radius, height, legs, material})`. `b.antenna(frame, {height, material})`.
- `b.skylight(frame, {width, depth, rise, glass, frame})`, `b.dome(frame, {radius, rise, drum, material, drumMaterial})`, `b.spire(frame, {radius, height, sides, material})`.
- `b.railing(which, {material, glass, height = 1.05, inset, y, spacing})` — guard rail along edges at roof or terrace level.

## Architectural parts (first argument is a frame)

- `b.dormer(frame, {width, height, depth, roof: 'gable' | 'shed' | 'flat', material, roofMaterial, trimMaterial, glass, setback = 0.6})` — side cheeks follow the host roof; a rectangular opening is cut in the host shell (disable with `cutRoof:false`). Vary type and dimensions only where observed.
- `b.gable(frame, {width, height, depth, stem = 0, material, roofMaterial, trimMaterial, trimWidth, glass, maxDepth})` — the facade rises above the eave into a peaked gable whose roof runs level and inward until the host roof meets it (a closed cross roof, so a gable taller than the main ridge reads as a cross wing).
- `b.window(frame, {width, height, y, trimMaterial, glass, trimWidth = 0.13, mullions: [2,2], pediment: 'triangular' | 'flat', keystone, out = 0.06})` — modeled jambs, lintel, sill, glass and mullions. Use per floor/edge with `walls({windows:false,...})`; upper-floor ornament may differ. Glass is a separate surface; no actual wall recess is claimed.
- `b.chimney(frame, {width, depth, height, material, capMaterial, pots})` — hollow rectangular shaft/cap with open pots. `height` is above the roof at that point.
- `b.turret(frame, {radius, sides = 8, y = 0, wallTop, roof: 'cone' | 'dome', roofHeight, material, roofMaterial, finial})` — `sides: 4` gives a square tower. `wallTop` is the local shaft top; positive `roofHeight` is the cap rise for both cone and dome. The dome default rise is `radius * 1.05`; the cone default is `radius * 2.2`. A finial begins at the cap apex.
- `b.bay(frame, {width, depth, height, y = 0, storeys, material, glass, roofMaterial, roofHeight})` — a mass projecting out of the facade.
- `b.portal(frame, {width, height, depth, arch = true, material, door, steps})` — entrance surround.
- `b.pilasters(which, {count | spacing, width, out, height, material})`, `b.quoins({size, height, material})`.

## Free geometry (for anything the parts above do not cover)

- `b.box(frame, {w, h, d, y = 0, dx = 0, dz = 0, material})`
- `b.cylinder(frame, {r, rTop, h, y, sides, material})`, `b.cone(frame, {r, h, y, sides, material})`
- `b.prism(frame, {profile: [[x, y], ...], depth, y, dz, material})` — a vertical profile extruded inward.
- `b.loft([{y, points: [[x, z], ...]}, ...], material)` — horizontal rings joined by flat faces.
- `b.add(object3D, frame)` with `b.THREE` for fully custom meshes.

## Look

`b.look({background, ground, sun, sky, exposure})` — daylight colours and intensities (defaults `sun: 3, sky: 2, exposure: 1`).

## Example fragment

```js
export function design(site, b, style) {
  b.material('brick', {color: site.colours.wall, surface: {type: 'brick', scale: 1.2}});
  b.material('slate', {color: site.colours.roof, surface: {type: 'slate', scale: 1.5}});
  b.material('stone', {color: site.colours.trim});
  b.walls({material: 'brick', bay: 3, window: {w: 0.4, h: 0.6, arch: true}});
  b.band({material: 'stone'});
  const roof = b.roof({form: 'hip', material: 'slate'});
  for (const d of site.features.dormers) b.dormer(b.edge(d.edge).at(d.t), {width: d.width_m, material: 'slate', glass: 'stone'});
  for (const f of b.along('long', {spacing: 9, inset: 3})) b.chimney(f, {material: 'stone', height: 1.8});
}
```
