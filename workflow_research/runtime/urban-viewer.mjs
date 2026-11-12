import * as THREE from 'three';
import {RoomEnvironment} from 'three/addons/environments/RoomEnvironment.js';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {treeBatches,frondMeshData} from './urban-trees.mjs';
import {proceduralSurface} from './urban-procedural-materials.mjs';

const W=1440,H=1080;
const renderer=new THREE.WebGLRenderer({antialias:true,preserveDrawingBuffer:true});
renderer.debug.onShaderError=()=>{throw Error('URBAN_SHADER_COMPILE_FAILURE');};
renderer.setSize(W,H);renderer.setPixelRatio(1);renderer.outputColorSpace=THREE.SRGBColorSpace;
renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.shadowMap.enabled=true;renderer.shadowMap.type=THREE.PCFSoftShadowMap;
renderer.shadowMap.autoUpdate=false;renderer.shadowMap.needsUpdate=true;
document.body.style.margin='0';document.body.appendChild(renderer.domElement);
const scene=new THREE.Scene();
let camera=new THREE.OrthographicCamera(-320,320,240,-240,.1,2500);
const controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=true;controls.maxPolarAngle=Math.PI*.49;
const hemi=new THREE.HemisphereLight(0xd8efff,0x727966,1.7);scene.add(hemi);
const sun=new THREE.DirectionalLight(0xfff3dc,2.2);sun.position.set(-250,550,230);
sun.castShadow=true;sun.shadow.mapSize.set(2048,2048);sun.shadow.camera.left=-400;sun.shadow.camera.right=400;
sun.shadow.camera.top=400;sun.shadow.camera.bottom=-400;sun.shadow.camera.far=1200;sun.shadow.normalBias=.12;sun.shadow.bias=-.00008;scene.add(sun);
let root,city,textures={},materials={},groups={},style,buildingScene,buildingAnchors=new Map();
const anchorBranches=new WeakMap(),isolationVisibility=new Map();
const nativeMaterials=new Map();
const proceduralCache=new Map();
function bindRecipe(m,recipe){
 if(!recipe||!recipe.pattern||recipe.pattern==='none')return m;
 const key=JSON.stringify([recipe,m.color.getHexString()]);
 if(!proceduralCache.has(key)){
  const slot='procedural-'+proceduralCache.size; textures[slot]=proceduralSurface(THREE,recipe,m.color);
  proceduralCache.set(key,slot);
 }
 bindTexture(m,proceduralCache.get(key));m.color.set(0xffffff);return m;
}
// Surface defaults describe assumed infrastructure, never a user style palette.
const surfaceDefaults={road:[0x6b6b65,.96,0],pavement:[0xccccbf,.9,0],grass:[0x658348,.95,0],foliage:[0x32603b,.9,0],trunk:[0x655344,.95,0],metal:[0x7c8184,.5,.65],ground:[0xc2c1b2,.95,0],marking:[0xe6e4d4,.8,0]};
function bindTexture(m,slot){
  const maps=textures[slot];if(!maps)return m;
  // Painted plaster gets its albedo from the object's evidenced paint color.
  // Do not multiply it by an unrelated scan's stains/yellowing. Keep surface
  // normals/roughness. Natural tile/stone retain their full-color albedo maps.
  const intrinsicPaint=m.userData.useAlbedoMap===false||(slot==='plaster'&&m.userData.useAlbedoMap!==true);
  m.map=intrinsicPaint?null:(maps.color||null);m.normalMap=maps.normal||null;m.roughnessMap=maps.roughness||null;
  if(m.normalMap)m.normalScale.setScalar(.65);
  // World-metre projection handles scaled boxes and every instance consistently.
  const rotation=Number.isFinite(m.userData.textureRotation)?m.userData.textureRotation:0,c=Math.cos(rotation).toFixed(10),s=Math.sin(rotation).toFixed(10);
  m.onBeforeCompile=shader=>{
    shader.vertexShader=shader.vertexShader.replace('#include <uv_vertex>',`#include <uv_vertex>
      vec4 metricP=vec4(position,1.0);vec3 metricN=normal;
      #ifdef USE_INSTANCING
        metricP=instanceMatrix*metricP;metricN=mat3(instanceMatrix)*metricN;
      #endif
      metricP=modelMatrix*metricP;metricN=abs(normalize(mat3(modelMatrix)*metricN));
      vec2 metricUV=metricN.y>metricN.x && metricN.y>metricN.z?metricP.xz:(metricN.x>metricN.z?metricP.zy:metricP.xy);
      metricUV=vec2(${c}*metricUV.x+${s}*metricUV.y,-${s}*metricUV.x+${c}*metricUV.y);
      #ifdef USE_MAP
        vMapUv=(mapTransform*vec3(metricUV,1.0)).xy;
      #endif
      #ifdef USE_NORMALMAP
        vNormalMapUv=(normalMapTransform*vec3(metricUV,1.0)).xy;
      #endif
      #ifdef USE_ROUGHNESSMAP
        vRoughnessMapUv=(roughnessMapTransform*vec3(metricUV,1.0)).xy;
      #endif`);
  };
  m.customProgramCacheKey=()=> 'world-metric-surface-v3:'+slot+':'+rotation;return m;
}
function material(role){
  if(materials[role])return materials[role];
  const fallback=surfaceDefaults[role]||[0xbfc0b8,.85,0],recipe=city?.material_recipes?.[role];
  const [color,roughness,metalness]=recipe?[recipe.color??fallback[0],recipe.roughness??fallback[1],recipe.metalness??fallback[2]]:fallback;
  const m=new THREE.MeshStandardMaterial({name:role,color,roughness,metalness});
  if(recipe)bindRecipe(m,recipe);else {bindTexture(m,role);if(m.map)m.color.setScalar(city?.surface_settings?.[role]?.albedo_multiplier??1);}materials[role]=m;return m;
}
function preserveMaterial(original){
  if(nativeMaterials.has(original.uuid))return nativeMaterials.get(original.uuid);
  const m=original.clone();if(m.userData?.surfaceRecipe)bindRecipe(m,m.userData.surfaceRecipe);else bindTexture(m,m.userData?.textureRole);nativeMaterials.set(original.uuid,m);return m;
}
function batchStaticMeshes(content){
  content.updateMatrixWorld(true);
  for(const object of content.children){
    const batches=new Map(),inverse=new THREE.Matrix4().copy(object.matrixWorld).invert();
    object.traverse(o=>{if(o.isMesh&&!o.isInstancedMesh&&!Array.isArray(o.material)){
      const key=o.geometry.uuid+'|'+o.material.uuid;const list=batches.get(key)||[];list.push(o);batches.set(key,list);
    }});
    for(const list of batches.values()){
      if(list.length<2)continue;
      const merged=new THREE.InstancedMesh(list[0].geometry,list[0].material,list.length);
      list.forEach((o,i)=>{merged.setMatrixAt(i,new THREE.Matrix4().multiplyMatrices(inverse,o.matrixWorld));o.removeFromParent();});
      merged.instanceMatrix.needsUpdate=true;merged.castShadow=true;merged.receiveShadow=true;
      merged.computeBoundingBox();merged.computeBoundingSphere();object.add(merged);
    }
  }
}
function shapeGeometry(poly,height=0){
  function points(r){return r.map(([x,z])=>new THREE.Vector2(x,-z));}
  let outer=points(poly.outer);if(!THREE.ShapeUtils.isClockWise(outer))outer.reverse();
  const shape=new THREE.Shape(outer);
  for(const ring of poly.holes||[]){let pts=points(ring);if(THREE.ShapeUtils.isClockWise(pts))pts.reverse();shape.holes.push(new THREE.Path(pts));}
  const geo=height?new THREE.ExtrudeGeometry(shape,{depth:height,bevelEnabled:false}):new THREE.ShapeGeometry(shape);
  geo.rotateX(-Math.PI/2);
  const pos=geo.getAttribute('position'),uv=new Float32Array(pos.count*2);
  for(let i=0;i<pos.count;i++){uv[i*2]=pos.getX(i);uv[i*2+1]=pos.getZ(i);}
  geo.setAttribute('uv',new THREE.BufferAttribute(uv,2));return geo;
}
function addSurface(poly,role,y){const mesh=new THREE.Mesh(shapeGeometry(poly),material(role));mesh.position.y=y;mesh.receiveShadow=true;groups.infrastructure.add(mesh);return mesh;}
function group(name){const g=new THREE.Group();g.name=name;root.add(g);groups[name]=g;return g;}
function instances(geometry,role,records){
  const mesh=new THREE.InstancedMesh(geometry,material(role),records.length),d=new THREE.Object3D(),color=new THREE.Color();
  records.forEach((r,i)=>{d.position.set(...r.position);d.scale.set(...(r.scale||[1,1,1]));if(r.quaternion)d.quaternion.fromArray(r.quaternion);else d.rotation.set(0,r.rotation||0,0);d.updateMatrix();mesh.setMatrixAt(i,d.matrix);
    color.setScalar(r.shade||1);mesh.setColorAt(i,color);});
  mesh.instanceMatrix.needsUpdate=true;mesh.castShadow=true;mesh.receiveShadow=true;mesh.computeBoundingBox();mesh.computeBoundingSphere();return mesh;
}
let vegetationVariation=0;
function buildVegetation(){
  const batches=treeBatches(city.trees.map(t=>({...t,seed:vegetationVariation===0?(t.seed??t.id):(t.seed??t.id)+':'+vegetationVariation})),{clusterDetail:city.tree_cluster_detail||1});window.cityTreeInstances=batches.metadata;
  groups.vegetation.add(instances(new THREE.IcosahedronGeometry(1,city.tree_cluster_detail>1?1:2),'foliage',batches.crowns));
  groups.vegetation.add(instances(new THREE.CylinderGeometry(.6,1,2,8),'trunk',batches.wood));
  const data=frondMeshData(),frond=new THREE.BufferGeometry();frond.setAttribute('position',new THREE.Float32BufferAttribute(data.positions,3));frond.setIndex(data.indices);frond.computeVertexNormals();
  groups.vegetation.add(instances(frond,'foliage',batches.fronds));
  const poles=[],arms=[],heads=[];
  for(const l of city.lamps){const [x,z]=l.position;poles.push({position:[x,3.8,z],scale:[.08,3.8,.08]});
    const a=l.heading||0;arms.push({position:[x+Math.cos(a)*.65,7.5,z+Math.sin(a)*.65],scale:[.75,.07,.07],rotation:-a});heads.push({position:[x+Math.cos(a)*1.3,7.45,z+Math.sin(a)*1.3],scale:[.4,.10,.23],rotation:-a});}
  groups.furniture.add(instances(new THREE.CylinderGeometry(1,1,2,6),'metal',poles));
  groups.furniture.add(instances(new THREE.BoxGeometry(2,2,2),'metal',arms));
  groups.furniture.add(instances(new THREE.BoxGeometry(2,2,2),'metal',heads));
}
window.reseedCityTrees=value=>{
 if(!Number.isSafeInteger(value))throw Error('TREE_VARIATION_MUST_BE_INTEGER');
 vegetationVariation=value;
 for(const name of ['vegetation','furniture']){for(const mesh of groups[name].children){mesh.geometry?.dispose();mesh.dispose?.();}groups[name].clear();}
 buildVegetation();renderer.shadowMap.needsUpdate=true;renderer.render(scene,camera);
};
function markings(){
  const records=[];
  for(const road of city.roads){
    if(!road.markings_verified&&!road.markings_inferred)continue; // Inferred illustrative markings are explicitly labelled in city data.
    let chain=road.phase_m;
    for(let i=1;i<road.points.length;i++){
      const a=new THREE.Vector2(...road.points[i-1]),b=new THREE.Vector2(...road.points[i]);const len=a.distanceTo(b),dir=b.clone().sub(a).normalize();
      for(let d=(8-(chain%8))%8;d<len;d+=8){const p=a.clone().addScaledVector(dir,d);
        if(p.x<city.bounds[0]||p.x>city.bounds[2]||p.y<city.bounds[1]||p.y>city.bounds[3])continue;
        records.push({position:[p.x,.12,p.y],scale:[.065,.004,1.5],rotation:Math.atan2(dir.x,dir.y)});}
      chain+=len;
    }
  }
  groups.infrastructure.add(instances(new THREE.BoxGeometry(2,2,2),'marking',records));
}
window.initCity=async({data,buildings,assets,profile,presentation,neutral_presentation,render_probe})=>{
  window.cityPresentation=presentation;window.cityNeutralPresentation=neutral_presentation;
  city=data;buildingScene=buildings;style=profile;
  const loader=new THREE.TextureLoader();
  for(const [role,entry] of Object.entries(assets)){
    textures[role]={};
    for(const [semantic,uri] of Object.entries(entry.maps)){
      if(!uri.startsWith('data:image/jpeg;base64,'))throw Error('UNTRUSTED_TEXTURE_URI');
      const t=await loader.loadAsync(uri);t.wrapS=t.wrapT=THREE.RepeatWrapping;t.repeat.setScalar(1/entry.physical_tile_m);
      t.colorSpace=semantic==='color'?THREE.SRGBColorSpace:THREE.NoColorSpace;t.anisotropy=Math.min(8,renderer.capabilities.getMaxAnisotropy());textures[role][semantic]=t;
    }
  }
  root=new THREE.Group();root.name='Procedural urban block';scene.add(root);
  group('buildings');group('infrastructure');group('vegetation');group('furniture');group('grid');
  if(buildings.images?.length||buildings.textures?.length)throw Error('GENERATED_TEXTURE_PAYLOAD');
  const content=new THREE.ObjectLoader().parse(buildings);
  content.traverse(o=>{if(o.isMesh){o.material=Array.isArray(o.material)?o.material.map(preserveMaterial):preserveMaterial(o.material);o.castShadow=true;o.receiveShadow=true;}});
  batchStaticMeshes(content);
  content.traverse(o=>{if(o.userData?.objectId)buildingAnchors.set(o.userData.objectId,o);});
  const markAnchors=o=>{let found=!!o.userData?.objectId;for(const child of o.children)found=markAnchors(child)||found;anchorBranches.set(o,found);return found;};markAnchors(content);
  groups.buildings.add(content);
  const [xmin,zmin,xmax,zmax]=city.bounds;const ground=new THREE.Mesh(new THREE.BoxGeometry(xmax-xmin+4,1,zmax-zmin+4),material('ground'));ground.position.set((xmin+xmax)/2,-.58,(zmin+zmax)/2);ground.receiveShadow=true;groups.infrastructure.add(ground);
  for(const p of city.surfaces.road)addSurface(p,'road',.025);
  for(const p of city.surfaces.pavement)addSurface(p,'pavement',.055);
  if(city.context_curbs){
    const records=[];
    for(const p of city.surfaces.pavement)for(let i=0;i<p.outer.length;i++){
      const a=p.outer[i],b=p.outer[(i+1)%p.outer.length],dx=b[0]-a[0],dz=b[1]-a[1],length=Math.hypot(dx,dz);
      if(length<.2)continue;
      records.push({position:[(a[0]+b[0])/2,.12,(a[1]+b[1])/2],scale:[length/2,.08,.10],rotation:-Math.atan2(dz,dx)});
    }
    groups.infrastructure.add(instances(new THREE.BoxGeometry(2,2,2),'pavement',records));
  }
  for(const p of city.parks)addSurface(p,'grass',.075);
  for(const p of city.observed_markings||[])addSurface(p,'marking',.045);
  markings();buildVegetation();
  const gridMaterial=new THREE.LineBasicMaterial({color:0xf9ab45,transparent:true,opacity:.9});
  for(const x of [...new Set(city.cells.flatMap(c=>[c.bounds[0],c.bounds[2]]))]){const g=new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(x,.25,zmin),new THREE.Vector3(x,.25,zmax)]);groups.grid.add(new THREE.Line(g,gridMaterial));}
  for(const z of [...new Set(city.cells.flatMap(c=>[c.bounds[1],c.bounds[3]]))]){const g=new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(xmin,.25,z),new THREE.Vector3(xmax,.25,z)]);groups.grid.add(new THREE.Line(g,gridMaterial));}
  const pmrem=new THREE.PMREMGenerator(renderer);const room=new RoomEnvironment();scene.environment=pmrem.fromScene(room,.04).texture;room.dispose();pmrem.dispose();
  groups.grid.visible=false;window.setCityStyle(profile);window.setCityView('overview');if(render_probe)window.probeCityLighting(render_probe);window.__CITY_READY__=true;
  if(window.__CITY_INTERACTIVE__)renderer.setAnimationLoop(()=>{controls.update();renderer.render(scene,camera);});
};
window.setCityStyle=(profile,inspection=false)=>{
  // Artistic intent does not mutate any material or texture.
  style=profile;const settings=inspection?window.cityNeutralPresentation:window.cityPresentation;
  const p=settings||{exposure:1.05,sun_intensity:3,ambient_intensity:1.7,shadow_softness:2.5,sun_azimuth_deg:-40,sun_elevation_deg:55};
  scene.background=new THREE.Color(0xe5e9ec);hemi.intensity=p.ambient_intensity;sun.intensity=p.sun_intensity;
  const az=THREE.MathUtils.degToRad(p.sun_azimuth_deg),el=THREE.MathUtils.degToRad(p.sun_elevation_deg);
  sun.position.set(Math.sin(az)*Math.cos(el)*550,Math.sin(el)*550,Math.cos(az)*Math.cos(el)*550);
  sun.shadow.radius=p.shadow_softness;renderer.toneMappingExposure=p.exposure;renderer.shadowMap.needsUpdate=true;sun.shadow.needsUpdate=true;renderer.render(scene,camera);
};
window.cityMaterialFingerprint=()=>{
 const records=[];root.traverse(o=>{if(o.isMesh){for(const m of Array.isArray(o.material)?o.material:[o.material])records.push([m.name,m.color?.getHexString(),m.roughness,m.metalness,m.map?.uuid,m.normalMap?.uuid,m.roughnessMap?.uuid,m.userData]);}});return JSON.stringify(records);
};
window.citySurfaceBindings=()=>{
 const values=new Map();root.traverse(o=>{if(o.isMesh){for(const m of Array.isArray(o.material)?o.material:[o.material])values.set(m.uuid,{name:m.name,color:m.color?.getHexString(),role:m.userData?.textureRole||null,albedo_map:!!m.map,normal_map:!!m.normalMap,roughness_map:!!m.roughnessMap});}});return [...values.values()];
};
window.cityRayHits=(x,y)=>{
 const ray=new THREE.Raycaster();ray.setFromCamera(new THREE.Vector2(x,y),camera);
 return ray.intersectObject(root,true).filter(h=>{for(let o=h.object;o;o=o.parent)if(!o.visible)return false;return true;}).slice(0,6).map(h=>({material:h.object.material?.name,distance:h.distance,point:h.point.toArray(),instance:h.instanceId}));
};
let selectedObject=null;
window.selectCityObject=(id,isolate=false,frame=true)=>{
 if(!buildingAnchors.has(id))throw Error('UNKNOWN_CITY_OBJECT');
 selectedObject=id;
 const apply=o=>{
  if(!isolationVisibility.has(o))isolationVisibility.set(o,o.visible);
  if(o.userData?.objectId){o.visible=!isolate||o.userData.objectId===id;return;}
  if(!anchorBranches.get(o)){o.visible=!isolate;return;}
  o.visible=true;for(const child of o.children)apply(child);
 };apply(groups.buildings.children[0]);
 groups.vegetation.visible=!isolate;groups.furniture.visible=!isolate;renderer.shadowMap.needsUpdate=true;sun.shadow.needsUpdate=true;if(frame)window.setCityView('landmark');
};
window.resetCityObjects=()=>{selectedObject=null;for(const [o,visible] of isolationVisibility)o.visible=visible;isolationVisibility.clear();groups.infrastructure.visible=true;groups.vegetation.visible=true;groups.furniture.visible=true;renderer.shadowMap.needsUpdate=true;sun.shadow.needsUpdate=true;};
window.cityVisibleObjectIds=()=>[...buildingAnchors].filter(([,o])=>{for(let p=o;p;p=p.parent)if(!p.visible)return false;return true;}).map(([id])=>id).sort();
window.setCityView=name=>{
  if(name==='street'){
    const route=city.roads.filter(r=>r.walk&&!r.area).sort((a,b)=>b.length-a.length)[0]||city.roads[0]; if(!route){window.setCityView('detail');return;}
    const i=Math.max(0,Math.floor(route.points.length/2)-1),a=route.points[i],b=route.points[Math.min(i+1,route.points.length-1)];
    const dx=b[0]-a[0],dz=b[1]-a[1],n=Math.hypot(dx,dz)||1;
    camera=new THREE.PerspectiveCamera(55,W/H,.1,2500);controls.object=camera;
    camera.position.set((a[0]+b[0])/2,2.1,(a[1]+b[1])/2);
    controls.target.set(camera.position.x+dx/n*65,8,camera.position.z+dz/n*65);
    if(city.street_camera){camera.position.set(...city.street_camera.position);controls.target.set(...city.street_camera.target);}
    camera.lookAt(controls.target);controls.update();renderer.render(scene,camera);return;
  }
  if(!camera.isOrthographicCamera){camera=new THREE.OrthographicCamera(-320,320,240,-240,.1,2500);controls.object=camera;}
  if(name==='landmark'){
    const b=city.buildings.find(b=>b.id===selectedObject)||city.buildings.find(b=>city.observed_objects?.includes(b.id))||city.buildings[0];
    const object=buildingAnchors.get(b.id);
    const bounds=object?new THREE.Box3().setFromObject(object):null;
    const center=bounds&&!bounds.isEmpty()?bounds.getCenter(new THREE.Vector3()):new THREE.Vector3(b.center[0],b.height*.5,b.center[1]);
    const normal=b.front_normal_hint||[0,1],length=Math.hypot(...normal)||1,nx=normal[0]/length,nz=normal[1]/length;
    const size=bounds&&!bounds.isEmpty()?bounds.getSize(new THREE.Vector3()):new THREE.Vector3(20,b.height,20);
    const projectedWidth=Math.abs(nz)*size.x+Math.abs(nx)*size.z;
    const span=Math.max(size.y*1.4,projectedWidth*H/W*1.3,15);
    camera.position.set(center.x+nx*span*2,center.y+size.y*.12,center.z+nz*span*2);controls.target.copy(center);
    camera.left=-span*W/H/2;camera.right=span*W/H/2;camera.top=span/2;camera.bottom=-span/2;camera.updateProjectionMatrix();camera.lookAt(controls.target);controls.update();renderer.render(scene,camera);return;
  }
  const views={overview:{position:[-560,490,80],target:[0,35,0],span:690},north:{position:[430,440,-500],target:[0,35,0],span:690},
    grid:{position:[0,800,.01],target:[0,0,0],span:440},street:{position:[135,45,205],target:[15,25,10],span:220},
    detail:{position:[-120,110,130],target:[-30,20,0],span:195},seam:{position:[0,230,260],target:[0,0,0],span:190}};
  const v={...(views[name]||views.overview)};
  if(city.scene_mode && ['overview','north','grid'].includes(name)){
    const box=new THREE.Box3().setFromObject(groups.buildings),center=box.getCenter(new THREE.Vector3()),size=box.getSize(new THREE.Vector3());
    const span=Math.max(Math.hypot(size.x,size.z)*1.25,size.y*1.85,80),direction=new THREE.Vector3(...v.position).normalize();
    if(name==='grid')center.y=0;
    camera.position.copy(center).addScaledVector(direction,span*3);controls.target.copy(center);
    camera.left=-span/2;camera.right=span/2;camera.top=span*H/W/2;camera.bottom=-camera.top;camera.updateProjectionMatrix();camera.lookAt(center);controls.update();renderer.render(scene,camera);return;
  }
  const factor=(city.bounds[2]-city.bounds[0])/400;v.position=v.position.map(n=>n*factor);v.target=v.target.map(n=>n*factor);v.span*=factor;camera.position.set(...v.position);controls.target.set(...v.target);
  camera.left=-v.span/2;camera.right=v.span/2;camera.top=v.span*H/W/2;camera.bottom=-camera.top;camera.updateProjectionMatrix();
  camera.lookAt(controls.target);controls.update();renderer.render(scene,camera);
};
window.showCityGrid=value=>{groups.grid.visible=value;renderer.render(scene,camera);};
window.cityStats=()=>{
  renderer.render(scene,camera);return {draw_calls:renderer.info.render.calls,triangles:renderer.info.render.triangles,
    geometries:renderer.info.memory.geometries,textures:renderer.info.memory.textures,renderer:renderer.getContext().getParameter(renderer.getContext().RENDERER),width:W,height:H};
};
window.benchmarkCity=async(frames=24)=>{
  if(!Number.isInteger(frames)||frames<6||frames>120)throw Error('BENCHMARK_FRAME_LIMIT');
  const samples=[];
  for(let i=0;i<frames;i++){await new Promise(requestAnimationFrame);const t=performance.now();renderer.render(scene,camera);samples.push(performance.now()-t);}
  samples.sort((a,b)=>a-b);return {samples:frames,cpu_render_submission_ms_median:samples[Math.floor(frames/2)],cpu_render_submission_ms_p95:samples[Math.min(frames-1,Math.floor(frames*.95))],
    caveat:'CPU submission timings only, not GPU completion or guaranteed display FPS',...window.cityStats()};
};
window.toggleCityLayer=(name,value)=>{if(groups[name]){groups[name].visible=value;renderer.shadowMap.needsUpdate=true;sun.shadow.needsUpdate=true;}};
window.cityGeometryFingerprint=()=>{
  let hash=2166136261,count=0;
  const add=n=>{hash=Math.imul(hash^(Math.round(n*10000)|0),16777619)>>>0;};
  root.updateMatrixWorld(true);
  root.traverse(o=>{if(o.isMesh){count++;for(const v of o.matrixWorld.elements)add(v);
    const p=o.geometry.getAttribute('position');for(let i=0;i<p.array.length;i++)add(p.array[i]);
    if(o.isInstancedMesh){add(o.count);for(const v of o.instanceMatrix.array)add(v);}
  }});return {hash:hash.toString(16),mesh_objects:count};
};

