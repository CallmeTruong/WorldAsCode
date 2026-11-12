// Synthetic, seeded material channels. Tiles are measured in metres via UVs;
// these are authored surfaces, never recovered source PBR.
import * as THREE from 'three';

function random(seed) {
  let s = 2166136261;
  for (const c of String(seed)) s = Math.imul(s ^ c.charCodeAt(0), 16777619);
  return () => { s += 0x6D2B79F5; let t = Math.imul(s ^ s >>> 15, 1 | s); t ^= t + Math.imul(t ^ t >>> 7, 61 | t); return ((t ^ t >>> 14) >>> 0) / 4294967296; };
}
function texture(canvas, colour, scale) {
  const t = new THREE.CanvasTexture(canvas);
  t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(1 / scale, 1 / scale);
  t.anisotropy = 8;
  if (colour) t.colorSpace = THREE.SRGBColorSpace;
  return t;
}
export function surfaceMaps(color, surface, seed = 0) {
  const size = 512, type = surface.type, tileMetres = surface.scale ?? 2.4;
  if (!(tileMetres > 0)) throw Error('KIT_INVALID_SURFACE_SCALE');
  const canvases = Array.from({length: 3}, () => { const c = document.createElement('canvas'); c.width = c.height = size; return c; });
  const [a, h, r] = canvases.map(c => c.getContext('2d'));
  const rng = random(seed), base = new THREE.Color(color), secondary = new THREE.Color(surface.color2 ?? color);
  a.fillStyle = '#' + base.clone().multiplyScalar(.73).getHexString(); a.fillRect(0, 0, size, size);
  h.fillStyle = '#444'; h.fillRect(0, 0, size, size);
  r.fillStyle = '#ddd'; r.fillRect(0, 0, size, size);
  // Physical tile size controls course count, rather than squeezing a fixed
  // eight courses into a fraction of a metre.
  const course = surface.course_m ?? (type === 'brick' ? .075 : type === 'slate' ? .24 : .6);
  const rows = Math.max(1, Math.round(tileMetres / course));
  const cols = Math.max(1, Math.round(tileMetres / (surface.unit_width_m ?? (type === 'brick' ? .23 : type === 'slate' ? .32 : .8))));
  const ch = size / rows, cw = size / cols;
  for (let row = 0; row < rows; row++) for (let col = -1; col <= cols; col++) {
    const x = (col + (row % 2) / 2) * cw, y = row * ch, gap = type === 'brick' ? Math.max(.8, size / tileMetres * .008) : 1;
    const value = .89 + rng() * .2;
    a.fillStyle = '#' + base.clone().lerp(secondary, rng() * .22).multiplyScalar(value).getHexString();
    a.fillRect(x + gap, y + gap, cw - gap, ch - gap);
    h.fillStyle = type === 'slate' ? `rgb(${180 + row % 2 * 20},${180 + row % 2 * 20},${180 + row % 2 * 20})` : '#ccc';
    h.fillRect(x + gap, y + gap, cw - gap, ch - gap);
    const rough = Math.round(185 + rng() * 45); r.fillStyle = `rgb(${rough},${rough},${rough})`;
    r.fillRect(x + gap, y + gap, cw - gap, ch - gap);
  }
  // Low amplitude pore variation at an independent frequency, without random
  // colour speckles dominating the architecture.
  const image = a.getImageData(0, 0, size, size);
  for (let i = 0; i < image.data.length; i += 4) {
    const delta = (rng() - .5) * 5;
    for (let c = 0; c < 3; c++) image.data[i + c] += delta;
  }
  a.putImageData(image, 0, 0);
  return {map: texture(canvases[0], true, tileMetres), bumpMap: texture(canvases[1], false, tileMetres), roughnessMap: texture(canvases[2], false, tileMetres)};
}

export function metricUVs(geometry) {
  const p = geometry.attributes.position, n = geometry.attributes.normal;
  if (!p || !n) return geometry;
  const uv = [];
  for (let i = 0; i < p.count; i++) {
    const nx = Math.abs(n.getX(i)), ny = Math.abs(n.getY(i)), nz = Math.abs(n.getZ(i));
    uv.push(nx > ny && nx > nz ? p.getZ(i) : p.getX(i), ny >= nx && ny >= nz ? p.getZ(i) : p.getY(i));
  }
  geometry.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
  return geometry;
}
