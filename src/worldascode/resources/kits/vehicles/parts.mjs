// Vehicles. Local frame: +X is forward, the vehicle stands on y = 0.
import * as THREE from 'three';

function wheels(host, g, length, width, radius, material, axles) {
  for (const x of axles) for (const s of [-1, 1]) { const w = new THREE.Mesh(new THREE.CylinderGeometry(radius, radius, .22, 14), host._material(material)); w.rotation.x = Math.PI / 2; w.position.set(x * length, radius, s * (width / 2 - .08)); g.add(w); }
}
// Side profile [[x, y], ...] (x forward, as fractions of length/height) extruded across the width.
function body(host, profile, length, height, width, y, material) {
  const shape = new THREE.Shape(); profile.forEach(([x, v], i) => i ? shape.lineTo(x * length, v * height) : shape.moveTo(x * length, v * height)); shape.closePath();
  const m = new THREE.Mesh(new THREE.ExtrudeGeometry(shape, { depth: width, bevelEnabled: false }), host._material(material)); m.position.set(0, y, -width / 2); return m;
}

export const parts = {
  // Passenger car. `form`: 'sedan' | 'hatch' | 'suv'.
  car(host, frame, o = {}) {
    const form = o.form ?? 'sedan', L = o.length ?? (form === 'suv' ? 4.7 : 4.4), W = o.width ?? 1.8, H = o.height ?? (form === 'suv' ? 1.7 : 1.45), r = o.wheelRadius ?? .33, g = new THREE.Group();
    const cabin = form === 'sedan' ? [[-.22, .5], [-.12, 1], [.18, 1], [.3, .5]] : form === 'hatch' ? [[-.46, .52], [-.4, 1], [.16, 1], [.3, .5]] : [[-.47, .5], [-.44, 1], [.2, 1], [.32, .5]];
    g.add(body(host, [[-.5, 0], [.5, 0], [.5, .34], [.44, .5], [-.5, .5]], L, H - r * .6, W, r * .6, o.material));
    g.add(body(host, cabin, L, H - r * .6, W * .9, r * .6, o.glass ?? o.material));
    g.add(body(host, cabin.map(([x, y]) => [x, y === 1 ? 1.02 : .97]).slice(1, 3).concat([[cabin[2][0], .97], [cabin[1][0], .97]]), L, H - r * .6, W * .92, r * .6, o.material));
    wheels(host, g, L, W, r, o.wheelMaterial ?? o.material, [-.3, .31]);
    return host._add(g, 'car', frame);
  },
  van(host, frame, o = {}) {
    const L = o.length ?? 5.2, W = o.width ?? 1.95, H = o.height ?? 2.2, r = .36, g = new THREE.Group();
    g.add(body(host, [[-.5, 0], [.5, 0], [.5, .4], [.4, .62], [.3, 1], [-.5, 1]], L, H - r * .6, W, r * .6, o.material));
    g.add(body(host, [[.3, .98], [.4, .62], [.3, .62], [.22, .98]], L, H - r * .6, W * 1.01, r * .6, o.glass ?? o.material));
    wheels(host, g, L, W, r, o.wheelMaterial ?? o.material, [-.32, .33]);
    return host._add(g, 'van', frame);
  },
  bus(host, frame, o = {}) {
    const L = o.length ?? 12, W = o.width ?? 2.55, H = o.height ?? 3.1, r = .48, g = new THREE.Group();
    g.add(host._box(L, H - r * .7, W, 0, r * .7, 0, o.material));
    g.add(host._box(L * .9, (H - r) * .32, W + .02, 0, r * .7 + (H - r) * .45, 0, o.glass ?? o.material));
    g.add(host._box(.04, (H - r) * .45, W * .9, L / 2 + .01, r * .7 + (H - r) * .38, 0, o.glass ?? o.material));
    wheels(host, g, L, W, r, o.wheelMaterial ?? o.material, [-.3, .33]);
    return host._add(g, 'bus', frame);
  },
  // Rigid truck: cab and box body.
  truck(host, frame, o = {}) {
    const L = o.length ?? 8, W = o.width ?? 2.5, H = o.height ?? 3.4, r = .5, cab = L * .24, g = new THREE.Group();
    g.add(host._box(cab, H * .62, W, L / 2 - cab / 2, r * .8, 0, o.material)); g.add(host._box(cab * .5, H * .22, W + .02, L / 2 - cab * .2, r * .8 + H * .34, 0, o.glass ?? o.material));
    g.add(host._box(L - cab - .2, H - r * 1.1, W, -cab / 2 - .1, r * 1.1, 0, o.bodyMaterial ?? o.material)); g.add(host._box(L, .25, W * .7, 0, r * .8, 0, o.wheelMaterial ?? o.material));
    wheels(host, g, L, W, r, o.wheelMaterial ?? o.material, [-.34, -.2, .36]);
    return host._add(g, 'truck', frame);
  },
  // Tram or train car on its own track gauge.
  tram(host, frame, o = {}) {
    const L = o.length ?? 14, W = o.width ?? 2.4, H = o.height ?? 3.3, g = new THREE.Group();
    g.add(host._box(L, H - .5, W, 0, .5, 0, o.material)); g.add(host._box(L * .92, (H - .5) * .34, W + .02, 0, .5 + (H - .5) * .42, 0, o.glass ?? o.material));
    g.add(host._box(L * .8, .35, W * .8, 0, .15, 0, o.wheelMaterial ?? o.material)); g.add(host._box(.1, .9, .1, 0, H, 0, o.wheelMaterial ?? o.material));
    return host._add(g, 'tram', frame);
  },
  bicycle(host, frame, o = {}) {
    const g = new THREE.Group(), r = .34;
    for (const x of [-.52, .52]) { const w = new THREE.Mesh(new THREE.TorusGeometry(r, .025, 6, 18), host._material(o.wheelMaterial ?? o.material)); w.position.set(x, r, 0); g.add(w); }
    g.add(host._box(1.04, .04, .04, 0, r + .32, 0, o.material)); g.add(host._box(.04, .5, .04, -.2, r + .3, 0, o.material)); g.add(host._box(.04, .55, .04, .46, r + .25, 0, o.material)); g.add(host._box(.06, .04, .46, .46, r + .8, 0, o.material));
    return host._add(g, 'bicycle', frame);
  },
};
