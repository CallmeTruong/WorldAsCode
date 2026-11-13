// Building recipes by material class. Each is an ordinary kit design script: it reads
// everything from `site` (measured outline, heights, roof structure, palette colours) and
// contains no coordinates of its own, so one recipe serves every building of its class.
// A style or an agent may replace any recipe; the area pipeline only needs these names.

let recipeWarnings=[];
const attempt = fn => { try { return fn(); } catch (error) { recipeWarnings.push(String(error.message??error));return null; } };
const shade = (hex, f) => '#' + [1, 3, 5].map(i => Math.max(0, Math.min(255, Math.round(parseInt(hex.slice(i, i + 2), 16) * f))).toString(16).padStart(2, '0')).join('');
const blend = (a, b, t) => '#' + [1, 3, 5].map(i => Math.round(parseInt(a.slice(i, i + 2), 16) * (1 - t) + parseInt(b.slice(i, i + 2), 16) * t).toString(16).padStart(2, '0')).join('');

function materials(site, b, wall) {
  const a = site.appearance;
  b.material('wall', wall); b.material('roof', {color: a.roof, roughness: .9}); b.material('trim', {color: a.trim, roughness: .85});
  b.material('plant', {color: a.plant, roughness: .8}); b.material('glass', {color: a.glass, roughness: .25, metalness: .2});
}
// Roof from what was measured: fitted sections when the roof is pitched, otherwise a flat
// roof with a parapet and the plant rooms or penthouses found standing on it.
function roof(site, b, style = {}) {
  const r = site.roof;
  if (r.form === 'sections') {
    b.roofSections({material: 'roof', endMaterial: 'wall'});
    if(style.roof_detail!==false) for (const v of r.volumes ?? []) attempt(() => b.volume(b.at(v.x, v.z, v.rotation_y_rad), {width: v.width_m, depth: v.depth_m, y: v.base_m - 1.5, shoulder: v.shoulder_m, top: v.top_m, cap: v.cap, material: 'wall', roofMaterial: 'roof'}));
    return;
  }
  if (r.form !== 'flat' && attempt(() => b.roof({form: r.form, rise: r.rise_m, material: 'roof'}))) return;
  b.roof({form:'flat',material:'roof',overhang:0,parapet:.02});
  if(style.roof_detail===false)return;
  attempt(() => b.parapet({material: 'trim', height: site.eave_m > 40 ? 1.4 : .9, thickness: .35}));
  for (const v of r.volumes ?? []) attempt(() => b.volume(b.at(v.x, v.z, v.rotation_y_rad), {width: Math.max(2, v.width_m - 1), depth: Math.max(2, v.depth_m - 1), y: site.eave_m - .2, shoulder: v.top_m, cap: 'flat', material: 'plant', roofMaterial: 'plant'}));
  for (const m of r.mechanical ?? []) attempt(() => b.mechanical(b.at(m.x, m.z, m.yaw), {width: m.width_m, depth: m.depth_m, height: m.height_m, material: 'plant'}));
}

