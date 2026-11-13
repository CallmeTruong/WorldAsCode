// Area scene: ground, surfaces, roads, rails, trees, street objects and buildings in one frame.
// Buildings go through the building kit with a recipe per material class; everything else is
// merged or instanced so a whole block costs a handful of draw calls.
// Frame: X east, Y up, Z south, metres.
import * as THREE from 'three';
import {mergeGeometries} from 'three/addons/utils/BufferGeometryUtils.js';

const flat = color => new THREE.MeshStandardMaterial({color, roughness: .92});
function meshOf(positions, material, name) {
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3)); g.computeVertexNormals();
  const m = new THREE.Mesh(g, material); m.name = name; m.receiveShadow = true; return m;
}
// A strip of constant width along a polyline, with round joints so bends and junctions close.
function ribbon(out, points, width, y) {
  const h = width / 2;
  for (let i = 0; i + 1 < points.length; i++) {
    const [ax, az] = points[i], [bx, bz] = points[i + 1], len = Math.hypot(bx - ax, bz - az); if (len < 1e-6) continue;
    const nx = -(bz - az) / len * h, nz = (bx - ax) / len * h;
    out.push(ax + nx, y, az + nz, bx + nx, y, bz + nz, bx - nx, y, bz - nz, ax + nx, y, az + nz, bx - nx, y, bz - nz, ax - nx, y, az - nz);
  }
  for (const [cx, cz] of points) for (let k = 0; k < 10; k++) { const a = k / 10 * Math.PI * 2, b = (k + 1) / 10 * Math.PI * 2; out.push(cx, y, cz, cx + Math.sin(b) * h, y, cz + Math.cos(b) * h, cx + Math.sin(a) * h, y, cz + Math.cos(a) * h); }
}
// Vertical skirt under an elevated ribbon, so a viaduct reads as a solid deck.
function skirt(out, points, width, y0, y1) {
  const h = width / 2;
  for (let i = 0; i + 1 < points.length; i++) {
    const [ax, az] = points[i], [bx, bz] = points[i + 1], len = Math.hypot(bx - ax, bz - az); if (len < 1e-6) continue;
    const nx = -(bz - az) / len * h, nz = (bx - ax) / len * h;
    for (const s of [1, -1]) { const p = [ax + s * nx, az + s * nz], q = [bx + s * nx, bz + s * nz]; out.push(p[0], y0, p[1], q[0], y0, q[1], q[0], y1, q[1], p[0], y0, p[1], q[0], y1, q[1], p[0], y1, p[1], p[0], y0, p[1], q[0], y1, q[1], q[0], y0, q[1], p[0], y0, p[1], p[0], y1, p[1], q[0], y1, q[1]); }
  }
}
function dashes(out, points, y, lateral, width, dash, gap, trim) {
  let total = 0; const lengths = []; for (let i = 0; i + 1 < points.length; i++) { const l = Math.hypot(points[i + 1][0] - points[i][0], points[i + 1][1] - points[i][1]); lengths.push(l); total += l; }
  let travelled = 0;
  for (let i = 0; i + 1 < points.length; i++) {
    const [ax, az] = points[i], len = lengths[i]; if (len < 1e-6) continue;
    const dx = (points[i + 1][0] - ax) / len, dz = (points[i + 1][1] - az) / len, nx = -dz, nz = dx;
    for (let s = Math.floor(travelled / (dash + gap)) * (dash + gap) - travelled; s < len; s += dash + gap) {
      const start=Math.max(0,s,trim-travelled),e=Math.min(s+dash,len,total-trim-travelled);if(e<=start)continue;
      const p = [ax + dx * start + nx * lateral, az + dz * start + nz * lateral], q = [ax + dx * e + nx * lateral, az + dz * e + nz * lateral], w = width / 2;
      out.push(p[0] + nx * w, y, p[1] + nz * w, q[0] + nx * w, y, q[1] + nz * w, q[0] - nx * w, y, q[1] - nz * w, p[0] + nx * w, y, p[1] + nz * w, q[0] - nx * w, y, q[1] - nz * w, p[0] - nx * w, y, p[1] - nz * w);
    }
    travelled += len;
  }
}
function surface(polygon, y, material, name,holes=[]) {
  const shape = new THREE.Shape(polygon.map(([x, z]) => new THREE.Vector2(x, -z)));shape.holes=holes.map(h=>new THREE.Path(h.map(([x,z])=>new THREE.Vector2(x,-z))));const g = new THREE.ShapeGeometry(shape); g.rotateX(-Math.PI / 2);
  const m = new THREE.Mesh(g, material); m.position.y = y; m.name = name; m.receiveShadow = true; return m;
}
function box(w, h, d, x, y, z, yaw = 0) { const g = new THREE.BoxGeometry(w, h, d); g.translate(0, h / 2, 0); g.rotateY(yaw); g.translate(x, y, z); return g; }
function post(r, h, x, y, z) { const g = new THREE.CylinderGeometry(r * .7, r, h, 8); g.translate(x, y + h / 2, z); return g; }

