// Building kit: the vocabulary a design script is written in.
//
// A design script is `export function design(site, b, style) { ... }`. It decides what the
// building is made of and how it looks. It does not own the wall plan: `b.walls`, `b.roof`
// and every edge frame come from the measured `site`, so a design can be imaginative
// without drifting off the real footprint.
//
// Frame: X east, Y up, Z south, metres. An edge frame has local +X along the wall and
// local +Z pointing out of the building.
import * as THREE from 'three';
import {mergeGeometries} from 'three/addons/utils/BufferGeometryUtils.js';
import {surfaceMaps, metricUVs} from './surfaces.mjs';
import {cutRoofOpening} from './roof-openings.mjs';

function deepFreeze(value) { if (value && typeof value === 'object' && !Object.isFrozen(value)) { Object.freeze(value); for (const child of Object.values(value)) deepFreeze(child); } return value; }

// ---- plan geometry (counter-clockwise in [x, north]) --------------------------------
const toPlan = fp => { const p = fp.map(([x, z]) => [x, -z]); return area(p) > 0 ? p : p.reverse(); };
const fromPlan = p => p.map(([x, n]) => [x, -n]);
function area(p) { let s = 0; for (let i = 0; i < p.length; i++) { const a = p[i], b = p[(i + 1) % p.length]; s += a[0] * b[1] - b[0] * a[1]; } return s / 2; }
function offset(plan, distances) {
  const n = plan.length, d = typeof distances === 'number' ? plan.map(() => distances) : distances, lines = [];
  for (let i = 0; i < n; i++) {
    const a = plan[i], b = plan[(i + 1) % n]; let dx = b[0] - a[0], dy = b[1] - a[1]; const len = Math.hypot(dx, dy);
    if (len < 1e-9) return null; dx /= len; dy /= len; lines.push([[a[0] - dy * d[i], a[1] + dx * d[i]], [dx, dy]]);
  }
  const out = [];
  for (let i = 0; i < n; i++) {
    const [p, r] = lines[(i + n - 1) % n], [q, s] = lines[i], cross = r[0] * s[1] - r[1] * s[0];
    if (Math.abs(cross) < 1e-9) { out.push([q[0], q[1]]); continue; }
    const t = ((q[0] - p[0]) * s[1] - (q[1] - p[1]) * s[0]) / cross; out.push([p[0] + r[0] * t, p[1] + r[1] * t]);
  }
  for (let i = 0; i < n; i++) { const a = out[i], b = out[(i + 1) % n], dir = lines[i][1]; if ((b[0] - a[0]) * dir[0] + (b[1] - a[1]) * dir[1] <= 1e-6) return null; }
  return area(out) > 1e-6 ? out : null;
}
function insetLimit(plan, weights) {
  let low = 0, high = Math.max(...plan.map((a, i) => Math.hypot(plan[(i + 1) % plan.length][0] - a[0], plan[(i + 1) % plan.length][1] - a[1])));
  for (let i = 0; i < 40; i++) { const mid = (low + high) / 2; if (offset(plan, weights.map(w => mid * w))) low = mid; else high = mid; }
  return low;
}
function inside(plan, x, n) { let c = false; for (let i = 0, j = plan.length - 1; i < plan.length; j = i++) { const a = plan[i], b = plan[j]; if ((a[1] > n) !== (b[1] > n) && x < (b[0] - a[0]) * (n - a[1]) / (b[1] - a[1]) + a[0]) c = !c; } return c; }
function segmentDistance(a, b, x, n) { const dx = b[0] - a[0], dy = b[1] - a[1], t = Math.max(0, Math.min(1, ((x - a[0]) * dx + (n - a[1]) * dy) / (dx * dx + dy * dy))); return Math.hypot(x - a[0] - dx * t, n - a[1] - dy * t); }

// ---- procedural textures -------------------------------------------------------------
function canvasTexture(size, paint) {
  const canvas = document.createElement('canvas'); canvas.width = canvas.height = size; paint(canvas.getContext('2d'), size);
  const t = new THREE.CanvasTexture(canvas); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.anisotropy = 8; return t;
}
function mix(a, b, t) { const x = new THREE.Color(a).lerp(new THREE.Color(b), t); return '#' + x.getHexString(); }
function paintSurface(g, size, color, surface) {
  g.fillStyle = color; g.fillRect(0, 0, size, size);
  if (!surface || surface.type === 'plain') return;
  const c2 = surface.color2 ?? mix(color, '#000000', 0.18);
  if (surface.type === 'brick') { const rows = 8, h = size / rows; g.fillStyle = c2; for (let r = 0; r < rows; r++) { g.fillRect(0, r * h, size, 2); for (let c = 0; c < 4; c++) g.fillRect(((c + (r % 2) / 2) * size / 4) % size, r * h, 2, h); } }
  else if (surface.type === 'slate') { const rows = 6, h = size / rows; for (let r = 0; r < rows; r++) { g.fillStyle = mix(color, '#000000', 0.05 + 0.1 * ((r * 7) % 3) / 2); g.fillRect(0, r * h, size, h - 2); g.fillStyle = c2; g.fillRect(0, (r + 1) * h - 2, size, 2); for (let c = 0; c < 5; c++) g.fillRect(((c + (r % 2) / 2) * size / 5) % size, r * h, 2, h); } }
  else if (surface.type === 'stripes') { const n = surface.count ?? 6; g.fillStyle = c2; for (let i = 0; i < n; i++) g.fillRect(i * size / n, 0, size / n / (surface.ratio ?? 4), size); }
  else if (surface.type === 'panels') { g.strokeStyle = c2; g.lineWidth = 3; g.strokeRect(1.5, 1.5, size - 3, size - 3); }
  else throw Error('KIT_UNKNOWN_SURFACE:' + surface.type);
}
// One tile = one bay wide, one storey tall.
function windowTile(spec, color) {
  const w = spec.window ?? {}, ww = (w.w ?? 0.45), wh = (w.h ?? 0.58), frame = w.frame ?? '#e8e2d4', glass = w.glass ?? '#2c3a46';
  const shape = (g, size, fill) => {
    const pw = ww * size, ph = wh * size, x = (size - pw) / 2, y = size * (1 - (w.sill ?? 0.2)) - ph;
    g.fillStyle = fill; g.fillRect(x, y, pw, ph);
    if (w.arch) { g.beginPath(); g.ellipse(size / 2, y, pw / 2, pw * 0.32, 0, Math.PI, 0); g.fill(); }
    return [x, y, pw, ph];
  };
  const map = canvasTexture(256, (g, size) => {
    paintSurface(g, size, color, spec.surface);
    if (spec.course) { g.fillStyle = spec.course; g.fillRect(0, size - 8, size, 8); }
    const f = Math.max(4, size * 0.03);
    g.save(); g.translate(0, 0); const [x, y, pw, ph] = shape(g, size, frame); g.restore();
    g.fillStyle = frame; g.fillRect(x - f, y - (w.arch ? 0 : f), pw + 2 * f, ph + f + (w.arch ? 0 : f)); g.fillRect(x - 2 * f, y + ph, pw + 4 * f, f * 1.3);
    if (w.arch) { g.beginPath(); g.ellipse(size / 2, y, pw / 2 + f, pw * 0.32 + f, 0, Math.PI, 0); g.fill(); }
    shape(g, size, glass);
    g.fillStyle = frame; const m = w.mullions ?? [2, 2];
    for (let i = 1; i < m[0]; i++) g.fillRect(x + pw * i / m[0] - f / 4, y - (w.arch ? pw * 0.32 : 0), f / 2, ph + (w.arch ? pw * 0.32 : 0));
    for (let i = 1; i < m[1]; i++) g.fillRect(x, y + ph * i / m[1] - f / 4, pw, f / 2);
  });
  map.colorSpace = THREE.SRGBColorSpace;
  const emissiveMap = canvasTexture(256, (g, size) => { g.fillStyle = '#000'; g.fillRect(0, 0, size, size); shape(g, size, '#fff'); });
  return { map, emissiveMap };
}

