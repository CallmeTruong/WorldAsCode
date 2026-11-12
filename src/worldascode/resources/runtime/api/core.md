# Building kit API

Write one ES module: `export function design(site, b, style) { ... }`. No imports. Units are metres. Y is up.


## What you receive

`site` (measured, read-only):
- `eave_m` wall-top height, `ridge_m` main roof top, `top_m` highest feature, `storeys`
- `roof`: `{form, pitch_deg}` as measured (a hint; you choose the form)
- `edges`: `[{id, length_m, facing, end}]` — `facing` is the compass side the wall looks at; `end: true` marks the short end of a wing
- `wings`: `[{length_m, width_m, centre_xz, rotation_y_rad, corners, confidence}]`; optional rectangular layout priors in the same registered frame. Corners retain precision; the protected footprint remains authoritative.
- `observations`: evidence-led roof hierarchy, facade rhythm, material identity and uncertain features from the observer node; these are visual interpretations, not surveyed facts.
- `features` (measured positions, may be missing): `dormers: [{edge, t, width_m, height_m}]`, `chimneys: [{x, z, height_m}]`, `towers: [{x, z, width_m, height_m}]`. `t` is the 0..1 position along that edge.
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


## Look

`b.look({background, ground, sun, sky, exposure})` — daylight colours and intensities (defaults `sun: 3, sky: 2, exposure: 1`).


