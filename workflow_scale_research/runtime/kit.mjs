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
    this.site = site; this.style = style ?? {}; this.THREE = THREE;
    this.plan = toPlan(site.footprint); this.root = new THREE.Group(); this.root.name = site.object_id ?? 'building';
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
    const color = spec.color ?? '#999999', m = new THREE.MeshStandardMaterial({ color, roughness: spec.roughness ?? 0.8, metalness: spec.metalness ?? 0 });
    m.userData.base = { roughness: spec.roughness ?? 0.8, emissive_at_night: false, weather_response: spec.weather ?? true };
    m.userData.spec = { ...spec, color };
    if (spec.surface && spec.surface.type !== 'plain') {
      m.map = canvasTexture(256, (g, size) => paintSurface(g, size, color, spec.surface)); m.map.colorSpace = THREE.SRGBColorSpace;
      const s = 1 / (spec.surface.scale ?? 2); m.map.repeat.set(s, s); m.color.set('#ffffff');
    }
    if (spec.glow) { m.emissive.set(spec.glow); m.emissiveIntensity = 0; m.userData.base.emissive_at_night = true; }
    this.materials.set(name, m); return name;
  }
  _material(name) { const m = this.materials.get(name); if (!m) throw Error('KIT_UNKNOWN_MATERIAL:' + name + ' (declare it with b.material first)'); return m; }
  _facadeMaterial(name, facade) {
    const key = name + '#facade#' + JSON.stringify(facade);
    if (!this.materials.has(key)) {
      const base = this._material(name), spec = base.userData.spec, maps = windowTile({ ...facade, surface: spec.surface }, spec.color);
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
    const pivot = new THREE.Group(); this.counts[type] = (this.counts[type] ?? 0) + 1; const id = type + '-' + this.counts[type];
    pivot.name = id + ':pivot'; if (frame) { pivot.position.set(frame.x, 0, frame.z); pivot.rotation.y = frame.yaw ?? 0; }
    object.name = object.name || id; pivot.add(object); this.root.add(pivot);
    object.traverse(o => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; if (!o.name) o.name = id; } });
    this.parts.push({ instance: this.root.name, component: { id, kind: type, semantic_requirements: [] }, node: object, pivot });
    return { id, object, pivot };
  }
  _loft(rings, material, facade) {
    const positions = [], uvs = [];
    const quad = (a, b, c, d, ua, ub, va, vb) => { for (const p of [a, b, c, a, c, d]) positions.push(...p); uvs.push(ua, va, ub, va, ub, vb, ua, va, ub, vb, ua, vb); };
    for (let k = 0; k + 1 < rings.length; k++) {
      const low = rings[k], high = rings[k + 1], n = low.plan.length; if (high.plan.length !== n) throw Error('KIT_LOFT_RING_MISMATCH');
      for (let i = 0; i < n; i++) {
        const j = (i + 1) % n, a = low.plan[i], b = low.plan[j], length = Math.hypot(b[0] - a[0], b[1] - a[1]);
        const ub = facade ? Math.max(1, Math.round(length / facade.bay)) : length, va = facade ? (low.y - rings[0].y) / facade.storey : low.y, vb = facade ? (high.y - rings[0].y) / facade.storey : high.y;
        quad([a[0], low.y, -a[1]], [b[0], low.y, -b[1]], [high.plan[j][0], high.y, -high.plan[j][1]], [high.plan[i][0], high.y, -high.plan[i][1]], 0, ub, va, vb);
      }
    }
    const top = rings[rings.length - 1], contour = top.plan.map(p => new THREE.Vector2(p[0], p[1]));
    for (const f of THREE.ShapeUtils.triangulateShape(contour, [])) for (const i of f) { positions.push(top.plan[i][0], top.y, -top.plan[i][1]); uvs.push(top.plan[i][0], top.plan[i][1]); }
    const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3)); g.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2)); g.computeVertexNormals();
    return new THREE.Mesh(g, material);
  }
  walls(o = {}) {
    const height = o.height ?? this.site.eave_m, y = o.y ?? 0, storeys = o.storeys ?? this.site.storeys ?? 3, facade = { bay: o.bay ?? 3.2, storey: height / storeys, window: o.window, course: o.course };
    const m = o.windows === false ? this._material(o.material) : this._facadeMaterial(o.material, facade);
    this.wallTop = Math.max(this.wallTop ?? 0, y + height);
    return this._add(this._loft([{ y, plan: this.plan }, { y: y + height, plan: this.plan }], m, o.windows === false ? null : facade), 'walls');
  }
  band(o = {}) {
    const plan = offset(this.plan, -(o.out ?? 0.25)); if (!plan) throw Error('KIT_BAND_OFFSET_FAILED');
    const y = o.y ?? this.site.eave_m - (o.height ?? 0.4);
    return this._add(this._loft([{ y, plan }, { y: y + (o.height ?? 0.4), plan }], this._material(o.material)), 'band');
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
    return { ...this._add(this._loft(rings, this._material(o.material)), 'roof'), ridgeY: this.roofProfile.top, eaveY: eave };
  }
  // Height of the roof surface (or wall top outside any roof) at a plan position.
  roofY(x, z) {
    const p = this.roofProfile; if (!p) return this.wallTop ?? this.site.eave_m;
    if (!inside(this.plan, x, -z)) return p.eave;
    let d = Infinity; this.edges.forEach((e, i) => { if (p.weights[i] > 0) d = Math.min(d, segmentDistance(e.a, e.b, x, -z)); });
    for (let k = 0; k + 1 < p.insets.length; k++) if (p.insets[k + 1] > p.insets[k] && d <= p.insets[k + 1]) return p.ys[k] + (p.ys[k + 1] - p.ys[k]) * (d - p.insets[k]) / (p.insets[k + 1] - p.insets[k]);
    return p.top;
  }
  _world(frame, lx, lz) { const c = Math.cos(frame.yaw ?? 0), s = Math.sin(frame.yaw ?? 0); return [frame.x + lx * c + lz * s, frame.z - lx * s + lz * c]; }
  // -- primitives in a frame's local space (x along, y up, z out)
  _box(w, h, d, x, y, z, material) { const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), this._material(material)); m.position.set(x, y + h / 2, z); return m; }
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
    g.add(this._box(w, body, d, 0, y, z0 - d / 2, o.material ?? o.wall));
    if (o.roof !== 'flat') { const r = this._prism(o.roof === 'shed' ? [[-w / 2 - .12, 0], [w / 2 + .12, 0], [w / 2 + .12, h - body], [-w / 2 - .12, (h - body) * .3]] : [[-w / 2 - .15, 0], [w / 2 + .15, 0], [0, h - body]], d + 0.15, o.roofMaterial ?? o.material); r.position.set(0, y + body, z0 - d); g.add(r); }
    if (o.window !== false && o.glass) g.add(this._box(w * 0.6, body * 0.62, 0.06, 0, y + body * 0.2, z0 + 0.02, o.glass));
    return this._add(g, 'dormer', frame);
  }
  chimney(frame, o = {}) {
    const w = o.width ?? 0.9, d = o.depth ?? 0.6, top = this.roofY(frame.x, frame.z) + (o.height ?? 1.6), y = this.roofY(frame.x, frame.z) - 0.6, g = new THREE.Group();
    g.add(this._box(w, top - y, d, 0, y, 0, o.material));
    if (o.cap !== false) g.add(this._box(w + 0.16, 0.14, d + 0.16, 0, top, 0, o.capMaterial ?? o.material));
    for (let i = 0; i < (o.pots ?? 0); i++) { const pot = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.12, 0.35, 8), this._material(o.potMaterial ?? o.material)); pot.position.set((i - (o.pots - 1) / 2) * w / o.pots, top + 0.31, 0); g.add(pot); }
    return this._add(g, 'chimney', frame);
  }
  // A wall-plane gable: the facade continues above the eave to a peak, with its own roof running inward.
  gable(frame, o = {}) {
    const w = o.width ?? 4, h = o.height ?? 3, d = o.depth ?? 3, y = o.y ?? this.wallTop ?? this.site.eave_m, g = new THREE.Group(), stem = o.stem ?? 0;
    const front = this._prism([[-w / 2, 0], [w / 2, 0], [w / 2, stem], [0, stem + h], [-w / 2, stem]], 0.3, o.material); front.position.set(0, y, (o.out ?? 0.05) - 0.3); g.add(front);
    const roof = this._prism([[-w / 2 - .2, stem], [w / 2 + .2, stem], [0, stem + h + .15]], d, o.roofMaterial ?? o.material); roof.position.set(0, y, -d - 0.25); g.add(roof);
    if (stem > 0) g.add(this._box(w, stem, d, 0, y, -d / 2 - 0.25, o.material));
    if (o.glass) g.add(this._box(w * 0.22, (stem + h) * 0.3, 0.06, 0, y + (stem + h) * 0.22, (o.out ?? 0.05) + 0.02, o.glass));
    return this._add(g, 'gable', frame);
  }
  turret(frame, o = {}) {
    const r = o.radius ?? 1.6, sides = o.sides ?? 8, y = o.y ?? 0, wall = (o.wallTop ?? (this.wallTop ?? this.site.eave_m) + 1.5) - y, g = new THREE.Group();
    const shaft = new THREE.Mesh(new THREE.CylinderGeometry(r, r, wall, sides), this._material(o.material)); shaft.position.y = y + wall / 2; if (sides === 4) shaft.rotation.y = Math.PI / 4; g.add(shaft);
    const cap = o.roof === 'dome' ? new THREE.Mesh(new THREE.SphereGeometry(r * 1.05, Math.max(sides, 12), 8, 0, Math.PI * 2, 0, Math.PI / 2), this._material(o.roofMaterial ?? o.material)) : new THREE.Mesh(new THREE.ConeGeometry(r * 1.12, o.roofHeight ?? r * 2.2, sides), this._material(o.roofMaterial ?? o.material));
    cap.position.y = y + wall + (o.roof === 'dome' ? 0 : (o.roofHeight ?? r * 2.2) / 2); if (sides === 4) cap.rotation.y = Math.PI / 4; g.add(cap);
    if (o.finial) { const f = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.06, o.finial, 6), this._material(o.finialMaterial ?? o.roofMaterial ?? o.material)); f.position.y = y + wall + (o.roofHeight ?? r * 2.2) + o.finial / 2; g.add(f); }
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
  look(o) { Object.assign(this.lookConfig, o); }
  finish() {
    if (!this.counts.walls) throw Error('KIT_DESIGN_HAS_NO_WALLS: call b.walls(...)');
    this.root.userData.components = this.parts; this.root.userData.kitCounts = this.counts; this.root.userData.look = this.lookConfig; this.root.updateMatrixWorld(true); return this.root;
  }
}

export function buildDesign(design, site, style) { const b = new Builder(site, style); design(site, b, style); return b.finish(); }
export const planGeometry = { toPlan, fromPlan, offset, insetLimit, area };
