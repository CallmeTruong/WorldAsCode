// Vegetation parts. Shapes vary with `seed` so instances of one recipe are not clones.
import * as THREE from 'three';

function rng(seed) { let a = (seed >>> 0) || 1; return () => { a += 0x6d2b79f5; let t = Math.imul(a ^ a >>> 15, 1 | a); t ^= t + Math.imul(t ^ t >>> 7, 61 | t); return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
const seedOf = (host, o) => o.seed ?? host.site.seed ?? 1;

export const parts = {
  // Seeded branch skeleton and instanced, folded leaf blades. LOD is explicit.
  tree(host, frame, o = {}) {
    const h=o.height??8,r=o.crown??h*.3;
    if(!(h>0&&r>0))throw Error('PACK_INVALID_TREE_SIZE');
    const seed=o.seed??((seedOf(host,o)^Math.round(frame.x*73856093)^Math.round(frame.z*19349663))>>>0),random=rng(seed),g=new THREE.Group();
    const bark=o.textured===false?host._material(o.trunkMaterial):host._surface(o.trunkMaterial,{type:'bark',scale:1.5},o.textureSeed??0);
    const leafMaterial=(o.textured===false?host._material(o.leafMaterial):host._surface(o.leafMaterial,{type:'foliage',scale:1,cluster:true},o.textureSeed??0)).clone();leafMaterial.side=THREE.DoubleSide;
    const branch=(start,end,radius)=>{const delta=end.clone().sub(start),geometry=new THREE.CylinderGeometry(radius*.38,radius,delta.length(),8,2),uv=geometry.attributes.uv;
      for(let i=0;i<uv.count;i++)uv.setXY(i,uv.getX(i)*Math.PI*radius*2,uv.getY(i)*delta.length());
      const mesh=new THREE.Mesh(geometry,bark);mesh.position.copy(start).add(end).multiplyScalar(.5);mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),delta.normalize());g.add(mesh);};
    const fork=new THREE.Vector3((random()-.5)*h*.045,h*(o.trunkFraction??.34),(random()-.5)*h*.045);
    branch(new THREE.Vector3(),fork,o.trunkRadius??h*.045);
    for(let i=0;i<5;i++){const a=i/5*Math.PI*2;branch(new THREE.Vector3(Math.cos(a)*h*.04,.015,Math.sin(a)*h*.04),new THREE.Vector3(0,h*.14,0),h*.014);}
    const clusters=[],lobes=Math.max(5,Math.min(24,o.lobes??12));
    for(let i=0;i<lobes;i++){const a=i*2.39996+random()*.3,d=r*(.15+Math.sqrt(random())*.65),centre=new THREE.Vector3(Math.cos(a)*d,h*(.46+random()*.32),Math.sin(a)*d);
      const size=new THREE.Vector3(r*(.34+random()*.13),h*(.15+random()*.05),r*(.34+random()*.13));clusters.push({centre,size});branch(fork,centre,h*(.008+random()*.008));
      for(let j=0;j<2;j++)branch(centre.clone().lerp(fork,.3),centre.clone().add(new THREE.Vector3((random()-.5)*r*.6,(random()-.5)*r*.4,(random()-.5)*r*.6)),h*.004);}
    const defaults={near:3200,medium:1800,far:300},count=Math.max(60,Math.min(6000,o.leaves??defaults[o.lod??'medium']??1800));
    const geometry=new THREE.PlaneGeometry(1,1,2,2),position=geometry.attributes.position;
    for(let i=0;i<position.count;i++)position.setZ(i,.1*(1-Math.abs(position.getX(i))*2));geometry.computeVertexNormals();
    const leaves=new THREE.InstancedMesh(geometry,leafMaterial,count),dummy=new THREE.Object3D(),colour=new THREE.Color();leaves.name='leaf-sprays';
    for(let i=0;i<count;i++){const c=clusters[i%clusters.length],theta=random()*Math.PI*2,cos=2*random()-1,sin=Math.sqrt(1-cos*cos),distance=Math.cbrt(random());
      dummy.position.set(c.centre.x+Math.cos(theta)*sin*distance*c.size.x,c.centre.y+cos*distance*c.size.y,c.centre.z+Math.sin(theta)*sin*distance*c.size.z);
      dummy.rotation.set((random()-.5)*Math.PI,random()*Math.PI*2,(random()-.5)*1.2);
      const length=(o.leafSize??h*.02)*(.7+random()*.6)*(o.lod==='far'?2.5:1);dummy.scale.set(length*.7*4.2,length*4.2,1);dummy.updateMatrix();leaves.setMatrixAt(i,dummy.matrix);colour.setScalar(.76+random()*.32);leaves.setColorAt(i,colour);}
    leaves.instanceMatrix.needsUpdate=true;leaves.computeBoundingBox();leaves.computeBoundingSphere();g.add(leaves);
    return host._add(g,'tree',frame);
  },
  // Conifer: stacked cones narrowing to a tip.
  conifer(host, frame, o = {}) {
    const h = o.height ?? 10, r = o.crown ?? h * .2, tiers = o.tiers ?? 5, g = new THREE.Group(), trunkH = h * .18;
    const trunk = new THREE.Mesh(new THREE.CylinderGeometry(h * .02, h * .03, trunkH, 8), host._material(o.trunkMaterial)); trunk.position.y = trunkH / 2; g.add(trunk);
    for (let i = 0; i < tiers; i++) { const t = i / tiers, ch = (h - trunkH) / tiers * 1.7, cone = new THREE.Mesh(new THREE.ConeGeometry(r * (1 - t * .75), ch, 10), host._material(o.leafMaterial)); cone.position.y = trunkH + (h - trunkH) * t + ch / 2 - ch * .2; g.add(cone); }
    return host._add(g, 'conifer', frame);
  },
  // Palm: slender curved trunk and drooping fronds.
  palm(host, frame, o = {}) {
    const h = o.height ?? 9, random = rng(seedOf(host, o)), g = new THREE.Group(), lean = (random() - .5) * .12;
    for (let i = 0; i < 6; i++) { const seg = new THREE.Mesh(new THREE.CylinderGeometry(h * .016, h * .02, h / 6 + .05, 8), host._material(o.trunkMaterial)); seg.position.set(lean * i * i * .25, h / 6 * (i + .5), 0); g.add(seg); }
    const top = new THREE.Vector3(lean * 9, h, 0), fronds = o.fronds ?? 9;
    for (let i = 0; i < fronds; i++) { const a = i / fronds * Math.PI * 2, len = h * (.26 + random() * .08), frond = new THREE.Mesh(new THREE.BoxGeometry(len, .04, h * .05), host._material(o.leafMaterial)); frond.position.copy(top).add(new THREE.Vector3(Math.cos(a) * len * .45, -len * .18, Math.sin(a) * len * .45)); frond.rotation.set(0, -a, -.45); g.add(frond); }
    return host._add(g, 'palm', frame);
  },
  shrub(host, frame, o = {}) {
    const r = o.radius ?? .8, random = rng(seedOf(host, o)), g = new THREE.Group();
    for (let i = 0; i < 4; i++) { const s = r * (.6 + random() * .4), m = new THREE.Mesh(new THREE.IcosahedronGeometry(s, 1), host._material(o.leafMaterial)); m.position.set((random() - .5) * r, s * .7, (random() - .5) * r); m.scale.y = .75; g.add(m); }
    return host._add(g, 'shrub', frame);
  },
  // Clipped hedge running along the frame's X axis.
  hedge(host, frame, o = {}) { const g = new THREE.Group(); g.add(host._box(o.length ?? 6, o.height ?? 1.1, o.depth ?? .7, 0, 0, 0, o.leafMaterial)); return host._add(g, 'hedge', frame); },
  // Raised planter box with soil.
  planter(host, frame, o = {}) { const w = o.width ?? 2, d = o.depth ?? .8, h = o.height ?? .55, g = new THREE.Group(); g.add(host._box(w, h, d, 0, 0, 0, o.material)); g.add(host._box(w - .16, .06, d - .16, 0, h - .02, 0, o.soilMaterial ?? o.material)); return host._add(g, 'planter', frame); },
};
