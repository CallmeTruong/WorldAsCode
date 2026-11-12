## Materials

`b.material(name, {color, roughness = 0.8, metalness = 0, surface, glow})`
- `surface`: `{type: 'plain' | 'brick' | 'slate' | 'stripes' | 'panels', scale: metres per TILE (typically 2.4), course_m, unit_width_m, relief_m, color2}`. Brick defaults: 0.075 m courses and 0.23 m units. Slate: 0.24 m courses / 0.32 m units. Seeded synthetic color/bump/roughness channels, not source PBR. `seed` on material selects a reproducible variant.
- `glow`: emissive colour switched on at night.