const definitions = {
  // Curtain-wall tower: glass field with light mullions and spandrels, darker base.
  glass_tower(site, b) {
    const a = site.appearance;
    materials(site, b, {color: blend(a.wall, a.frame, .55), roughness: .4, metalness: .15});
    b.walls({material: 'wall', bay: 1.7, window: {w: .86, h: .74, sill: .12, frame: a.frame, glass: shade(a.wall, .82), mullions: [1, 1]}});
    attempt(() => b.band({y: 0, height: Math.min(6, site.eave_m * .08), out: .2, material: 'trim'}));
    roof(site, b);
  },
  // Stone-clad tower: vertical piers with narrow tall windows, a podium line and a cornice.
  stone_tower(site, b) {
    const a = site.appearance;
    materials(site, b, {color: a.wall, roughness: .85});
    b.walls({material: 'wall', bay: 2.4, window: {w: .5, h: .72, sill: .14, frame: shade(a.wall, .9), glass: a.glass, mullions: [1, 2]}});
    attempt(() => b.band({y: Math.min(12, site.eave_m * .12), height: .7, out: .3, material: 'trim'}));
    attempt(() => b.band({y: site.eave_m - 1.2, height: 1.2, out: .35, material: 'trim'}));
    roof(site, b);
  },
  // Mid-rise office or commercial block: regular window grid, taller glazed ground floor.
  midrise(site, b) {
    const a = site.appearance;
    materials(site, b, {color: a.wall, roughness: .85});
    b.walls({material: 'wall', bay: 3, window: {w: .62, h: .58, sill: .22, frame: a.trim, glass: a.glass, mullions: [2, 1]}, course: shade(a.wall, .88)});
    attempt(() => b.band({y: 0, height: .6, out: .12, material: 'trim'}));
    attempt(() => b.band({y: site.eave_m / site.storeys, height: .35, out: .22, material: 'trim'}));
    attempt(() => b.band({y: site.eave_m - .6, height: .6, out: .3, material: 'trim'}));
    roof(site, b);
  },
  lowrise(site, b) {
    const a = site.appearance;
    materials(site, b, {color: a.wall, roughness: .85});
    b.walls({material: 'wall', bay: 3.2, window: {w: .6, h: .6, sill: .2, frame: a.trim, glass: a.glass, mullions: [2, 1]}});
    attempt(() => b.band({y: site.eave_m - .4, height: .4, out: .2, material: 'trim'}));
    roof(site, b);
  },
  // Masonry building with stone dressings; pitched roofs, dormers and stacks where measured.
  brick(site, b) {
    const a = site.appearance;
    materials(site, b, {color: a.wall, roughness: .9, surface: {type: 'brick', scale: 2.4}});
    b.walls({material: 'wall', bay: 3.2, window: {w: .42, h: .62, sill: .2, frame: a.trim, glass: a.glass, mullions: [2, 2]}, course: a.trim});
    attempt(() => b.band({y: 0, height: .8, out: .15, material: 'trim'}));
    attempt(() => b.cornice({material: 'trim', steps: 3, height: .8, out: .4}));
    roof(site, b);
    for (const d of site.features?.dormers ?? []) attempt(() => b.dormer(b.edge(d.edge).at(d.t), {width: Math.min(2.2, d.width_m), height: 2, material: 'roof', roofMaterial: 'roof', glass: 'glass'}));
    for (const c of site.features?.chimneys ?? []) attempt(() => b.chimney(b.at(c.x, c.z, site.axis_yaw ?? 0), {material: 'wall', capMaterial: 'trim', height: c.height_m, pots: 2}));
  },
  // Driven by what was observed: two facade tones, the share of glazing and whether the wall
  // reads as floor bands, vertical fins or a grid. The style has already turned those facts
  // into colours and proportions, so this one recipe serves every observed building.
  observed(site, b, style = {}) {
    const a = site.appearance, f = a.facade;
    materials(site, b, {color: a.wall, roughness: f.glassy ? .42 : .85, metalness: f.glassy ? .18 : 0});
    b.walls({material: 'wall', bay: f.bay, window: {w: f.w, h: f.h, sill: f.sill, frame: a.frame, glass: a.glass, mullions: f.mullions, glow: a.glow ?? undefined}, course: f.course ? a.trim : undefined});
    if(style.facade_mode==='relief') {
      b.material('frame',{color:a.frame,roughness:.7});
      const depth=style.relief_m??.18, storeys=Math.min(80,Math.max(1,site.storeys));
      for(const edge of site.edges) {
        const bay=Math.max(f.bay,edge.length_m/48);
        if(f.rhythm==='fins') attempt(()=>b.fins(edge.id,{material:'frame',spacing:bay,depth,thickness:.12,top:site.eave_m}));
        else attempt(()=>b.frameGrid(edge.id,{material:'frame',bay,storeys,columnWidth:f.rhythm==='bands'?.06:.12,beamHeight:f.rhythm==='bands'?.2:.09,out:depth}));
      }
    }
    if (!site.part_of) attempt(() => b.band({y: 0, height: Math.min(5, Math.max(.6, site.eave_m * .06)), out: .15, material: 'trim'}));
    if (!f.glassy) attempt(() => b.band({y: site.eave_m - .7, height: .7, out: .28, material: 'trim'}));
    roof(site, b, style);
  },
  // Free-standing roof on posts (station canopy, shelter): no enclosed walls.
  canopy(site, b) {
    const a = site.appearance, h = site.eave_m;
    b.material('roof', {color: a.roof, roughness: .7}); b.material('post', {color: '#8f959a', roughness: .6, metalness: .4});
    b.loft([{y: h - .35, points: site.footprint}, {y: h, points: site.footprint}], 'roof');
    for (const [x, z] of site.footprint) b.box(b.at(x * .94, z * .94), {w: .3, h: h - .35, d: .3, material: 'post'});
  },
  // A mass that starts above the ground (bridge link, overhang).
  raised(site, b) {
    const a = site.appearance;
    b.material('wall', {color: a.wall, roughness: .7});
    b.loft([{y: site.min_height_m, points: site.footprint}, {y: site.eave_m, points: site.footprint}], 'wall');
  },
  // Plain measured mass, used when a class recipe cannot build an unusual outline.
  fallback(site, b) {
    const a = site.appearance;
    b.material('wall', {color: a.wall ?? '#c9c5bb', roughness: .85});
    if ((site.kind ?? 'building') === 'building') b.walls({material: 'wall', windows: false});
    else b.loft([{y: site.min_height_m ?? 0, points: site.footprint}, {y: site.eave_m, points: site.footprint}], 'wall');
  },
};
export const recipes=Object.fromEntries(Object.entries(definitions).map(([name,recipe])=>[name,(site,b,style)=>{
  recipeWarnings=[];recipe(site,b,style);b.look({recipeWarnings:[...recipeWarnings]});
}]));
