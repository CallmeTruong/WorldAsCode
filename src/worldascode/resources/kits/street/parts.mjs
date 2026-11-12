// Street furniture and ground surfaces. Local frame: +X along the street, +Z across it.
import * as THREE from 'three';

function cylinder(host, r, h, material, x = 0, y = 0, z = 0, rTop = r, sides = 10) { const m = new THREE.Mesh(new THREE.CylinderGeometry(rTop, r, h, sides), host._material(material)); m.position.set(x, y + h / 2, z); return m; }

export const parts = {
  // Street lamp: pole, arm reaching over the carriageway (+Z) and a luminaire that glows at night.
  lamp(host, frame, o = {}) {
    const h = o.height ?? 7, arm = o.arm ?? 1.6, g = new THREE.Group();
    g.add(cylinder(host, .09, h, o.material, 0, 0, 0, .06)); g.add(host._box(.08, .08, arm, 0, h - .1, arm / 2, o.material)); g.add(host._box(.28, .12, .6, 0, h - .2, arm, o.lightMaterial ?? o.material));
    return host._add(g, 'lamp', frame);
  },
  bench(host, frame, o = {}) {
    const w = o.width ?? 1.8, g = new THREE.Group();
    g.add(host._box(w, .06, .45, 0, .42, 0, o.material)); g.add(host._box(w, .4, .05, 0, .5, -.22, o.material));
    for (const s of [-1, 1]) g.add(host._box(.06, .42, .42, s * (w / 2 - .12), 0, 0, o.legMaterial ?? o.material));
    return host._add(g, 'bench', frame);
  },
  bollard(host, frame, o = {}) { const g = new THREE.Group(); g.add(cylinder(host, o.radius ?? .09, o.height ?? .9, o.material)); return host._add(g, 'bollard', frame); },
  bin(host, frame, o = {}) { const g = new THREE.Group(); g.add(cylinder(host, .26, o.height ?? .9, o.material, 0, 0, 0, .3)); return host._add(g, 'bin', frame); },
  hydrant(host, frame, o = {}) { const g = new THREE.Group(); g.add(cylinder(host, .12, .55, o.material)); g.add(cylinder(host, .15, .1, o.material, 0, .55)); g.add(host._box(.42, .1, .1, 0, .32, 0, o.material)); return host._add(g, 'hydrant', frame); },
  // Pole with a sign plate facing +Z.
  roadSign(host, frame, o = {}) {
    const h = o.height ?? 2.6, s = o.size ?? .6, g = new THREE.Group();
    g.add(cylinder(host, .035, h, o.poleMaterial ?? o.material)); g.add(host._box(s, s, .03, 0, h - s, .04, o.material));
    return host._add(g, 'roadSign', frame);
  },
  trafficLight(host, frame, o = {}) {
    const h = o.height ?? 3.4, g = new THREE.Group();
    g.add(cylinder(host, .06, h, o.material)); g.add(host._box(.3, .9, .26, 0, h - .9, .1, o.material));
    ['red', 'amber', 'green'].forEach((name, i) => { if (o[name]) g.add(host._box(.16, .16, .04, 0, h - .32 - i * .28, .25, o[name])); });
    return host._add(g, 'trafficLight', frame);
  },
  // Bus shelter: roof, back panel and one side panel, open toward +Z.
  busShelter(host, frame, o = {}) {
    const w = o.width ?? 4, d = o.depth ?? 1.5, h = o.height ?? 2.5, g = new THREE.Group();
    g.add(host._box(w + .2, .1, d + .2, 0, h, 0, o.material)); g.add(host._box(w, h - .3, .04, 0, .15, -d / 2, o.glass ?? o.material)); g.add(host._box(.04, h - .3, d, -w / 2, .15, 0, o.glass ?? o.material));
    for (const [x, z] of [[-w / 2, d / 2], [w / 2, d / 2], [w / 2, -d / 2]]) g.add(host._box(.08, h, .08, x, 0, z, o.material));
    g.add(host._box(w * .6, .06, .4, 0, .45, -d / 2 + .3, o.material));
    return host._add(g, 'busShelter', frame);
  },
  // Fence or railing along the frame's X axis.
  fence(host, frame, o = {}) {
    const L = o.length ?? 8, h = o.height ?? 1.2, n = Math.max(1, Math.round(L / (o.spacing ?? 2))), g = new THREE.Group();
    for (let i = 0; i <= n; i++) g.add(host._box(.08, h, .08, -L / 2 + L * i / n, 0, 0, o.material));
    if (o.solid) g.add(host._box(L, h * .8, .04, 0, h * .1, 0, o.panelMaterial ?? o.material)); else for (const y of [h * .35, h * .9]) g.add(host._box(L, .05, .05, 0, y, 0, o.material));
    return host._add(g, 'fence', frame);
  },
  // Carriageway strip along X with lane markings.
  road(host, frame, o = {}) {
    const L = o.length ?? 40, w = o.width ?? 7, lanes = o.lanes ?? 2, g = new THREE.Group();
    if(!(L>0&&w>0))throw Error('PACK_INVALID_ROAD_SIZE');
    const asphalt=host._box(L,.1,w,0,-.1,0,o.material);if(o.textured!==false)asphalt.material=host._surface(o.material,{type:'asphalt',scale:o.textureScale??2,cracks:o.cracks??false},o.textureSeed??0);g.add(asphalt);
    if (o.marking) {
      const start=o.station_m??0,dash=o.dashLength??3,period=dash+(o.dashGap??3);
      if(!(dash>0&&period>dash))throw Error('PACK_INVALID_DASH_PATTERN');
      for(let k=1;k<lanes;k++)for(let station=Math.floor(start/period)*period;station<start+L;station+=period){const a=Math.max(start,station),b=Math.min(start+L,station+dash);if(b>a)g.add(host._box(b-a,.008,.1,(a+b)/2-start-L/2,0,-w/2+w*k/lanes,o.marking));}
      for(const s of [-1,1])g.add(host._box(L,.008,.09,0,0,s*(w/2-.22),o.marking));
    }
    return host._add(g, 'road', frame);
  },
  // Raised pavement strip along X with a kerb on its +Z side.
  sidewalk(host, frame, o = {}) { const L = o.length ?? 40, w = o.width ?? 3, k = o.kerb ?? .15, g = new THREE.Group();const slab=host._box(L,k,w,0,0,0,o.material);if(o.textured!==false)slab.material=host._surface(o.material,{type:'concrete',scale:o.textureScale??2.4,unit_m:o.paverSize??.6},o.textureSeed??0);g.add(slab);for(let x=-L/2;x<L/2;x+=1){const len=Math.min(.99,L/2-x);g.add(host._box(len,k+.01,.18,x+len/2,0,w/2-.09,o.kerbMaterial??o.material));}return host._add(g,'sidewalk',frame); },
  // Zebra crossing: stripes laid across a road running along X.
  crosswalk(host, frame, o = {}) { const w = o.width ?? 7, len = o.length ?? 3, n = Math.max(2, Math.round(w / .9)), g = new THREE.Group(); for (let i = 0; i < n; i++) g.add(host._box(len, .014, w / n * .55, 0, 0, -w / 2 + w * (i + .5) / n, o.material)); return host._add(g, 'crosswalk', frame); },
};
