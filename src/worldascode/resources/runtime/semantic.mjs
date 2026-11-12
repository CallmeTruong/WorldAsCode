import * as THREE from 'three';

// Reusable geometry generators and composition of owned Three.js factories.
const SUPPORTED = new Set(['box','hollow_shaft','gable_roof','window_frame','tree','lamp','road_strip','rail_track','loft','roof_planes']);
// A loft joins horizontal rings {y, points[[x,z]]} with flat faces and caps the top.
// Rings are compiled from evidence in Python (massing.py); this only triangulates them,
// so the fitted silhouette and the rendered mesh cannot disagree.
// Facade UVs count whole bays (u) and storeys (v) per wall edge; other lofts use metres.
function loft(c,m) {
  const rings=c.rings,positions=[],uvs=[],facade=c.facade;
  const area=p=>p.reduce((s,a,i)=>{const b=p[(i+1)%p.length];return s+a[0]*b[1]-b[0]*a[1];},0);
  const flip=area(rings[0].points)>0; // counter-clockwise in (x, north) has negative area in (x, z)
  const quad=(a,b,c2,d,ua,ub,va,vb)=>{const v=flip?[a,d,c2,a,c2,b]:[a,b,c2,a,c2,d],t=flip?[[ua,va],[ua,vb],[ub,vb],[ua,va],[ub,vb],[ub,va]]:[[ua,va],[ub,va],[ub,vb],[ua,va],[ub,vb],[ua,vb]];for(const p of v)positions.push(...p);for(const p of t)uvs.push(...p);};
  for(let k=0;k+1<rings.length;k++){
    const low=rings[k],high=rings[k+1],n=low.points.length;
    if(high.points.length!==n)throw Error('LOFT_RING_VERTEX_COUNT_MISMATCH:'+c.id);
    for(let i=0;i<n;i++){
      const j=(i+1)%n,a=low.points[i],b=low.points[j],length=Math.hypot(b[0]-a[0],b[1]-a[1]);
      const ub=facade?Math.max(1,Math.round(length/facade.bay_m)):length;
      const va=facade?(low.y-rings[0].y)/facade.storey_m:low.y,vb=facade?(high.y-rings[0].y)/facade.storey_m:high.y;
      quad([a[0],low.y,a[1]],[b[0],low.y,b[1]],[high.points[j][0],high.y,high.points[j][1]],[high.points[i][0],high.y,high.points[i][1]],0,ub,va,vb);
    }
  }
  const top=rings[rings.length-1],contour=top.points.map(p=>new THREE.Vector2(p[0],-p[1]));
  for(const f of THREE.ShapeUtils.triangulateShape(contour,[])){
    const order=THREE.ShapeUtils.isClockWise(contour)?[f[0],f[2],f[1]]:f;
    for(const i of order){positions.push(top.points[i][0],top.y,top.points[i][1]);uvs.push(facade?0:top.points[i][0],facade?0:top.points[i][1]);}
  }
  const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));g.setAttribute('uv',new THREE.Float32BufferAttribute(uvs,2));g.computeVertexNormals();
  return mesh(g,m,c.id);
}
// Measured roof: planes y = a*u + b*v + c over rectangles in the footprint's principal
// frame (u, v), each a prism from base_y up to its plane. Tops take the plane's material,
// vertical faces the side material (gable ends, tower and dormer walls, chimney shafts).
function roofPlanes(c,materials) {
  const cos=Math.cos(c.frame_angle_rad),sin=Math.sin(c.frame_angle_rad),slots=[materials.get(c.side_material)],buckets=[[]];
  const world=(u,v,y)=>[u*cos-v*sin,y,-(u*sin+v*cos)];
  for(const plane of c.planes){
    let slot=slots.indexOf(materials.get(plane.material));if(slot<0){slot=slots.push(materials.get(plane.material))-1;buckets.push([]);}
    const h=(u,v)=>Math.max(c.base_y,plane.a*u+plane.b*v+plane.c);
    for(const [u0,v0,u1,v1] of plane.rects){
      const k=[[u0,v0],[u1,v0],[u1,v1],[u0,v1]],t=k.map(([u,v])=>world(u,v,h(u,v))),b=k.map(([u,v])=>world(u,v,c.base_y));
      buckets[slot].push(t[0],t[1],t[2],t[0],t[2],t[3]);
      for(let i=0;i<4;i++){const j=(i+1)%4;if(t[i][1]-c.base_y<1e-3&&t[j][1]-c.base_y<1e-3)continue;buckets[0].push(b[i],b[j],t[j],b[i],t[j],t[i]);}
    }
  }
  const positions=[],g=new THREE.BufferGeometry();let offset=0;
  buckets.forEach((bucket,slot)=>{for(const p of bucket)positions.push(...p);g.addGroup(offset,bucket.length,slot);offset+=bucket.length;});
  g.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));g.computeVertexNormals();
  return mesh(g,slots,c.id);
}
// One tile is one bay by one storey; night windows come from the emissive map.
function facadeMaps(base){
  const p=base.pattern,size=256,draw=(paint)=>{const canvas=document.createElement('canvas');canvas.width=canvas.height=size;paint(canvas.getContext('2d'));const t=new THREE.CanvasTexture(canvas);t.wrapS=t.wrapT=THREE.RepeatWrapping;t.anisotropy=8;return t;};
  const w=p.window_width*size,h=p.window_height*size,x=(size-w)/2,y=(size-h)/2-size*.04,f=Math.max(4,size*.035);
  const map=draw(g=>{g.fillStyle=base.color;g.fillRect(0,0,size,size);g.fillStyle='rgba(0,0,0,.10)';g.fillRect(0,size-5,size,5);
    g.fillStyle=p.trim;g.fillRect(x-f,y-f,w+2*f,h+2*f);g.fillRect(x-2*f,y+h+f,w+4*f,f*1.4);g.fillStyle=p.glass;g.fillRect(x,y,w,h);
    g.fillStyle=p.trim;g.fillRect(x+w/2-f/3,y,f/1.5,h);g.fillRect(x,y+h*.42,w,f/1.5);});
  map.colorSpace=THREE.SRGBColorSpace;
  const emissiveMap=draw(g=>{g.fillStyle='#000';g.fillRect(0,0,size,size);g.fillStyle='#fff';g.fillRect(x,y,w,h);g.fillStyle='#000';g.fillRect(x+w/2-f/3,y,f/1.5,h);g.fillRect(x,y+h*.42,w,f/1.5);});
  return {map,emissiveMap};
}
function material(v){
  const m=new THREE.MeshStandardMaterial({color:v.color,roughness:v.roughness,metalness:v.metalness,emissive:v.emission});
  if(v.pattern?.kind==='facade'){const maps=facadeMaps(v);m.color.set('#ffffff');m.map=maps.map;m.emissiveMap=maps.emissiveMap;}
  m.userData.base=v;return m;
}
const geometryPool=new Map();
function geometry(key,create){if(!geometryPool.has(key))geometryPool.set(key,create());return geometryPool.get(key);}
function rng(seed) { let a=seed>>>0; return ()=>{a+=0x6d2b79f5;let t=Math.imul(a^a>>>15,1|a);t^=t+Math.imul(t^t>>>7,61|t);return ((t^t>>>14)>>>0)/4294967296;}; }
export function seedChannel(worldSeed,objectId,version,channel) {let h=2166136261;for(const byte of new TextEncoder().encode(JSON.stringify([worldSeed,objectId,version,channel]))) h=Math.imul(h^byte,16777619);return h>>>0;}
function mesh(g,m,name) {const o=new THREE.Mesh(g,m);o.name=name;o.castShadow=true;o.receiveShadow=true;return o;}
function box(size,m,name,pos=[0,0,0]) {const o=mesh(geometry('box:'+JSON.stringify(size),()=>new THREE.BoxGeometry(...size)),m,name);o.position.set(...pos);return o;}
function ring(w,h,t) {
  const s=new THREE.Shape();s.moveTo(-w/2,-h/2);s.lineTo(w/2,-h/2);s.lineTo(w/2,h/2);s.lineTo(-w/2,h/2);s.closePath();
  const p=new THREE.Path();p.moveTo(-w/2+t,-h/2+t);p.lineTo(-w/2+t,h/2-t);p.lineTo(w/2-t,h/2-t);p.lineTo(w/2-t,-h/2+t);p.closePath();s.holes.push(p);return s;
}
function opening(c,m) {
  const [w,h,d]=c.size,t=c.wall_thickness;
  const shaft=c.kind==='hollow_shaft';
  const g=geometry(c.kind+JSON.stringify([w,h,d,t]),()=>{const v=new THREE.ExtrudeGeometry(ring(w,shaft?d:h,t),{depth:shaft?h:d,bevelEnabled:false,steps:1});if(shaft){v.rotateX(-Math.PI/2);v.translate(0,-h/2,0);}else v.translate(0,0,-d/2);return v;});
  return mesh(g,m,c.id);
}
function gable(c,m) {
  const [w,h,d]=c.size,s=new THREE.Shape();s.moveTo(-w/2,-h/2);s.lineTo(w/2,-h/2);s.lineTo(0,h/2);s.closePath();
  const g=geometry('gable:'+JSON.stringify([w,h,d]),()=>{const v=new THREE.ExtrudeGeometry(s,{depth:d,bevelEnabled:false});v.translate(0,0,-d/2);return v;});return mesh(g,m,c.id);
}
function tree(c,m,random) {
  const [w,h,d]=c.size,g=new THREE.Group();g.name=c.id;
  if(!m.userData.wind){
    const wind={strength:{value:0},time:{value:0}};m.userData.wind=wind;
    m.onBeforeCompile=shader=>{shader.uniforms.worldWind=wind.strength;shader.uniforms.worldTime=wind.time;
      shader.vertexShader='uniform float worldWind; uniform float worldTime;\n'+shader.vertexShader;
      shader.vertexShader=shader.vertexShader.replace('#include <begin_vertex>','#include <begin_vertex>\n transformed.x += sin(worldTime * 1.6 + position.y * 1.9) * worldWind * 0.08 * max(position.y + 1.0, 0.0);');};
    m.customProgramCacheKey=()=> 'worldscale-foliage-wind-v1';
  }
  const bark=new THREE.MeshStandardMaterial({color:0x625347,roughness:.95});
  const trunk=mesh(new THREE.CylinderGeometry(w*.035,w*.055,h*.68,7),bark,'trunk');trunk.position.y=-h*.16;g.add(trunk);
  for(let i=0;i<11;i++) {
    const a=i*2.39996,r=Math.sqrt(random())*.31,sy=.2+random()*.14;
    const leaf=mesh(geometry('canopy-ico-2',()=>new THREE.IcosahedronGeometry(1,2)),m,'canopy-'+i);
    leaf.scale.set(w*(.17+random()*.08),h*sy,d*(.17+random()*.08));
    leaf.position.set(Math.cos(a)*w*r,h*(.08+random()*.23),Math.sin(a)*d*r);g.add(leaf);
  }return g;
}
function lamp(c,m) {
  const [w,h,d]=c.size,g=new THREE.Group();g.name=c.id;
  const pole=mesh(new THREE.CylinderGeometry(.055,.09,h,10),m,'pole');g.add(pole);
  const arm=box([w,.09,.09],m,'arm',[w/2,h/2-.08,0]);g.add(arm);
  const glow=new THREE.MeshStandardMaterial({color:0xf5ead5,emissive:0xffcf82,emissiveIntensity:0});
  glow.userData.base={roughness:.5,emissive_at_night:true,weather_response:false};
  g.add(box([w*.43,.12,Math.max(d,.23)],glow,'luminaire',[w*.85,h/2-.15,0]));
  const light=new THREE.PointLight(0xffd49a,0,12,2);light.position.set(w*.85,h/2-.3,0);light.userData.nightLight=true;g.add(light);return g;
}
export function buildWorld(world,factories={}) {
  const root=new THREE.Group();root.name='world';const definitions=new Map(world.blueprints.map(b=>[b.id,b]));
  root.userData.components=[];root.userData.factoryAssets=[];const materialPools=new Map();
  for(const instance of world.instances) {
    const b=definitions.get(instance.blueprint);
    if(b.origin==='factory'){
      const factory=factories[b.id];if(!factory)throw Error('BLUEPRINT_REQUIRES_FACTORY');
      const asset=factory({seed:(world.seed^instance.seed)>>>0,instanceId:instance.id});if(!asset?.isObject3D)throw Error('FACTORY_MUST_RETURN_OBJECT3D');asset.userData.instanceId=instance.id;asset.position.set(...instance.anchor);asset.rotation.y=instance.rotation_y;asset.scale.setScalar(instance.scale);root.add(asset);root.userData.factoryAssets.push(asset);continue;
    }
    if(!materialPools.has(b.id))materialPools.set(b.id,new Map(b.materials.map(v=>[v.id,material(v)])));
    const materials=materialPools.get(b.id);
    const asset=new THREE.Group();asset.name=instance.id;asset.position.set(...instance.anchor);asset.rotation.y=instance.rotation_y;asset.scale.setScalar(instance.scale);root.add(asset);
    const nodes=new Map();
    for(const c of b.components) {
      if(!SUPPORTED.has(c.kind))throw Error('UNSUPPORTED_GENERATOR:'+c.kind);
      const random=rng(seedChannel((world.seed^instance.seed)>>>0,instance.id+'/'+c.id,b.version,'shape'));
      const m=materials.get(c.material);let o;
      if(c.kind==='hollow_shaft'||c.kind==='window_frame')o=opening(c,m);
      else if(c.kind==='gable_roof')o=gable(c,m);
      else if(c.kind==='tree')o=tree(c,m,c.allow_shape_variation?random:()=>.5);
      else if(c.kind==='lamp')o=lamp(c,m);
      else if(c.kind==='loft')o=loft(c,m);
      else if(c.kind==='roof_planes')o=roofPlanes(c,materials);
      else if(c.kind==='rail_track'){
        const [w,h,d]=c.size;o=new THREE.Group();o.name=c.id;
        // Gauge is between the inside faces, not the rail centres.
        for(const x of [-w/2-.04,w/2+.04])o.add(box([.08,h,d],m,'rail',[x,0,0]));
        const tie=new THREE.MeshStandardMaterial({color:0x73685b,roughness:.95});
        for(let z=-d/2;z<=d/2;z+=.6)o.add(box([w+.7,.1,.2],tie,'sleeper',[0,-h/2,z]));
      } else o=box(c.size,m,c.id);
      const pivot=new THREE.Group();pivot.name=c.id+':pivot';pivot.position.set(...c.position);pivot.rotation.y=c.rotation_y;pivot.add(o);
      nodes.set(c.id,pivot);root.userData.components.push({instance:instance.id,component:c,node:o,pivot});
    }
    for(const c of b.components)(c.parent?nodes.get(c.parent):asset).add(nodes.get(c.id));
  }
  root.updateMatrixWorld(true);return root;
}
export function applyState(root,state) {
  const night=state.hour<6||state.hour>=18,seen=new Set();
  root.traverse(o=>{
    if(o.isMesh)for(const m of (Array.isArray(o.material)?o.material:[o.material])){
      if(seen.has(m))continue;seen.add(m);const base=m.userData.base;if(!base)continue;
      m.roughness=Math.max(.12,(base.roughness??.75)*(base.weather_response?1-.65*state.wetness:1));
      m.emissiveIntensity=base.emissive_at_night?(night?2:0):1;
      if(m.userData.wind)m.userData.wind.strength.value=state.wind;
    }
    if(o.userData.nightLight)o.intensity=night?28:0;
  });
  return {night,wind:state.wind,windImplemented:true};
}
export function tick(root,seconds){const seen=new Set();root.traverse(o=>{if(o.isMesh)for(const m of(Array.isArray(o.material)?o.material:[o.material]))if(!seen.has(m)){seen.add(m);if(m.userData.wind)m.userData.wind.time.value=seconds;}});}
export function semanticProbes(root) {
  root.updateMatrixWorld(true);const reports=[];
  for(const {instance,component:c,node:o} of root.userData.components??[]) {
    for(const requirement of c.semantic_requirements) {
      let passed=false,details={};
      if(requirement==='air_path'||requirement==='opening') {
        const axis=c.kind==='hollow_shaft'?new THREE.Vector3(0,1,0):new THREE.Vector3(0,0,1);
        const half=(c.kind==='hollow_shaft'?c.size[1]:c.size[2])/2;
        const centre=o.localToWorld(new THREE.Vector3());
        const direction=axis.clone().transformDirection(o.matrixWorld);
        const ray=new THREE.Raycaster(centre.clone().addScaledVector(direction,half+1),direction.clone().negate(),0,2*half+2);
        const all=root.children;const centreHits=ray.intersectObjects(all,true);
        // Also hit a real wall: an empty Group must not satisfy a cavity test.
        const wallPoint=new THREE.Vector3(c.size[0]/2-c.wall_thickness/2,0,0);o.localToWorld(wallPoint);
        const wallRay=new THREE.Raycaster(wallPoint.clone().addScaledVector(direction,half+1),direction.clone().negate(),0,2*half+2);
        const wallHits=wallRay.intersectObject(o,true);
        passed=centreHits.length===0&&wallHits.length>0;details={centreHits:centreHits.map(h=>h.object.name),wallHits:wallHits.length};
      } else if(requirement==='attached') {
        const parent=root.userData.components.find(v=>v.instance===instance&&v.component.id===c.parent);
        if(parent){const a=new THREE.Box3().setFromObject(o),b=new THREE.Box3().setFromObject(parent.node);b.expandByScalar(.06);passed=a.intersectsBox(b);}
      } else if(requirement==='track_gauge') {
        const rails=o.children.filter(x=>x.name==='rail');
        passed=rails.length===2&&Math.abs(rails[1].position.x-rails[0].position.x-.08-c.size[0])<1e-6;
      }
      reports.push({instance,component:c.id,requirement,passed,details});
    }
  }
  for(const check of root.userData.semanticChecks??[]) {
    const node=root.getObjectByName(check.component_id);let passed=false,details={};
    if(node){
      const localAxis=new THREE.Vector3(...check.axis).normalize(),centre=node.localToWorld(new THREE.Vector3(...check.centre));
      const endpoint=node.localToWorld(new THREE.Vector3(...check.centre).addScaledVector(localAxis,check.length/2));
      const half=endpoint.distanceTo(centre),axis=endpoint.sub(centre).normalize(),wall=node.localToWorld(new THREE.Vector3(...check.wall_probe));
      const ray=new THREE.Raycaster(centre.clone().addScaledVector(axis,half+.001),axis.clone().negate(),0,2*half+.002);
      const wallRay=new THREE.Raycaster(wall.clone().addScaledVector(axis,half+.001),axis.clone().negate(),0,2*half+.002);
      const hits=ray.intersectObject(root,true),walls=wallRay.intersectObject(node,true);
      passed=hits.length===0&&walls.length>0;details={centreHits:hits.map(h=>h.object.name),wallHits:walls.length};
    }else details={error:'MISSING_PROBE_COMPONENT'};
    reports.push({component:check.component_id,requirement:check.requirement,passed,details});
  }
  for(const part of root.userData.components??[])if(part.node.userData.semanticChecks?.length)reports.push(...semanticProbes(part.node).map(r=>({...r,instance:part.instance,part:part.component.id})));
  for(const asset of root.userData.factoryAssets??[])reports.push(...semanticProbes(asset).map(r=>({...r,instance:asset.userData.instanceId??asset.name})));
  return reports;
}
