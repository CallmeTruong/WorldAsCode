## Street parts (frames from `b.at(x, z, yaw)`; local +X runs along the street, +Z across it)

Road/sidewalk use seeded asphalt/concrete albedo, bump and roughness maps by default. `textured:false` keeps the caller's flat material. No source PBR is claimed. `textureScale` is in metres; base colour comes from the caller's material. Road `station_m` is the start distance along a shared road: pass it consistently across segments to preserve dash phase. `dashLength`/`dashGap` set the pattern. These are straight segment primitives, not a road-network solver.

- `b.lamp(frame, {height = 7, arm = 1.6, material, lightMaterial})` — street lamp; give `lightMaterial` a `glow` to light it at night.
- `b.bench(frame, {width, material, legMaterial})`, `b.bollard(frame, {height, radius, material})`, `b.bin(frame, {height, material})`, `b.hydrant(frame, {material})`.
- `b.roadSign(frame, {height, size, material, poleMaterial})`, `b.trafficLight(frame, {height, material, red, amber, green})` — lens options are material names.
- `b.busShelter(frame, {width, depth, height, material, glass})`, `b.fence(frame, {length, height, spacing, material, solid, panelMaterial})`.
- `b.road(frame, {length, width, lanes, material, marking})`, `b.sidewalk(frame, {length, width, kerb, material, kerbMaterial})`, `b.crosswalk(frame, {width, length, material})` — ground surfaces along the frame's X axis.