window.pauseCityAnimation=()=>renderer.setAnimationLoop(null);
window.probeCityShadowCaching=enabled=>{
 if(typeof enabled!=='boolean')throw Error('SHADOW_CACHE_OPTION');
 renderer.shadowMap.autoUpdate=!enabled;renderer.shadowMap.needsUpdate=true;sun.shadow.needsUpdate=true;renderer.render(scene,camera);
 return {enabled:!renderer.shadowMap.autoUpdate};
};
window.setCityEvidenceCamera=p=>{
 if(![p.position,p.direction,p.up].every(v=>Array.isArray(v)&&v.length===3&&v.every(Number.isFinite))||!(p.fov>0&&p.fov<170)||Math.abs(p.aspect-W/H)>.001)throw Error('EVIDENCE_CAMERA_INVALID');
 camera=new THREE.PerspectiveCamera(p.fov,p.aspect,.1,10000);
 camera.position.fromArray(p.position);camera.up.fromArray(p.up).normalize();
 controls.object=camera;controls.target.copy(camera.position).add(new THREE.Vector3().fromArray(p.direction).normalize().multiplyScalar(100));
 camera.lookAt(controls.target);controls.update();renderer.render(scene,camera);
};

// Controlled research probe. Production defaults remain unchanged.
window.probeCityLighting=options=>{
 const limits={ambient:[0,3],environment:[0,3],sun:[0,6],exposure:[.3,2],normalBias:[0,.5],bias:[-.005,.005]};
 for(const [key,[lo,hi]] of Object.entries(limits))if(options[key]!==undefined && (!Number.isFinite(options[key])||options[key]<lo||options[key]>hi))throw Error('LIGHT_PROBE_LIMIT:'+key);
 if(options.ambient!==undefined)hemi.intensity=options.ambient;
 if(options.environment!==undefined)scene.environmentIntensity=options.environment;
 if(options.sun!==undefined)sun.intensity=options.sun;
 if(options.exposure!==undefined)renderer.toneMappingExposure=options.exposure;
 if(options.normalBias!==undefined)sun.shadow.normalBias=options.normalBias;
 if(options.bias!==undefined)sun.shadow.bias=options.bias;
 if(options.fitShadow){
  const bounds=new THREE.Box3().setFromObject(root),center=bounds.getCenter(new THREE.Vector3());
  sun.target.position.copy(center);sun.target.updateMatrixWorld(true);sun.updateMatrixWorld(true);sun.shadow.updateMatrices(sun);
  const projected=new THREE.Box3();
  for(const x of [bounds.min.x,bounds.max.x])for(const y of [bounds.min.y,bounds.max.y])for(const z of [bounds.min.z,bounds.max.z])projected.expandByPoint(new THREE.Vector3(x,y,z).applyMatrix4(sun.shadow.camera.matrixWorldInverse));
  Object.assign(sun.shadow.camera,{left:projected.min.x-5,right:projected.max.x+5,bottom:projected.min.y-5,top:projected.max.y+5,near:Math.max(.1,-projected.max.z-10),far:-projected.min.z+10});sun.shadow.camera.updateProjectionMatrix();
 }
 if(options.shadowSize!==undefined){
  if(![1024,2048,4096].includes(options.shadowSize))throw Error('LIGHT_PROBE_SHADOW_SIZE');
  sun.shadow.map?.dispose();sun.shadow.map=null;sun.shadow.mapSize.setScalar(options.shadowSize);
 }
 sun.shadow.needsUpdate=true;renderer.shadowMap.needsUpdate=true;renderer.render(scene,camera);
 return {ambient:hemi.intensity,environment:scene.environmentIntensity,sun:sun.intensity,exposure:renderer.toneMappingExposure,normalBias:sun.shadow.normalBias,bias:sun.shadow.bias,shadowSize:sun.shadow.mapSize.x,shadowWidth:sun.shadow.camera.right-sun.shadow.camera.left,shadowTexelM:(sun.shadow.camera.right-sun.shadow.camera.left)/sun.shadow.mapSize.x};
};