// Measured surfaces: the ground and every roof carry the true orthophoto, every wall carries
// its own facade image. Colours come from the captures, so these materials are unlit: the
// capture already contains the light it was taken in.
function measuredSurfaces(scene, add) {
  const photo = scene.photo, loader = new THREE.TextureLoader(), half = photo.ortho.half_m;
  const texture = name => { const t = loader.load('./' + name); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; return t; };
  const orthoMaterial = new THREE.MeshBasicMaterial({map: texture(photo.ortho.image), toneMapped: false});
  const wallMaterial = new THREE.MeshBasicMaterial({map: texture(photo.atlas.image), toneMapped: false, side: THREE.DoubleSide});
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(2 * half, 2 * half), orthoMaterial); ground.rotation.x = -Math.PI / 2; ground.position.y = .02; ground.name = 'ground-orthophoto';
  add(ground, 'ground-orthophoto', 'ground');
  const orthoUV = (x, z) => [(x + half) / (2 * half), (half - z) / (2 * half)];
  const wallPositions = [], wallUVs = [], roofPositions = [], roofUVs = [], W = photo.atlas.width, H = photo.atlas.height;
  for (const mass of photo.masses) {
    const p = mass.polygon, n = p.length;
    for (let i = 0; i < n; i++) {
      const rect = mass.walls[i]; if (!rect) continue;
      const a = p[i], b = p[(i + 1) % n], [rx, ry, rw, rh] = rect, u0 = (rx + .5) / W, u1 = (rx + rw - .5) / W, vTop = 1 - (ry + .5) / H, vBottom = 1 - (ry + rh - .5) / H;
      wallPositions.push(a[0], mass.y0, a[1], b[0], mass.y0, b[1], b[0], mass.y1, b[1], a[0], mass.y0, a[1], b[0], mass.y1, b[1], a[0], mass.y1, a[1]);
      wallUVs.push(u0, vBottom, u1, vBottom, u1, vTop, u0, vBottom, u1, vTop, u0, vTop);
    }
    const contour = p.map(([x, z]) => new THREE.Vector2(x, -z)), holes = (mass.holes ?? []).map(h => h.map(([x, z]) => new THREE.Vector2(x, -z)));
    const vertices = [...p, ...(mass.holes ?? []).flat()];
    for (const face of THREE.ShapeUtils.triangulateShape(contour, holes)) for (const i of face) { const [x, z] = vertices[i]; roofPositions.push(x, mass.y1, z); roofUVs.push(...orthoUV(x, z)); }
  }
  const geometry = (positions, uvs) => { const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3)); g.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2)); return g; };
  const roofMaterial = orthoMaterial.clone(); roofMaterial.side = THREE.DoubleSide;
  add(new THREE.Mesh(geometry(wallPositions, wallUVs), wallMaterial), 'measured-walls', 'building');
  add(new THREE.Mesh(geometry(roofPositions, roofUVs), roofMaterial), 'measured-roofs', 'building');
}