// ---- builder -------------------------------------------------------------------------
class Builder {
  constructor(site, style) {
    this.site = deepFreeze(structuredClone(site)); this.style = style ?? {}; this.THREE = THREE;
    this.plan = site.footprint ? toPlan(site.footprint) : []; this.holes=(site.holes??[]).map(h=>toPlan(h).reverse()); this.root = new THREE.Group(); this.root.name = site.object_id ?? 'building'; this.root.userData.objectKind=site.kind??'building';
    this.materials = new Map(); this.parts = []; this.counts = {}; this.roofProfile = null; this.lookConfig = {};
    const n = this.plan.length;
    this.edges = this.plan.map((a, i) => {
      const b = this.plan[(i + 1) % n], length = Math.hypot(b[0] - a[0], b[1] - a[1]);
      return { id: 'e' + i, a, b, length, dir: [(b[0] - a[0]) / length, (b[1] - a[1]) / length] };
    });
  }
  // -- materials
  material(name, spec = {}) {
    if (this.materials.has(name)) throw Error('KIT_DUPLICATE_MATERIAL:' + name);
    const opacity=spec.opacity??1;if(!Number.isFinite(opacity)||opacity<0||opacity>1)throw Error('KIT_INVALID_MATERIAL_OPACITY');
    const color = spec.color ?? '#999999', m = new THREE.MeshStandardMaterial({ color, roughness: spec.roughness ?? 0.8, metalness: spec.metalness ?? 0,opacity,transparent:opacity<1,depthWrite:opacity>=1 });
    m.userData.base = { roughness: spec.roughness ?? 0.8, emissive_at_night: false, weather_response: spec.weather ?? true };
    m.userData.spec = { ...spec, color };
    if (spec.surface && spec.surface.type !== 'plain') {
      if (['brick', 'slate', 'panels','asphalt','concrete','bark','foliage','soil'].includes(spec.surface.type)) {
        Object.assign(m, surfaceMaps(color, spec.surface, spec.seed ?? this.site.seed ?? 0));
        m.bumpScale = spec.surface.relief_m ?? (spec.surface.type === 'brick' ? .012 : spec.surface.type==='foliage'?.001:.008);
        if(spec.surface.type==='foliage'){m.side=THREE.DoubleSide;m.alphaTest=.4;}
        m.userData.surfaceProvenance = 'seeded synthetic material; not source PBR';
      } else {
        m.map = canvasTexture(512, (g, size) => paintSurface(g, size, color, spec.surface)); m.map.colorSpace = THREE.SRGBColorSpace;
        m.map.repeat.set(1 / (spec.surface.scale ?? 2), 1 / (spec.surface.scale ?? 2));
      }
      m.color.set('#ffffff');
    }
    if (spec.glow) { m.emissive.set(spec.glow); m.emissiveIntensity = 0; m.userData.base.emissive_at_night = true; }
    this.materials.set(name, m); return name;
  }
  _material(name) { const m = this.materials.get(name); if (!m) throw Error('KIT_UNKNOWN_MATERIAL:' + name + ' (declare it with b.material first)'); return m; }
  _surface(name,surface,seed=0) {
    const base=this._material(name),key=name+'#surface#'+JSON.stringify([surface,seed]);
    if(!this.materials.has(key)){const m=base.clone();Object.assign(m,surfaceMaps(base.userData.spec.color,surface,seed));m.color.set('#ffffff');m.bumpScale=surface.relief_m??(surface.type==='bark'?.025:surface.type==='foliage'?.001:.006);if(surface.type==='foliage'){m.side=THREE.DoubleSide;m.alphaTest=.4;}m.userData.surfaceProvenance='seeded synthetic '+surface.type+'; not recovered source PBR';this.materials.set(key,m);}return this.materials.get(key);
  }
  _facadeMaterial(name, facade) {
    const key = name + '#facade#' + JSON.stringify(facade);
    if (!this.materials.has(key)) {
      const base = this._material(name), spec = base.userData.spec;
      // Facade painting accepts literal CSS colours and declared material IDs.
      // Resolve IDs before Canvas sees them; invalid fillStyle silently retains the previous colour.
      const colour=value=>this.materials.get(value)?.userData.spec.color??value;
      const window=facade.window?{...facade.window,frame:colour(facade.window.frame),glass:colour(facade.window.glass)}:undefined;
      const maps = windowTile({ ...facade,window,course:colour(facade.course), surface: spec.surface }, spec.color);
      const m = new THREE.MeshStandardMaterial({ color: '#ffffff', map: maps.map, emissiveMap: maps.emissiveMap, emissive: facade.window?.glow ?? '#ffcf82', emissiveIntensity: 0, roughness: base.roughness });
      m.userData.base = { roughness: base.roughness, emissive_at_night: true, weather_response: true }; this.materials.set(key, m);
    }
    return this.materials.get(key);
  }
  // -- placement
  edge(id) {
    const e = this.edges.find(v => v.id === id); if (!e) throw Error('KIT_UNKNOWN_EDGE:' + id);
    return { ...e, at: (t, inset = 0) => this._edgeFrame(e, t, inset) };
  }
  _edgeFrame(e, t, inset = 0) {
    // Inward normal of a counter-clockwise edge is (-dy, dx).
    const x = e.a[0] + (e.b[0] - e.a[0]) * t - e.dir[1] * inset, n = e.a[1] + (e.b[1] - e.a[1]) * t + e.dir[0] * inset;
    return { x, z: -n, yaw: Math.atan2(e.dir[1], e.dir[0]), edge: e.id, t };
  }
  along(which, options = {}) {
    const ids = which === 'all' ? this.edges.map(e => e.id) : which === 'long' ? this.site.edges.filter(e => !e.end).map(e => e.id) : which === 'ends' ? this.site.edges.filter(e => e.end).map(e => e.id) : [].concat(which);
    const frames = [];
    for (const id of ids) {
      const e = this.edge(id), margin = options.margin ?? 1.5, usable = e.length - 2 * margin; if (usable <= 0) continue;
      const count = options.count ?? Math.max(1, Math.round(usable / (options.spacing ?? 4)));
      for (let k = 0; k < count; k++) frames.push(this._edgeFrame(e, (margin + usable * (k + 0.5) / count) / e.length, options.inset ?? 0));
    }
    return frames;
  }
  at(x, z, yaw = 0) { return { x, z, yaw }; }
  // -- core masses
  _add(object, type, frame) {
    if (object.isGroup && type !== 'custom' && !object.userData.dynamic) {
      // Static pieces of one part that share a material render in one draw.
      // The part's pivot is kept for semantic selection and state control.
      const batches = new Map();
      for (const child of [...object.children]) if (child.isMesh && !child.isInstancedMesh && !child.isSkinnedMesh && !Array.isArray(child.material) && !child.userData.dynamic) {
        child.updateMatrix();
        const geometry = (child.geometry.index ? child.geometry.toNonIndexed() : child.geometry.clone()).applyMatrix4(child.matrix);
        if (!batches.has(child.material)) batches.set(child.material, []);
        batches.get(child.material).push(geometry);
        object.remove(child); child.geometry.dispose();
      }
      for (const [material, geometries] of batches) {
        // Pieces with different attribute sets cannot merge; they stay separate.
        const merged = geometries.length > 1 ? mergeGeometries(geometries, false) : null;
        if (merged) { object.add(new THREE.Mesh(merged, material)); geometries.forEach(g => g.dispose()); }
        else for (const geometry of geometries) object.add(new THREE.Mesh(geometry, material));
      }
    }
    const pivot = new THREE.Group(); this.counts[type] = (this.counts[type] ?? 0) + 1; const id = type + '-' + this.counts[type];
    pivot.name = id + ':pivot'; if (frame) { pivot.position.set(frame.x, 0, frame.z); pivot.rotation.y = frame.yaw ?? 0; }
    object.name = object.name || id; pivot.add(object); this.root.add(pivot);
    object.traverse(o => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; if (!o.name) o.name = id; } });
    this.parts.push({ instance: this.root.name, component: { id, kind: type, semantic_requirements: [] }, node: object, pivot });
    return { id, object, pivot };
  }
  _loft(rings, material, facade, holes=[]) {
    const positions = [], uvs = [];
    const quad = (a, b, c, d, ua, ub, va, vb) => { for (const p of [a, b, c, a, c, d]) positions.push(...p); uvs.push(ua, va, ub, va, ub, vb, ua, va, ub, vb, ua, vb); };
    for (let k = 0; k + 1 < rings.length; k++) {
      const low = rings[k], high = rings[k + 1], n = low.plan.length; if (high.plan.length !== n) throw Error('KIT_LOFT_RING_MISMATCH');
      for (let i = 0; i < n; i++) {
        const j = (i + 1) % n, a = low.plan[i], b = low.plan[j], length = Math.hypot(b[0] - a[0], b[1] - a[1]);
        const ub = facade ? Math.max(1, Math.round(length / facade.bay)) : length, va = facade ? (low.y - rings[0].y) / facade.storey : low.y;
        const vb = facade ? (high.y - rings[0].y) / facade.storey : va + Math.hypot(high.y-low.y, high.plan[i][0]-a[0], high.plan[i][1]-a[1]);
        quad([a[0], low.y, -a[1]], [b[0], low.y, -b[1]], [high.plan[j][0], high.y, -high.plan[j][1]], [high.plan[i][0], high.y, -high.plan[i][1]], 0, ub, va, vb);
      }
    }
    for(const hole of holes)for(let k=0;k+1<rings.length;k++)for(let i=0;i<hole.length;i++){
      const a=hole[i],b=hole[(i+1)%hole.length],length=Math.hypot(b[0]-a[0],b[1]-a[1]),low=rings[k],high=rings[k+1];
      quad([a[0],low.y,-a[1]],[b[0],low.y,-b[1]],[b[0],high.y,-b[1]],[a[0],high.y,-a[1]],0,facade?Math.max(1,Math.round(length/facade.bay)):length,facade?(low.y-rings[0].y)/facade.storey:low.y,facade?(high.y-rings[0].y)/facade.storey:high.y);
    }
    const top = rings[rings.length - 1], contour = top.plan.map(p => new THREE.Vector2(p[0], p[1])),vertices=[...top.plan,...holes.flat()];
    for (const f of THREE.ShapeUtils.triangulateShape(contour, holes.map(h=>h.map(p=>new THREE.Vector2(...p))))) for (const i of f) { positions.push(vertices[i][0], top.y, -vertices[i][1]); uvs.push(vertices[i][0], vertices[i][1]); }
    const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3)); g.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2)); g.computeVertexNormals();
    return new THREE.Mesh(g, material);
  }
  walls(o = {}) {
    if (this.counts.walls) throw Error('KIT_EXACTLY_ONE_WALL_ASSEMBLY');
    const height = o.height ?? this.site.eave_m, y = o.y ?? 0, storeys = o.storeys ?? this.site.storeys ?? 3, facade = { bay: o.bay ?? 3.2, storey: height / storeys, window: o.window, course: o.course };
    if (Math.abs(height / this.site.eave_m - 1) > .15 || y !== 0) throw Error('KIT_WALL_HEIGHT_OUTSIDE_MEASURED_TOLERANCE');
    const m = o.windows === false ? this._material(o.material) : this._facadeMaterial(o.material, facade);
    this.wallTop = Math.max(this.wallTop ?? 0, y + height);
    const part = this._add(this._loft([{ y, plan: this.plan }, { y: y + height, plan: this.plan }], m, o.windows === false ? null : facade,this.holes), 'walls');
    this.wallGuard = {part, positions: Array.from(part.object.geometry.attributes.position.array)};
    return part;
  }
  band(o = {}) {
    const plan = offset(this.plan, -(o.out ?? 0.25)); if (!plan) throw Error('KIT_BAND_OFFSET_FAILED');
    const y = o.y ?? this.site.eave_m - (o.height ?? 0.4);
    return this._add(this._loft([{ y, plan }, { y: y + (o.height ?? 0.4), plan }], this._material(o.material),null,this.holes), 'band');
  }
  roof(o = {}) {
    const form = o.form ?? this.site.roof?.form ?? 'hip', eave = o.y ?? this.wallTop ?? this.site.eave_m, rise = o.rise ?? Math.max(0.3, (this.site.ridge_m ?? eave) - eave);
    const base = offset(this.plan, -(o.overhang ?? 0.3)) ?? this.plan, ends = this.site.edges.map(e => e.end);
    let rings = [{ y: eave, plan: base }], insets = [0], weights = this.plan.map(() => 1);
    if (form === 'flat') { rings.push({ y: eave + (o.parapet ?? 0.4), plan: base }); insets.push(0); }
    else {
      if (form === 'gable' && ends.some(v => !v)) weights = ends.map(v => v ? 0 : 1);
      const limit = insetLimit(this.plan, weights) * 0.97;
      if (form === 'mansard') { const lower = rise * (o.lowerFraction ?? 0.6), inset = Math.min(lower * (o.lowerRun ?? 0.35), limit * 0.6); rings.push({ y: eave + lower, plan: offset(this.plan, weights.map(w => inset * w)) }); insets.push(inset); }
      else if (!['hip', 'gable'].includes(form)) throw Error('KIT_UNKNOWN_ROOF_FORM:' + form);
      rings.push({ y: eave + rise, plan: offset(this.plan, weights.map(w => limit * w)) }); insets.push(limit);
    }
    this.roofProfile = { eave, weights, ys: rings.map(r => r.y), insets, top: rings[rings.length - 1].y };
    if(this.holes.length&&form!=='flat')throw Error('KIT_COURTYARD_PITCHED_ROOF_UNSUPPORTED');
    const part=this._add(this._loft(rings, this._material(o.material),null,this.holes), 'roof');this.roofMesh=part.object;
    return { ...part, ridgeY: this.roofProfile.top, eaveY: eave };
  }
  // Height of the roof surface (or wall top outside any roof) at a plan position.
  roofY(x, z) {
    let tier = -Infinity; for (const t of this.tiers ?? []) if (inside(t.plan, x, -z)) tier = Math.max(tier, t.top);
    if (tier > -Infinity) return tier;
    if (this.roofSurfaces) {
      let best = -Infinity;
      for (const s of this.roofSurfaces) {
        const dx = x - s.cx, dz = z - s.cz, u = dx * s.c - dz * s.n, v = dx * s.n + dz * s.c;
        if (Math.abs(u) > s.half || Math.abs(v) > s.halfWidth) continue;
        let k = 1; if (s.hs) k = Math.min(k, Math.max(0, (u + s.half) / s.hs)); if (s.he) k = Math.min(k, Math.max(0, (s.half - u) / s.he));
        let y = v < s.prof[0][0] ? s.prof[0][1] : s.prof[s.prof.length - 1][1];
        for (let j = 0; j + 1 < s.prof.length; j++) if (v >= s.prof[j][0] && v <= s.prof[j + 1][0]) y = s.prof[j][1] + (s.prof[j + 1][1] - s.prof[j][1]) * (v - s.prof[j][0]) / ((s.prof[j + 1][0] - s.prof[j][0]) || 1);
        best = Math.max(best, s.b0 + (y - s.b0) * k);
      }
      return best > -Infinity ? best : this.wallTop ?? this.site.eave_m;
    }
    const p = this.roofProfile; if (!p) return this.wallTop ?? this.site.eave_m;
    if (!inside(this.plan, x, -z)) return p.eave;
    let d = Infinity; this.edges.forEach((e, i) => { if (p.weights[i] > 0) d = Math.min(d, segmentDistance(e.a, e.b, x, -z)); });
    for (let k = 0; k + 1 < p.insets.length; k++) if (p.insets[k + 1] > p.insets[k] && d <= p.insets[k + 1]) return p.ys[k] + (p.ys[k + 1] - p.ys[k]) * (d - p.insets[k]) / (p.insets[k + 1] - p.insets[k]);
    return p.top;
  }
  _world(frame, lx, lz) { const c = Math.cos(frame.yaw ?? 0), s = Math.sin(frame.yaw ?? 0); return [frame.x + lx * c + lz * s, frame.z - lx * s + lz * c]; }
  // -- primitives in a frame's local space (x along, y up, z out)
  _box(w, h, d, x, y, z, material) { const m = new THREE.Mesh(metricUVs(new THREE.BoxGeometry(w, h, d)), this._material(material)); m.position.set(x, y + h / 2, z); return m; }
  _prism(profile, depth, material) { const s = new THREE.Shape(); profile.forEach(([x, y], i) => i ? s.lineTo(x, y) : s.moveTo(x, y)); s.closePath(); const g = new THREE.ExtrudeGeometry(s, { depth, bevelEnabled: false }); return new THREE.Mesh(g, this._material(material)); }
  box(frame, o) { return this._add(this._box(o.w, o.h, o.d, o.dx ?? 0, o.y ?? 0, o.dz ?? 0, o.material), 'box', frame); }
  cylinder(frame, o) { const m = new THREE.Mesh(new THREE.CylinderGeometry(o.rTop ?? o.r, o.r, o.h, o.sides ?? 16), this._material(o.material)); m.position.set(o.dx ?? 0, (o.y ?? 0) + o.h / 2, o.dz ?? 0); return this._add(m, 'cylinder', frame); }
  cone(frame, o) { const m = new THREE.Mesh(new THREE.ConeGeometry(o.r, o.h, o.sides ?? 16), this._material(o.material)); m.position.set(o.dx ?? 0, (o.y ?? 0) + o.h / 2, o.dz ?? 0); if ((o.sides ?? 16) === 4) m.rotation.y = Math.PI / 4; return this._add(m, 'cone', frame); }
  // profile: [[x, y], ...] in the frame's vertical plane, extruded `depth` metres inward from `dz`.
  prism(frame, o) { const m = this._prism(o.profile, o.depth, o.material); m.position.set(o.dx ?? 0, o.y ?? 0, (o.dz ?? 0) - o.depth); return this._add(m, 'prism', frame); }
  loft(rings, material) { return this._add(this._loft(rings.map(r => ({ y: r.y, plan: toPlan(r.points) })), this._material(material)), 'loft'); }
  add(object, frame) { return this._add(object, 'custom', frame); }
  // -- architectural parts
  dormer(frame, o = {}) {
    const w = o.width ?? 1.6, h = o.height ?? 1.9, d = o.depth ?? 2.4, g = new THREE.Group(), [fx, fz] = this._world(frame, 0, -(o.setback ?? 0.6)), y = this.roofY(fx, fz) - 0.15;
    const z0 = -(o.setback ?? 0.6), body = h * (o.roof === 'flat' ? 1 : 0.62);
    if(this.roofMesh&&o.cutRoof!==false)cutRoofOpening(this.roofMesh,frame,w*.94,z0-.03,z0-d+.03);
    // Side cheeks follow the host roof instead of forming a box perched above it.
    const [bx, bz] = this._world(frame, 0, z0 - d), backY = Math.min(y + body - .12, this.roofY(bx, bz) - .15);
    const cheek = new THREE.BufferGeometry(), vertices = [];
    for (const x of [-w / 2, w / 2]) {
      const points = [[x,y,z0],[x,backY,z0-d],[x,y+body,z0-d],[x,y+body,z0]];
      for (const i of x < 0 ? [0,2,1,0,3,2] : [0,1,2,0,2,3]) vertices.push(...points[i]);
    }
    cheek.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3)); cheek.computeVertexNormals(); metricUVs(cheek);
    g.add(new THREE.Mesh(cheek, this._material(o.material ?? o.wall)));
    g.add(this._box(w, body, .18, 0, y, z0 - .09, o.material ?? o.wall));
    if (o.roof !== 'flat') { const r = this._prism(o.roof === 'shed' ? [[-w / 2 - .12, 0], [w / 2 + .12, 0], [w / 2 + .12, h - body], [-w / 2 - .12, (h - body) * .3]] : [[-w / 2 - .15, 0], [w / 2 + .15, 0], [0, h - body]], d + 0.15, o.roofMaterial ?? o.material); r.position.set(0, y + body, z0 - d); g.add(r); }
    if (o.window !== false && o.glass) {
      g.add(this._box(w * .7, body * .74, .09, 0, y + body * .12, z0 + .035, o.trimMaterial ?? o.material));
      g.add(this._box(w * .56, body * .61, .06, 0, y + body * .19, z0 + .095, o.glass));
    }
    return this._add(g, 'dormer', frame);
  }
  chimney(frame, o = {}) {
    const w = o.width ?? 0.9, d = o.depth ?? 0.6, top = this.roofY(frame.x, frame.z) + (o.height ?? 1.6), y = this.roofY(frame.x, frame.z) - 0.6, g = new THREE.Group();
    const ring = (width, depth, thickness, bottom, height, material) => {
      const shape = new THREE.Shape(); shape.moveTo(-width/2,-depth/2); shape.lineTo(width/2,-depth/2); shape.lineTo(width/2,depth/2); shape.lineTo(-width/2,depth/2); shape.closePath();
      const hole = new THREE.Path(); hole.moveTo(-width/2+thickness,-depth/2+thickness); hole.lineTo(-width/2+thickness,depth/2-thickness); hole.lineTo(width/2-thickness,depth/2-thickness); hole.lineTo(width/2-thickness,-depth/2+thickness); hole.closePath(); shape.holes.push(hole);
      const geometry = new THREE.ExtrudeGeometry(shape, {depth:height,bevelEnabled:false}); geometry.rotateX(-Math.PI/2); metricUVs(geometry);
      const mesh = new THREE.Mesh(geometry,this._material(material)); mesh.position.y = bottom; g.add(mesh);
    };
    const thickness = Math.min(w,d) * .19;
    ring(w,d,thickness,y,top-y,o.material);
    if (o.cap !== false) ring(w+.16,d+.16,thickness+.08,top,.14,o.capMaterial ?? o.material);
    // Open cylinders plus an annular rim preserve a real flue, not a painted dot.
    for (let i = 0; i < (o.pots ?? 0); i++) {
      const pot = new THREE.Mesh(new THREE.CylinderGeometry(.09,.12,.35,12,1,true),this._material(o.potMaterial ?? o.material));
      pot.material = pot.material.clone(); pot.material.side = THREE.DoubleSide;
      pot.position.set((i-(o.pots-1)/2)*w/o.pots,top+.315,0);g.add(pot);
      const lip = new THREE.Mesh(new THREE.TorusGeometry(.082,.018,6,12),this._material(o.capMaterial ?? o.material));lip.rotation.x=Math.PI/2;lip.position.copy(pot.position);lip.position.y=top+.49;g.add(lip);
    }
    return this._add(g, 'chimney', frame);
  }
  // A wall-plane gable: the facade continues above the eave to a peak, with its own roof running inward.
  gable(frame, o = {}) {
    const w = o.width ?? 4, h = o.height ?? 3, d = o.depth ?? 3, y = o.y ?? this.wallTop ?? this.site.eave_m, g = new THREE.Group(), stem = o.stem ?? 0;
    if(this.roofMesh&&o.cutRoof!==false)cutRoofOpening(this.roofMesh,frame,w*.95,-.27,-d-.20);
    const front = this._prism([[-w / 2, 0], [w / 2, 0], [w / 2, stem], [0, stem + h], [-w / 2, stem]], 0.3, o.material); front.position.set(0, y, (o.out ?? 0.05) - 0.3); g.add(front);
    // A cross roof: the ridge runs level and inward until the host roof rises to meet it.
    // It is a closed solid, so a gable taller than the host ridge reads as a cross wing,
    // never as a free-standing sheet.
    const hostY = (x,z) => { const [wx,wz]=this._world(frame,x,z); return this.roofY(wx,wz); };
    const peak=y+stem+h+.15, limit=o.maxDepth ?? Math.max(d, w*2.2); let run=Math.min(d, limit);
    while(run<limit && hostY(0,-run)<peak-.05) run+=.3;
    const cross=this._prism([[-w/2-.2,0],[w/2+.2,0],[0,h+.15]],run,o.roofMaterial ?? o.material);cross.position.set(0,y+stem,-run-.25);metricUVs(cross.geometry);g.add(cross);
    if (stem > 0) g.add(this._box(w, stem, run, 0, y, -run / 2 - 0.25, o.material));
    if (o.glass) g.add(this._box(w * 0.22, (stem + h) * 0.3, 0.06, 0, y + (stem + h) * 0.22, (o.out ?? 0.05) + 0.02, o.glass));
    if (o.trimMaterial) {
      const line = (a,b,width) => { const delta=new THREE.Vector3().subVectors(b,a); const beam=new THREE.Mesh(new THREE.BoxGeometry(width,delta.length(),.18),this._material(o.trimMaterial));beam.position.copy(a).add(b).multiplyScalar(.5);beam.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),delta.normalize());g.add(beam); };
      const z=(o.out ?? .05)+.1;
      line(new THREE.Vector3(-w/2,y+stem,z),new THREE.Vector3(0,y+stem+h,z),o.trimWidth ?? .18);
      line(new THREE.Vector3(0,y+stem+h,z),new THREE.Vector3(w/2,y+stem,z),o.trimWidth ?? .18);
      g.add(this._box(w+.35,.18,.35,0,y-.1,z-.05,o.trimMaterial));
    }
    return this._add(g, 'gable', frame);
  }
  window(frame, o = {}) {
    const w=o.width ?? 1.4,h=o.height ?? 2.3,y=o.y ?? 1,trim=o.trimMaterial,glass=o.glass,g=new THREE.Group(),t=o.trimWidth ?? .13,z=o.out ?? .06;
    g.add(this._box(w,h,.055,0,y,z+.025,glass));
    for (const x of [-w/2-t/2,w/2+t/2]) g.add(this._box(t,h+2*t,.15,x,y-t,z+.11,trim));
    for (const py of [y-t,y+h]) g.add(this._box(w+2*t,t,.16,0,py,z+.12,trim));
    g.add(this._box(w+4*t,.16,.38,0,y-.2,z+.18,trim));
    const [cols,rows]=o.mullions ?? [2,2];
    for(let i=1;i<cols;i++)g.add(this._box(.045,h,.08,-w/2+w*i/cols,y,z+.13,trim));
    for(let i=1;i<rows;i++)g.add(this._box(w,.045,.08,0,y+h*i/rows,z+.13,trim));
    if(o.pediment){const crown=this._prism([[-w*.65,0],[w*.65,0],[0,o.pediment==='triangular'?.5:.22]],.22,trim);crown.position.set(0,y+h+.19,z);g.add(crown);}
    if(o.keystone)g.add(this._box(.2,.3,.24,0,y+h+.1,z+.12,trim));
    return this._add(g,'window',frame);
  }
  turret(frame, o = {}) {
    const r = o.radius ?? 1.6, sides = o.sides ?? 8, y = o.y ?? 0, wall = (o.wallTop ?? (this.wallTop ?? this.site.eave_m) + 1.5) - y, g = new THREE.Group();
    const shaft = new THREE.Mesh(new THREE.CylinderGeometry(r, r, wall, sides), this._material(o.material)); shaft.position.y = y + wall / 2; if (sides === 4) shaft.rotation.y = Math.PI / 4; g.add(shaft);
    const dome=o.roof==='dome',capHeight=o.roofHeight??r*(dome?1.05:2.2);
    if(!Number.isFinite(capHeight)||capHeight<=0)throw Error('KIT_INVALID_TURRET_ROOF_HEIGHT');
    const cap = dome ? new THREE.Mesh(new THREE.SphereGeometry(r * 1.05, Math.max(sides, 12), 8, 0, Math.PI * 2, 0, Math.PI / 2), this._material(o.roofMaterial ?? o.material)) : new THREE.Mesh(new THREE.ConeGeometry(r * 1.12, capHeight, sides), this._material(o.roofMaterial ?? o.material));
    if(dome)cap.scale.y=capHeight/(r*1.05);
    cap.position.y = y + wall + (dome ? 0 : capHeight / 2); if (sides === 4) cap.rotation.y = Math.PI / 4; g.add(cap);
    if (o.finial) { const f = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.06, o.finial, 6), this._material(o.finialMaterial ?? o.roofMaterial ?? o.material)); f.position.y = y + wall + capHeight + o.finial / 2; g.add(f); }
    return this._add(g, 'turret', frame);
  }
  // A mass projecting out of the facade (oriel, porch block, stair tower).
  bay(frame, o = {}) {
    const w = o.width ?? 3, d = o.depth ?? 1.2, h = o.height ?? this.site.eave_m, y = o.y ?? 0, g = new THREE.Group();
    g.add(this._box(w, h, d, 0, y, d / 2, o.material));
    if (o.glass) for (let s = 0; s < (o.storeys ?? 1); s++) g.add(this._box(w * 0.6, h / (o.storeys ?? 1) * 0.5, 0.06, 0, y + h / (o.storeys ?? 1) * (s + 0.28), d + 0.02, o.glass));
    if (o.roofMaterial) { const r = this._prism([[-w / 2 - .15, 0], [w / 2 + .15, 0], [0, o.roofHeight ?? w * 0.35]], d + 0.2, o.roofMaterial); r.position.set(0, y + h, 0); g.add(r); }
    return this._add(g, 'bay', frame);
  }
  portal(frame, o = {}) {
    const w = o.width ?? 2.4, h = o.height ?? 3.6, d = o.depth ?? 0.5, g = new THREE.Group();
    g.add(this._box(w + 0.8, h + 0.5, d, 0, 0, d / 2, o.material)); g.add(this._box(w, h, 0.08, 0, 0, d + 0.02, o.door ?? o.material));
    if (o.arch !== false) { const R = w / 2 + 0.4, a = this._prism(Array.from({ length: 13 }, (_, i) => [R * Math.cos(Math.PI * i / 12), R * Math.sin(Math.PI * i / 12)]), d, o.material); a.position.set(0, h + 0.5, 0); g.add(a); }
    for (let i = 0; i < (o.steps ?? 0); i++) g.add(this._box(w + 1.4 + i * 0.5, 0.16, 0.32, 0, 0.16 * ((o.steps ?? 0) - 1 - i), d + 0.16 + i * 0.32, o.stepMaterial ?? o.material));
    return this._add(g, 'portal', frame);
  }
  pilasters(which, o = {}) { return this.along(which, o).map(f => this.box(f, { w: o.width ?? 0.5, h: o.height ?? this.site.eave_m, d: o.out ?? 0.18, dz: (o.out ?? 0.18) / 2, y: o.y ?? 0, material: o.material })); }
  // Vertical strips at every outline corner.
  quoins(o = {}) { return this.plan.map(([x, n]) => this.box(this.at(x, -n, o.yaw ?? this.site.axis_yaw ?? 0), { w: o.size ?? 0.7, h: o.height ?? this.site.eave_m, d: o.size ?? 0.7, material: o.material })); }
  ground(o = {}) { const plan = offset(this.plan, -(o.margin ?? 3)) ?? this.plan; return this._add(this._loft([{ y: -(o.thickness ?? 0.15), plan }, { y: 0.02, plan }], this._material(o.material)), 'ground'); }
  _ids(which) { return which === 'all' ? this.edges.map(e => e.id) : which === 'long' ? this.site.edges.filter(e => !e.end).map(e => e.id) : which === 'ends' ? this.site.edges.filter(e => e.end).map(e => e.id) : [].concat(which); }
  _mesh(positions, material) { const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3)); g.computeVertexNormals(); metricUVs(g); return new THREE.Mesh(g, material); }

  // ---- measured roofs and roof-level masses ------------------------------------------
  // Each wing's measured cross-section swept along the wing, with gable or hipped ends.
  roofSections(o = {}) {
    const sections = o.sections ?? this.site.roof?.sections;
    if (!sections?.length) throw Error('KIT_NO_MEASURED_ROOF_SECTIONS: use b.roof(...)');
    const over = o.overhang ?? 0.3, lift = o.lift ?? 0, scale = o.riseScale ?? 1, roofPositions = [], endPositions = []; let ridgeY = -Infinity;
    if (scale < 0.7 || scale > 1.4) throw Error('KIT_ROOF_RISE_SCALE_OUTSIDE_0.7_1.4');
    this.roofSurfaces = [];
    for (const s of sections) {
      const c = Math.cos(s.rotation_y_rad), n = Math.sin(s.rotation_y_rad), [cx, cz] = s.centre_xz, half = s.length_m / 2;
      const base = Math.min(...s.profile.map(p => p[1])), b0 = base + lift, hs = s.hip_start_m ?? 0, he = s.hip_end_m ?? 0;
      const prof = s.profile.map(([v, y]) => [v, b0 + (y - base) * scale]); prof[0] = [prof[0][0] - over, prof[0][1]]; prof[prof.length - 1] = [prof[prof.length - 1][0] + over, prof[prof.length - 1][1]];
      ridgeY = Math.max(ridgeY, ...prof.map(p => p[1]));
      const world = (u, v, y) => [cx + u * c + v * n, y, cz - u * n + v * c];
      const stations = [[-half - (hs ? over : 0), hs ? 0 : 1], ...(hs ? [[-half + hs, 1]] : []), ...(he ? [[half - he, 1]] : []), [half + (he ? over : 0), he ? 0 : 1]];
      const P = (st, j) => world(st[0], prof[j][0], b0 + (prof[j][1] - b0) * st[1]);
      for (let i = 0; i + 1 < stations.length; i++) for (let j = 0; j + 1 < prof.length; j++) {
        const a = P(stations[i], j), b = P(stations[i + 1], j), d = P(stations[i + 1], j + 1), e = P(stations[i], j + 1);
        roofPositions.push(...a, ...e, ...d, ...a, ...d, ...b);
      }
      // A gable end is a wall up to the roof line, not an open section.
      for (const [st, flip] of [[stations[0], false], [stations[stations.length - 1], true]]) if (st[1] === 1) for (let j = 0; j + 1 < prof.length; j++) {
        const a = world(st[0], prof[j][0], b0 - .05), b = world(st[0], prof[j + 1][0], b0 - .05), t1 = world(st[0], prof[j + 1][0], prof[j + 1][1]), t0 = world(st[0], prof[j][0], prof[j][1]);
        endPositions.push(...(flip ? [...a, ...b, ...t1, ...a, ...t1, ...t0] : [...a, ...t1, ...b, ...a, ...t0, ...t1]));
      }
      this.roofSurfaces.push({ c, n, cx, cz, half: half + over, halfWidth: s.width_m / 2 + over, hs, he, prof, b0 });
    }
    const material = this._material(o.material).clone(); material.side = THREE.DoubleSide;
    const g = new THREE.Group(), roof = this._mesh(roofPositions, material); g.add(roof);
    if (endPositions.length) { const end = this._material(o.endMaterial ?? o.material).clone(); end.side = THREE.DoubleSide; g.add(this._mesh(endPositions, end)); }
    this.roofProfile = null; this.roofMesh = roof;
    // 'custom' keeps the mesh objects intact: local roof openings are cut into `roof` later.
    const part = this._add(g, 'custom'); this.parts[this.parts.length - 1].component.kind = 'roof';
    return { ...part, ridgeY, eaveY: Math.min(...this.roofSurfaces.map(s => s.b0)) };
  }
  // A mass standing on or through the roof: pavilion, tower, cross wing, penthouse, plant room.
  volume(frame, o = {}) {
    const w = o.width ?? 4, d = o.depth ?? 4, y = o.y ?? (this.wallTop ?? this.site.eave_m) - .3, shoulder = o.shoulder ?? y + 3, top = Math.max(shoulder, o.top ?? shoulder), cap = o.cap ?? 'flat';
    const g = new THREE.Group(), rm = o.roofMaterial ?? o.material, rise = top - shoulder, ov = o.overhang ?? .2;
    g.add(this._box(w, shoulder - y, d, 0, y, 0, o.material));
    if (cap === 'flat' || rise < .05) { if (o.parapet !== false) g.add(this._box(w + .16, o.parapet ?? .25, d + .16, 0, shoulder, 0, rm)); }
    else if (cap === 'pyramid' || cap === 'hip') {
      const ridge = cap === 'hip' ? Math.abs(w - d) / 2 : 0, rx = w >= d ? ridge : 0, rz = w >= d ? 0 : ridge, hw = w / 2 + ov, hd = d / 2 + ov;
      const low = [[-hw, shoulder, hd], [hw, shoulder, hd], [hw, shoulder, -hd], [-hw, shoulder, -hd]], high = [[-rx, top, rz], [rx, top, rz], [rx, top, -rz], [-rx, top, -rz]], positions = [];
      for (let i = 0; i < 4; i++) { const j = (i + 1) % 4; positions.push(...low[i], ...low[j], ...high[j], ...low[i], ...high[j], ...high[i]); }
      const m = this._material(rm).clone(); m.side = THREE.DoubleSide; g.add(this._mesh(positions, m));
    } else if (cap === 'gable') {
      // Ridge along the longer side.
      if (w >= d) { const r = this._prism([[-d / 2 - ov, 0], [d / 2 + ov, 0], [0, rise]], w + 2 * ov, rm); r.rotation.y = Math.PI / 2; r.position.set(-w / 2 - ov, shoulder, 0); g.add(r); }
      else { const r = this._prism([[-w / 2 - ov, 0], [w / 2 + ov, 0], [0, rise]], d + 2 * ov, rm); r.position.set(0, shoulder, -d / 2 - ov); g.add(r); }
    } else if (cap === 'cone') { const r = new THREE.Mesh(new THREE.ConeGeometry(Math.max(w, d) / 2 + ov, rise, o.sides ?? 16), this._material(rm)); r.position.y = shoulder + rise / 2; if ((o.sides ?? 16) === 4) r.rotation.y = Math.PI / 4; g.add(r); }
    else if (cap === 'dome') { const r = new THREE.Mesh(new THREE.SphereGeometry(.5, 20, 10, 0, Math.PI * 2, 0, Math.PI / 2), this._material(rm)); r.scale.set(w + ov, rise * 2, d + ov); r.position.y = shoulder; g.add(r); }
    else throw Error('KIT_UNKNOWN_VOLUME_CAP:' + cap);
    if (o.glass) { const gh = (shoulder - y) * (o.glassHeight ?? .45), gy = shoulder - gh - (shoulder - y) * .18; for (const [gx, gz, gw, gd] of [[0, d / 2 + .02, w * .5, .06], [0, -d / 2 - .02, w * .5, .06], [w / 2 + .02, 0, .06, d * .5], [-w / 2 - .02, 0, .06, d * .5]]) g.add(this._box(gw, gh, gd, gx, gy, gz, o.glass)); }
    if (o.finial) { const f = new THREE.Mesh(new THREE.CylinderGeometry(.04, .07, o.finial, 6), this._material(o.finialMaterial ?? rm)); f.position.y = top + o.finial / 2; g.add(f); }
    return this._add(g, 'volume', frame);
  }
  // Upper storeys stepped back from the outline: tower on a podium, attic storey, crown.
  tier(o = {}) {
    const plan = offset(this.plan, o.inset ?? 2); if (!plan) throw Error('KIT_TIER_INSET_TOO_LARGE');
    const y = o.y ?? this.wallTop ?? this.site.eave_m, h = o.height ?? 3.5, storeys = o.storeys ?? Math.max(1, Math.round(h / 3.5));
    const facade = { bay: o.bay ?? 3.2, storey: h / storeys, window: o.window, course: o.course };
    const m = o.windows === false ? this._material(o.material) : this._facadeMaterial(o.material, facade);
    (this.tiers ??= []).push({ plan, top: y + h });
    return { ...this._add(this._loft([{ y, plan }, { y: y + h, plan }], m, o.windows === false ? null : facade), 'tier'), topY: y + h };
  }
  // Upstand around the outline (or `inset` metres inside it) at roof level.
  parapet(o = {}) {
    const outer = o.inset ? offset(this.plan, o.inset) : this.plan, inner = outer && offset(outer, o.thickness ?? .3); if (!inner) throw Error('KIT_PARAPET_DOES_NOT_FIT');
    const shape = new THREE.Shape(outer.map(p => new THREE.Vector2(p[0], p[1]))); shape.holes.push(new THREE.Path(inner.map(p => new THREE.Vector2(p[0], p[1]))));
    const geometry = new THREE.ExtrudeGeometry(shape, { depth: o.height ?? .9, bevelEnabled: false }); geometry.rotateX(-Math.PI / 2); metricUVs(geometry);
    const mesh = new THREE.Mesh(geometry, this._material(o.material)); mesh.position.y = o.y ?? this.roofY(inner[0][0], -inner[0][1]);
    return this._add(mesh, 'parapet');
  }
  // Stacked bands stepping outward: a moulded cornice rather than a single strip.
  cornice(o = {}) {
    const steps = o.steps ?? 3, height = o.height ?? .9, out = o.out ?? .5, top = o.y ?? this.wallTop ?? this.site.eave_m, g = new THREE.Group();
    for (let i = 0; i < steps; i++) { const plan = offset(this.plan, -out * (i + 1) / steps); if (!plan) throw Error('KIT_CORNICE_OFFSET_FAILED'); const y = top - height + height * i / steps; g.add(this._loft([{ y, plan }, { y: y + height / steps, plan }], this._material(o.material),null,this.holes)); }
    return this._add(g, 'cornice');
  }

  // ---- facade systems along edges ----------------------------------------------------
  // Glazed curtain wall: glass plane, mullion grid, optional opaque spandrel per floor.
  curtainWall(which, o = {}) {
    const y0 = o.y ?? 0, y1 = o.top ?? this.wallTop ?? this.site.eave_m, h = y1 - y0, floor = o.floor ?? this.site.eave_m / (this.site.storeys ?? 3), out = o.out ?? .12, md = o.mullionDepth ?? .14, parts = [];
    for (const id of this._ids(which)) {
      const e = this.edge(id), L = e.length - 2 * (o.margin ?? .4); if (L <= .5) continue;
      const g = new THREE.Group(), n = Math.max(1, Math.round(L / (o.module ?? 1.5))), rows = Math.max(1, Math.round(h / floor)), th = o.transomHeight ?? .08;
      g.add(this._box(L, h, .05, 0, y0, out, o.glass));
      for (let i = 0; i <= n; i++) g.add(this._box(o.mullionWidth ?? .07, h, md, -L / 2 + L * i / n, y0, out + md / 2, o.frame));
      for (let r = 0; r <= rows; r++) { const y = y0 + h * r / rows; g.add(this._box(L, th, .1, 0, Math.min(y, y1 - th), out + .05, o.frame)); if (o.spandrel && r < rows) g.add(this._box(L, o.spandrelHeight ?? .9, .06, 0, y, out + .012, o.spandrel)); }
      parts.push(this._add(g, 'curtainWall', e.at(.5)));
    }
    return parts;
  }
  // Continuous horizontal window bands, one per storey.
  ribbonWindows(which, o = {}) {
    const storeys = o.storeys ?? this.site.storeys ?? 3, floor = (o.top ?? this.wallTop ?? this.site.eave_m) / storeys, sill = o.sill ?? .95, out = o.out ?? .04, parts = [];
    for (const id of this._ids(which)) {
      const e = this.edge(id), L = e.length - 2 * (o.margin ?? .8); if (L <= 1) continue;
      const g = new THREE.Group(), n = Math.max(1, Math.round(L / (o.module ?? 1.8)));
      for (let s = o.fromStorey ?? 0; s < (o.toStorey ?? storeys); s++) {
        const y = s * floor + sill, bh = Math.min(o.height ?? 1.7, floor - sill - .25);
        g.add(this._box(L, bh, .05, 0, y, out, o.glass));
        for (let i = 0; i <= n; i++) g.add(this._box(.06, bh, .09, -L / 2 + L * i / n, y, out + .03, o.frame));
        for (const fy of [y - .08, y + bh]) g.add(this._box(L + .1, .08, .14, 0, fy, out + .04, o.frame));
      }
      parts.push(this._add(g, 'ribbonWindows', e.at(.5)));
    }
    return parts;
  }
  // Repeated blades standing off the facade: vertical fins, or horizontal louvres/sunshades.
  fins(which, o = {}) {
    const y0 = o.y ?? 0, y1 = o.top ?? this.wallTop ?? this.site.eave_m, depth = o.depth ?? .45, t = o.thickness ?? .08, spacing = o.spacing ?? 1.2, parts = [];
    for (const id of this._ids(which)) {
      const e = this.edge(id), L = e.length - 2 * (o.margin ?? .3); if (L <= .5) continue; const g = new THREE.Group();
      if (o.horizontal) { const n = Math.max(1, Math.round((y1 - y0) / spacing)); for (let i = 0; i < n; i++) g.add(this._box(L, t, depth, 0, y0 + (y1 - y0) * (i + .5) / n, depth / 2 + (o.out ?? 0), o.material)); }
      else { const n = Math.max(1, Math.round(L / spacing)); for (let i = 0; i <= n; i++) g.add(this._box(t, y1 - y0, depth, -L / 2 + L * i / n, y0, depth / 2 + (o.out ?? 0), o.material)); }
      parts.push(this._add(g, 'fins', e.at(.5)));
    }
    return parts;
  }
  // Expressed structural frame: columns at bay lines and a beam at every floor.
  frameGrid(which, o = {}) {
    const storeys = o.storeys ?? this.site.storeys ?? 3, top = o.top ?? this.wallTop ?? this.site.eave_m, floor = top / storeys, out = o.out ?? .2, parts = [];
    for (const id of this._ids(which)) {
      const e = this.edge(id), L = e.length; const g = new THREE.Group(), n = Math.max(1, Math.round(L / (o.bay ?? 6)));
      for (let i = 0; i <= n; i++) g.add(this._box(o.columnWidth ?? .5, top, out, -L / 2 + L * i / n, 0, out / 2, o.material));
      for (let s = 1; s <= storeys; s++) g.add(this._box(L, o.beamHeight ?? .45, out, 0, s * floor - (o.beamHeight ?? .45), out / 2, o.material));
      parts.push(this._add(g, 'frameGrid', e.at(.5)));
    }
    return parts;
  }
  // Balconies per storey: `spacing` gives separate balconies, otherwise one continuous run.
  balconies(which, o = {}) {
    const storeys = o.storeys ?? this.site.storeys ?? 3, floor = (o.top ?? this.wallTop ?? this.site.eave_m) / storeys, depth = o.depth ?? 1.2, rail = o.railHeight ?? 1.05, parts = [];
    for (const id of this._ids(which)) {
      const e = this.edge(id), L = e.length - 2 * (o.margin ?? 1); if (L <= 1.5) continue; const g = new THREE.Group();
      const count = o.spacing ? Math.max(1, Math.round(L / o.spacing)) : 1, width = o.spacing ? Math.min(o.width ?? o.spacing * .7, L / count - .2) : L;
      for (let s = o.fromStorey ?? 1; s < (o.toStorey ?? storeys); s++) for (let k = 0; k < count; k++) {
        const x = -L / 2 + L * (k + .5) / count, y = s * floor;
        g.add(this._box(width, o.slab ?? .18, depth, x, y - (o.slab ?? .18), depth / 2, o.material));
        const rm = o.railMaterial ?? o.material;
        if (o.rail === 'solid' || o.rail === 'glass') { g.add(this._box(width, rail, .05, x, y, depth - .03, rm)); for (const sx of [-1, 1]) g.add(this._box(.05, rail, depth, x + sx * (width / 2 - .03), y, depth / 2, rm)); }
        else { g.add(this._box(width, .05, .05, x, y + rail, depth - .03, rm)); const bars = Math.max(2, Math.round(width / .45)); for (let i = 0; i <= bars; i++) g.add(this._box(.035, rail, .035, x - width / 2 + width * i / bars, y, depth - .03, rm)); }
      }
      parts.push(this._add(g, 'balconies', e.at(.5)));
    }
    return parts;
  }
  // Ground-floor arcade or colonnade standing in front of the facade.
  arcade(which, o = {}) {
    const h = o.height ?? 4.5, depth = o.depth ?? 2.4, pier = o.pier ?? .6, parts = [];
    for (const id of this._ids(which)) {
      const e = this.edge(id), L = e.length - 2 * (o.margin ?? .3); if (L <= 2) continue; const g = new THREE.Group(), n = Math.max(1, o.bays ?? Math.round(L / (o.spacing ?? 4))), bw = L / n;
      for (let i = 0; i <= n; i++) g.add(this._box(pier, h, pier, -L / 2 + bw * i, 0, depth - pier / 2, o.material));
      if (o.arch !== false) for (let i = 0; i < n; i++) {
        const R = Math.min((bw - pier) / 2, h * .45), spring = h - R - .35, s = new THREE.Shape();
        s.moveTo(-bw / 2, spring); s.lineTo(-bw / 2, h); s.lineTo(bw / 2, h); s.lineTo(bw / 2, spring); s.lineTo(R, spring); s.absarc(0, spring, R, 0, Math.PI, false); s.closePath();
        const m = new THREE.Mesh(new THREE.ExtrudeGeometry(s, { depth: pier * .7, bevelEnabled: false, curveSegments: 10 }), this._material(o.material)); m.position.set(-L / 2 + bw * (i + .5), 0, depth - pier * .85); g.add(m);
      }
      else g.add(this._box(L + pier, .4, pier, 0, h - .4, depth - pier / 2, o.material));
      g.add(this._box(L + pier, .22, depth, 0, h, depth / 2, o.roofMaterial ?? o.material));
      parts.push(this._add(g, 'arcade', e.at(.5)));
    }
    return parts;
  }
  // Glazed shopfront at street level with a stall riser below and a fascia above.
  storefront(which, o = {}) {
    const h = o.height ?? 3.6, out = o.out ?? .08, parts = [];
    for (const id of this._ids(which)) {
      const e = this.edge(id), L = e.length - 2 * (o.margin ?? .6); if (L <= 1.5) continue; const g = new THREE.Group(), n = Math.max(1, Math.round(L / (o.bay ?? 3))), base = o.base ?? .45, fascia = o.fascia ?? .6;
      g.add(this._box(L, h - base - fascia, .05, 0, base, out, o.glass)); g.add(this._box(L, base, .14, 0, 0, out + .03, o.frame)); g.add(this._box(L + .2, fascia, .2, 0, h - fascia, out + .06, o.fasciaMaterial ?? o.frame));
      for (let i = 0; i <= n; i++) g.add(this._box(.09, h - fascia, .12, -L / 2 + L * i / n, 0, out + .04, o.frame));
      parts.push(this._add(g, 'storefront', e.at(.5)));
    }
    return parts;
  }
  // Free-standing round or square columns in front of the facade.
  columns(which, o = {}) {
    const h = o.height ?? this.site.eave_m, r = o.radius ?? .35, out = o.out ?? 1.2;
    return this.along(which, o).map(f => { const g = new THREE.Group(), shaft = new THREE.Mesh(new THREE.CylinderGeometry(r * .88, r, h - .5, o.sides ?? 16), this._material(o.material)); shaft.position.set(0, .25 + (h - .5) / 2, out); g.add(shaft); g.add(this._box(r * 2.6, .25, r * 2.6, 0, 0, out, o.material)); g.add(this._box(r * 2.5, .25, r * 2.5, 0, h - .25, out, o.material)); return this._add(g, 'columns', f); });
  }

  // ---- entrances and street-level parts (first argument is a frame) ------------------
  canopy(frame, o = {}) {
    const w = o.width ?? 4, d = o.depth ?? 2, y = o.y ?? 3.2, t = o.thickness ?? .18, g = new THREE.Group();
    g.add(this._box(w, t, d, 0, y, d / 2, o.material));
    if (o.posts) for (const sx of [-1, 1]) g.add(this._box(.12, y, .12, sx * (w / 2 - .15), 0, d - .15, o.postMaterial ?? o.material));
    return this._add(g, 'canopy', frame);
  }
  awning(frame, o = {}) { const w = o.width ?? 3, d = o.depth ?? 1.2, y = o.y ?? 2.6, drop = o.drop ?? .6; const m = this._prism([[0, 0], [d, -drop], [d, -drop - .08], [0, -.08]], w, o.material); m.rotation.y = -Math.PI / 2; m.position.set(w / 2, y + drop, 0); return this._add(m, 'awning', frame); }
  stairs(frame, o = {}) { const w = o.width ?? 3, n = o.steps ?? 4, rise = o.rise ?? .17, tread = o.tread ?? .3, g = new THREE.Group(); for (let i = 0; i < n; i++) g.add(this._box(w, rise * (n - i), tread, 0, 0, tread * (i + .5), o.material)); return this._add(g, 'stairs', frame); }
  sign(frame, o = {}) { const g = new THREE.Group(); g.add(this._box(o.width ?? 3, o.height ?? .7, .12, 0, o.y ?? 3.4, (o.out ?? .12) + .06, o.material)); return this._add(g, 'sign', frame); }

  // ---- rooftop equipment (frames from b.at; height defaults to the roof there) -------
  mechanical(frame, o = {}) {
    const w = o.width ?? 3, d = o.depth ?? 2, h = o.height ?? 1.6, y = o.y ?? this.roofY(frame.x, frame.z) - .05, g = new THREE.Group();
    g.add(this._box(w, h, d, 0, y, 0, o.material));
    if (o.louvers) for (let i = 0; i < 5; i++) for (const s of [-1, 1]) g.add(this._box(w * .8, .05, .05, 0, y + h * (.2 + .14 * i), s * (d / 2 + .02), o.louvers));
    return this._add(g, 'mechanical', frame);
  }
  tank(frame, o = {}) { const r = o.radius ?? 1.2, h = o.height ?? 2.2, y = o.y ?? this.roofY(frame.x, frame.z), g = new THREE.Group(), legs = o.legs ?? .8; const body = new THREE.Mesh(new THREE.CylinderGeometry(r, r, h, 20), this._material(o.material)); body.position.y = y + legs + h / 2; g.add(body); for (let i = 0; i < 4; i++) g.add(this._box(.12, legs, .12, Math.cos(Math.PI / 4 + i * Math.PI / 2) * r * .7, y, Math.sin(Math.PI / 4 + i * Math.PI / 2) * r * .7, o.legMaterial ?? o.material)); return this._add(g, 'tank', frame); }
  antenna(frame, o = {}) { const h = o.height ?? 6, y = o.y ?? this.roofY(frame.x, frame.z), g = new THREE.Group(); const mast = new THREE.Mesh(new THREE.CylinderGeometry(.04, .09, h, 8), this._material(o.material)); mast.position.y = y + h / 2; g.add(mast); g.add(this._box(.5, .3, .5, 0, y, 0, o.material)); return this._add(g, 'antenna', frame); }
  skylight(frame, o = {}) { const w = o.width ?? 3, d = o.depth ?? 2, rise = o.rise ?? .6, y = o.y ?? this.roofY(frame.x, frame.z), g = new THREE.Group(); g.add(this._box(w + .2, .25, d + .2, 0, y, 0, o.frame ?? o.glass)); const r = this._prism([[-w / 2, 0], [w / 2, 0], [0, rise]], d, o.glass); r.position.set(0, y + .25, -d / 2); g.add(r); return this._add(g, 'skylight', frame); }
  dome(frame, o = {}) { const r = o.radius ?? 3, y = o.y ?? this.roofY(frame.x, frame.z), drum = o.drum ?? 0, g = new THREE.Group(); if (drum) { const m = new THREE.Mesh(new THREE.CylinderGeometry(r, r, drum, 24), this._material(o.drumMaterial ?? o.material)); m.position.y = y + drum / 2; g.add(m); } const cap = new THREE.Mesh(new THREE.SphereGeometry(r, 24, 12, 0, Math.PI * 2, 0, Math.PI / 2), this._material(o.material)); cap.scale.y = o.rise ? o.rise / r : 1; cap.position.y = y + drum; g.add(cap); return this._add(g, 'dome', frame); }
  spire(frame, o = {}) { const r = o.radius ?? 1, h = o.height ?? 6, y = o.y ?? this.roofY(frame.x, frame.z), m = new THREE.Mesh(new THREE.ConeGeometry(r, h, o.sides ?? 8), this._material(o.material)); m.position.y = y + h / 2; if ((o.sides ?? 8) === 4) m.rotation.y = Math.PI / 4; return this._add(m, 'spire', frame); }
  // Guard rail along edges at roof or terrace level.
  railing(which, o = {}) {
    const rail = o.height ?? 1.05, parts = [];
    for (const id of this._ids(which)) { const e = this.edge(id), L = e.length - .2, g = new THREE.Group(), y = o.y ?? this.wallTop ?? this.site.eave_m, z = -(o.inset ?? .15);
      if (o.glass) g.add(this._box(L, rail, .04, 0, y, z, o.glass)); else { const n = Math.max(2, Math.round(L / (o.spacing ?? 1.5))); for (let i = 0; i <= n; i++) g.add(this._box(.05, rail, .05, -L / 2 + L * i / n, y, z, o.material)); g.add(this._box(L, .04, .04, 0, y + rail * .5, z, o.material)); }
      g.add(this._box(L, .06, .06, 0, y + rail, z, o.material ?? o.glass)); parts.push(this._add(g, 'railing', e.at(.5))); }
    return parts;
  }
  look(o) { Object.assign(this.lookConfig, o); }
  finish() {
    this.root.updateMatrixWorld(true);
    // Free-standing objects (trees, vehicles, street furniture) have no measured wall plan to protect.
    if ((this.site.kind ?? 'building') !== 'building') { if (!this.parts.length) throw Error('KIT_DESIGN_BUILT_NOTHING'); this.root.userData.components = this.parts; this.root.userData.kitCounts = this.counts; this.root.userData.look = this.lookConfig; return this.root; }
    if (!this.counts.walls) throw Error('KIT_DESIGN_HAS_NO_WALLS: call b.walls(...)');
    const guard = this.wallGuard, positions = guard.part.object.geometry.attributes.position.array;
    const identity = new THREE.Matrix4();
    if (!guard.part.object.matrixWorld.equals(identity) || positions.length !== guard.positions.length || guard.positions.some((v, i) => v !== positions[i]) || !guard.part.object.visible) throw Error('KIT_MEASURED_WALL_GEOMETRY_MUTATED');
    this.root.userData.components = this.parts; this.root.userData.kitCounts = this.counts; this.root.userData.look = this.lookConfig; this.root.updateMatrixWorld(true); return this.root;
  }
}

