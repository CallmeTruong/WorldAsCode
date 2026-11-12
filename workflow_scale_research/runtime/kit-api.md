# Building kit API

Write one ES module: `export function design(site, b, style) { ... }`. No imports. Units are metres. Y is up.

## What you receive

`site` (measured, read-only):
- `eave_m` wall-top height, `ridge_m` main roof top, `top_m` highest feature, `storeys`
- `roof`: `{form, pitch_deg}` as measured (a hint; you choose the form)
- `edges`: `[{id, length_m, facing, end}]` — `facing` is the compass side the wall looks at; `end: true` marks the short end of a wing
- `wings`: `[{length_m, width_m}]`
- `features` (measured positions, may be missing): `dormers: [{edge, t, width_m, height_m}]`, `chimneys: [{x, z, height_m}]`, `towers: [{x, z, width_m, height_m}]`. `t` is the 0..1 position along that edge.
- `colours`: `{wall, roof, trim}` sampled or estimated material colours
- `tags`: map tags such as architecture style

`style`: transferable treatment of materials, proportions, detail and lighting; never a fixed palette.

## Rules

- Call `b.walls(...)` exactly once, before the roof. The wall outline is the measured footprint and cannot be changed.
- Declare every material with `b.material(name, spec)` before using its name.
- Place parts with frames. A frame from an edge has local +X along the wall and local +Z pointing out of the building. Never compute world coordinates of walls yourself.
- Keep measured heights within about 15%. Exaggerate detail, colour and proportion of ornaments as the style asks, not the building's size.
- Use loops. Aim for 60–150 lines.

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

- `b.walls({material, height = site.eave_m, storeys = site.storeys, bay = 3.2, window: {w, h, sill, arch, mullions: [cols, rows], frame, glass, glow}, course, windows = true})` — `bay` is window spacing in metres; `w`/`h`/`sill` are fractions of a bay/storey; `course` is a colour for a line at each floor.
- `b.band({y, height = 0.4, out = 0.25, material})` — horizontal band around the whole outline (cornice, plinth, string course).
- `b.roof({form: 'hip' | 'gable' | 'mansard' | 'flat', rise, overhang = 0.3, material, lowerFraction, lowerRun, parapet})` → `{ridgeY, eaveY}`. `rise` defaults to the measured ridge.
- `b.ground({material, margin = 3})` — pavement slab around the building.

## Architectural parts (first argument is a frame)

- `b.dormer(frame, {width, height, depth, roof: 'gable' | 'shed' | 'flat', material, roofMaterial, trimMaterial, glass, setback = 0.6})` — side cheeks follow the host roof; a rectangular opening is cut in the host shell (disable with `cutRoof:false`). Vary type and dimensions only where observed.
- `b.gable(frame, {width, height, depth, stem = 0, material, roofMaterial, trimMaterial, trimWidth, glass})` — facade-plane gable with sloped trim; the back roof blends into sampled host height and cuts the underlying shell. Use for prominent tall gables; do not substitute uniform small dormers. This is a local attachment, not a general ridge/valley solver.
- `b.window(frame, {width, height, y, trimMaterial, glass, trimWidth = 0.13, mullions: [2,2], pediment: 'triangular' | 'flat', keystone, out = 0.06})` — modeled jambs, lintel, sill, glass and mullions. Use per floor/edge with `walls({windows:false,...})`; upper-floor ornament may differ. Glass is a separate surface; no actual wall recess is claimed.
- `b.chimney(frame, {width, depth, height, material, capMaterial, pots})` — hollow rectangular shaft/cap with open pots. `height` is above the roof at that point.
- `b.turret(frame, {radius, sides = 8, y = 0, wallTop, roof: 'cone' | 'dome', roofHeight, material, roofMaterial, finial})` — `sides: 4` gives a square tower.
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