export function buildArea(scene, {buildDesign, recipes, packs = []}) {
  const root = new THREE.Group(), palette = scene.palette, components = []; root.name = 'area';
  const add = (object, id, kind) => { const pivot = new THREE.Group(); pivot.name = id + ':pivot'; pivot.add(object); root.add(pivot); components.push({instance: 'area', component: {id, kind, semantic_requirements: []}, node: object, pivot}); return object; };
  if (scene.photo) {
    measuredSurfaces(scene, add);
    if (scene.trees.length) {
      const trunk = new THREE.InstancedMesh(new THREE.CylinderGeometry(.5, .7, 1, 7), new THREE.MeshBasicMaterial({color: palette.bark, toneMapped: false}), scene.trees.length);
      const crown = new THREE.InstancedMesh(new THREE.IcosahedronGeometry(1, 1), new THREE.MeshLambertMaterial({color: '#ffffff'}), scene.trees.length * 3), dummy = new THREE.Object3D(), colour = new THREE.Color();
      scene.trees.forEach((t, i) => {
        const h = t.height_m, r = t.crown_m ?? Math.max(1.6, h * .3), th = h * .42;
        dummy.position.set(t.x, th / 2, t.z); dummy.rotation.set(0, 0, 0); dummy.scale.set(h * .035, th, h * .035); dummy.updateMatrix(); trunk.setMatrixAt(i, dummy.matrix);
        for (let k = 0; k < 3; k++) { const a = t.seed * 1.7 + k * 2.1, o = k ? r * .42 : 0; dummy.position.set(t.x + Math.cos(a) * o, th + r * (.55 + .28 * k), t.z + Math.sin(a) * o); dummy.rotation.set(0, a, 0); const s = r * (k ? .72 : 1); dummy.scale.set(s, s * .82, s); dummy.updateMatrix(); crown.setMatrixAt(i * 3 + k, dummy.matrix);
          crown.setColorAt(i * 3 + k, t.colour ? colour.setRGB(t.colour[0] / 255, t.colour[1] / 255, t.colour[2] / 255, THREE.SRGBColorSpace) : colour.set(palette.leaf[(t.seed + k) % palette.leaf.length])); }
      });
      add(trunk, 'tree-trunks', 'vegetation'); add(crown, 'tree-crowns', 'vegetation');
    }
    root.userData.objectKind = 'area'; root.userData.components = components; root.userData.buildFailures = []; root.userData.buildWarnings = [];
    root.userData.buildingIds = scene.buildings.map(b => b.id);
    root.userData.look = {background: '#aebfcd', ground: '#4b5158', sun: 1.6, sky: 1.6, exposure: 1};
    root.updateMatrixWorld(true);
    return root;
  }

  root.userData.objectKind='area';
  for (const s of scene.surfaces) add(surface(s.polygon, s.kind === 'water' ? .03 : .05, flat(palette[s.kind === 'paved' ? 'sidewalk' : s.kind] ?? palette.plaza), s.id,s.holes), 'surface:' + s.id, 'ground');

  const walk = [], carriage = [], paint = [];
  for (const p of scene.paths) ribbon(walk, p.points, p.width_m, .07);
  for (const r of scene.roads) if (r.layer <= 0 && r.sidewalk_m > 0) ribbon(walk, r.points, r.width_m + 2 * r.sidewalk_m, .08);
  for (const r of scene.roads) if (r.layer <= 0) ribbon(carriage, r.points, r.width_m, .11);
  for (const r of scene.roads) if (r.layer <= 0 && r.marking) {
    if (r.oneway) for (let k = 1; k < r.lanes; k++) dashes(paint, r.points, .125, -r.width_m / 2 + r.width_m * k / r.lanes, .14, 3, 5, 9);
    else { dashes(paint, r.points, .125, 0, .16, 400, 0, 9); for (let k = 1; k < r.lanes; k++) if (k !== r.lanes / 2) dashes(paint, r.points, .125, -r.width_m / 2 + r.width_m * k / r.lanes, .13, 3, 5, 9); }
  }
  for (const c of scene.points) if (c.kind === 'crossing' && c.road_width_m) {
    const a = c.heading_rad ?? 0, dx = Math.cos(a), dz = -Math.sin(a), nx = -dz, nz = dx, n = Math.max(3, Math.round(c.road_width_m / .9));
    for (let i = 0; i < n; i++) { const o = -c.road_width_m / 2 + c.road_width_m * (i + .5) / n, w = c.road_width_m / n * .28, cx = c.x + nx * o, cz = c.z + nz * o, L = 2;
      paint.push(cx - dx * L + nx * w, .13, cz - dz * L + nz * w, cx + dx * L + nx * w, .13, cz + dz * L + nz * w, cx + dx * L - nx * w, .13, cz + dz * L - nz * w, cx - dx * L + nx * w, .13, cz - dz * L + nz * w, cx + dx * L - nx * w, .13, cz + dz * L - nz * w, cx - dx * L - nx * w, .13, cz - dz * L - nz * w); }
  }
  if (walk.length) add(meshOf(walk, flat(palette.sidewalk), 'sidewalks'), 'sidewalks', 'ground');
  if (carriage.length) add(meshOf(carriage, flat(palette.road), 'roads'), 'roads', 'ground');
  if (paint.length) add(meshOf(paint, new THREE.MeshStandardMaterial({color: palette.marking, roughness: .8, side: THREE.DoubleSide}), 'markings'), 'markings', 'ground');

  // Elevated roads and railways stand on a deck one storey per layer.
  const deck = [], bed = [], steel = [],elevatedRoads=[];
  for (const r of scene.roads) if (r.layer > 0) { const y = r.layer * 6.5; ribbon(deck, r.points, r.width_m + 1, y); skirt(deck, r.points, r.width_m + 1, y - 1.2, y); ribbon(elevatedRoads, r.points, r.width_m, y + .03); }
  for (const r of scene.rails) { const y = r.layer > 0 ? r.layer * 6.5 : .1; if (r.layer > 0) { ribbon(deck, r.points, 4.6, y - .15); skirt(deck, r.points, 4.6, y-1.2, y - .15); } ribbon(bed, r.points, 3.2, y); for (const s of [-1, 1]) dashes(steel, r.points, y + .12, s * r.gauge_m / 2, .09, 1e6, 0, 0); }
  if(elevatedRoads.length)add(meshOf(elevatedRoads,flat(palette.road),'elevated-roads'),'elevated-roads','ground');
  if (deck.length) { const m = meshOf(deck, new THREE.MeshStandardMaterial({color: palette.deck, roughness: .9, side: THREE.DoubleSide}), 'decks'); m.castShadow = true; add(m, 'decks', 'structure'); }
  if (bed.length) add(meshOf(bed, flat(palette.rail_bed), 'rail-beds'), 'rail-beds', 'ground');
  if (steel.length) add(meshOf(steel, new THREE.MeshStandardMaterial({color: palette.rail, roughness: .5, metalness: .6, side: THREE.DoubleSide}), 'rails'), 'rails', 'ground');

  // Trees: two instanced meshes for the whole area; size and tint vary per tree.
  if (scene.trees.length) {
    const trunk = new THREE.InstancedMesh(new THREE.CylinderGeometry(.5, .7, 1, 7), new THREE.MeshStandardMaterial({color: palette.bark, roughness: .95}), scene.trees.length);
    const crown = new THREE.InstancedMesh(new THREE.IcosahedronGeometry(1, scene.style?.tree_detail??1), new THREE.MeshStandardMaterial({color: '#ffffff', roughness: .9, flatShading: (scene.style?.tree_detail??1)<2}), scene.trees.length * 3);
    const wind={strength:{value:0},time:{value:0}};crown.material.userData.wind=wind;
    crown.material.userData.base={roughness:.9,weather_response:true};
    crown.material.onBeforeCompile=shader=>{shader.uniforms.areaWind=wind.strength;shader.uniforms.areaTime=wind.time;
      shader.vertexShader='uniform float areaWind;uniform float areaTime;\n'+shader.vertexShader;
      shader.vertexShader=shader.vertexShader.replace('#include <begin_vertex>','#include <begin_vertex>\ntransformed.x += areaWind * .07 * sin(areaTime * 1.6 + instanceMatrix[3].x * .09 + instanceMatrix[3].z * .13) * (position.y + 1.);');};
    crown.material.customProgramCacheKey=()=> 'area-tree-wind-1';
    const dummy = new THREE.Object3D(), colour = new THREE.Color(); trunk.castShadow = crown.castShadow = true; crown.receiveShadow = true;
    scene.trees.forEach((t, i) => {
      const h = t.height_m, r = t.crown_m ?? Math.max(1.6, h * .3), th = h * .42;
      dummy.position.set(t.x, th / 2, t.z); dummy.rotation.set(0, 0, 0); dummy.scale.set(h * .035, th, h * .035); dummy.updateMatrix(); trunk.setMatrixAt(i, dummy.matrix);
      for (let k = 0; k < 3; k++) { const a = t.seed * 1.7 + k * 2.1, o = k ? r * .42 : 0;
        dummy.position.set(t.x + Math.cos(a) * o, th + r * (.55 + .28 * k), t.z + Math.sin(a) * o); dummy.rotation.set(0, a, 0); const s = r * (k ? .72 : 1); dummy.scale.set(s, s * .82, s); dummy.updateMatrix(); crown.setMatrixAt(i * 3 + k, dummy.matrix);
        crown.setColorAt(i * 3 + k, colour.set(t.render_colour??palette.leaf[(t.seed + k) % palette.leaf.length])); }
    });
    add(trunk, 'tree-trunks', 'vegetation'); add(crown, 'tree-crowns', 'vegetation');
  }

  // Street objects, merged by material.
  const metal = [], light = [], accent = [];
  for (const p of scene.points) {
    const yaw = p.heading_rad ?? 0;
    if (p.kind === 'lamp') { metal.push(post(.09, 7, p.x, 0, p.z), box(.1, .1, 1.5, p.x, 6.9, p.z, yaw)); light.push(box(.3, .12, .6, p.x + Math.sin(yaw) * .75, 6.8, p.z + Math.cos(yaw) * .75, yaw)); }
    else if (p.kind === 'traffic_light') { const o = (p.road_width_m ?? 7) / 2 + 1, x = p.x - Math.sin(yaw) * o, z = p.z - Math.cos(yaw) * o; metal.push(post(.07, 4.2, x, 0, z), box(.32, .95, .28, x, 3.3, z, yaw)); light.push(box(.16, .16, .05, x + Math.cos(yaw) * .16, 3.95, z - Math.sin(yaw) * .16, yaw)); }
    else if (p.kind === 'bus_stop') { metal.push(post(.04, 2.6, p.x, 0, p.z)); accent.push(box(.5, .5, .05, p.x, 2.1, p.z, yaw)); }
    else if (p.kind === 'bollard') metal.push(post(.1, .9, p.x, 0, p.z));
    else if (p.kind === 'bench') metal.push(box(1.8, .45, .5, p.x, 0, p.z, yaw));
    else if (p.kind === 'hydrant' || p.kind === 'post_box') accent.push(box(.4, p.kind === 'post_box' ? 1.2 : .6, .4, p.x, 0, p.z));
    else if (p.kind === 'vending' || p.kind === 'phone') light.push(box(1, 1.9, .8, p.x, 0, p.z, yaw));
    else if (p.kind === 'bin') metal.push(post(.28, .9, p.x, 0, p.z));
  }
  for (const [list, material, id] of [[metal, new THREE.MeshStandardMaterial({color: palette.metal, roughness: .6, metalness: .4}), 'street-metal'], [light, new THREE.MeshStandardMaterial({color: '#f1efe6', roughness: .5, emissive: '#ffd28a', emissiveIntensity: 0}), 'street-light'], [accent, new THREE.MeshStandardMaterial({color: '#c8473c', roughness: .6}), 'street-accent']])
    if (list.length) { const m = new THREE.Mesh(mergeGeometries(list.map(g => g.toNonIndexed()), false), material); m.castShadow = true; if (id === 'street-light') material.userData.base = {roughness: .5, emissive_at_night: true, weather_response: false}; add(m, id, 'street'); }

  // Buildings: one kit design per building, placed at its anchor.
  const failures = [],warnings=[],buildingIds=[];
  for (const entry of scene.buildings) {
    const recipeKey=entry.site.recipe_family??entry.site.appearance.class;
    const recipe = recipes[recipeKey] ?? (scene.requireAuthoredRecipes?null:recipes.midrise);
    let built;
    try { built = buildDesign(recipe, entry.site, scene.style ?? {}, packs); }
    catch (error) { failures.push({id: entry.id, class: entry.site.appearance.class,recipe_family:recipeKey, error: String(error.message ?? error)}); try { built = buildDesign(recipes.fallback, entry.site, scene.style ?? {}, packs); } catch (again) { failures[failures.length - 1].fallback_error = String(again.message ?? again); continue; } }
    built.name = entry.id; built.position.set(entry.anchor[0], entry.elevation_m??0, entry.anchor[1]); root.add(built);
    buildingIds.push(entry.id);
    if(built.userData.look?.recipeWarnings?.length)warnings.push({entity_id:entry.id,operations:built.userData.look.recipeWarnings});
    for (const part of built.userData.components ?? []) components.push({...part, instance: entry.id,entity_id:entry.id,local_component_id:part.component.id,component:{...part.component,id:entry.id+'::'+part.component.id}});
  }
  root.userData.components = components; root.userData.buildFailures = failures;root.userData.buildWarnings=warnings;root.userData.buildingIds=buildingIds;
  root.userData.look = {background: palette.background, ground: palette.ground, sun: 2.4, sky: 1.2, exposure: .9,...scene.style?.light};
  root.updateMatrixWorld(true);
  const bounds=o=>{const b=new THREE.Box3().setFromObject(o);return {min:b.min.toArray(),max:b.max.toArray()};};
  root.userData.entityIndex=Object.fromEntries(root.children.filter(o=>buildingIds.includes(o.name)).map(o=>[o.name,{bounds:bounds(o)}]));
  root.userData.componentIndex=Object.fromEntries(components.filter(p=>p.entity_id).map(p=>[p.component.id,{entity_id:p.entity_id,kind:p.component.kind,bounds:bounds(p.pivot)}]));
  return root;
}
