## Vegetation parts (frames from `b.at(x, z, yaw)`; shapes vary with `seed`)

- `b.tree(frame, {height = 8, crown, lobes = 12, trunkMaterial, leafMaterial, seed, lod: 'near'|'medium'|'far', leaves, leafSize, trunkFraction = 0.34, trunkRadius, textured = true})` — branched broadleaf tree with folded alpha-cutout leaf sprays (multiple textured blades per instance), bark texture, and seeded canopy gaps. Defaults: near 3200 / medium 1800 / far 300 leaves. leafSize is the physical blade size (sprays are larger); leaves is the number of instanced sprays, capped at 6000. Leaf colours come from leafMaterial; no fixed palette. `textureSeed` changes shared texture variation independently from geometry seed.
- `b.conifer(frame, {height = 10, crown, tiers = 5, trunkMaterial, leafMaterial})` — stacked-cone evergreen.
- `b.palm(frame, {height = 9, fronds = 9, trunkMaterial, leafMaterial, seed})` — palm with drooping fronds.
- `b.shrub(frame, {radius = 0.8, leafMaterial, seed})`, `b.hedge(frame, {length, height, depth, leafMaterial})`, `b.planter(frame, {width, depth, height, material, soilMaterial})`.