// `packs` are additive part libraries: modules exporting `parts = {name(host, ...args) {...}}`.
// A part receives the builder as its host and is exposed to design scripts as `b.name(...args)`.
// Packs add vocabulary for any kind of object; they cannot replace a builtin part.
export function buildDesign(design, site, style, packs = []) {
  const b = new Builder(site, style), api = {THREE};
  for (const key of Object.getOwnPropertyNames(Builder.prototype)) if (key !== 'constructor' && key !== 'finish' && !key.startsWith('_')) api[key] = b[key].bind(b);
  const services = ['_box','_prism','_material','_surface','_add','_world','at','roofY'];
  const host = Object.freeze(Object.fromEntries([['site',b.site],['THREE',THREE],...services.filter(name=>typeof b[name]==='function').map(name=>[name,b[name].bind(b)])]));
  b.root.userData.packCalls = {};
  for (const pack of packs) for (const [name, part] of Object.entries(pack.parts ?? {})) {
    if (name in api || name.startsWith('_') || typeof part !== 'function') throw Error('KIT_PACK_PART_NAME_TAKEN_OR_INVALID:' + name);
    api[name] = (...args) => { const before=b.parts.length,result=part(host,...args);if(b.parts.length<=before)throw Error('PACK_PART_BUILT_NOTHING:'+name);b.root.userData.packCalls[name]=(b.root.userData.packCalls[name]??0)+1;return result; };
  }
  design(b.site, Object.freeze(api), deepFreeze(structuredClone(style ?? {})));
  return b.finish();
}
export const planGeometry = { toPlan, fromPlan, offset, insetLimit, area };
