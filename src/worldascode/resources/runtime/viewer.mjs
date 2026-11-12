import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {RoomEnvironment} from 'three/addons/environments/RoomEnvironment.js';
import {applyState,semanticProbes,tick} from './semantic.mjs';

export function monitorAssets(){
  const status={pending:0,failed:[]},manager=THREE.DefaultLoadingManager;
  const start=manager.itemStart.bind(manager),end=manager.itemEnd.bind(manager),error=manager.itemError.bind(manager);
  manager.itemStart=url=>{status.pending++;start(url);};manager.itemEnd=url=>{status.pending--;end(url);};manager.itemError=url=>{status.failed.push(url);error(url);};
  window.worldscaleLoading=status;
}

export function mount(root,config={}) {
  const scene=new THREE.Scene();scene.background=new THREE.Color('#ccd6dc');scene.add(root);
  const width=config.width??1100,height=config.height??850;
  const renderer=new THREE.WebGLRenderer({antialias:true,preserveDrawingBuffer:true});renderer.setSize(width,height);renderer.setPixelRatio(1);
  renderer.shadowMap.enabled=true;renderer.shadowMap.type=THREE.PCFSoftShadowMap;renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.ACESFilmicToneMapping;
  // Camera-only changes do not alter the light-space shadow of static assets.
  // Explicit state/geometry changes invalidate it below.
  renderer.shadowMap.autoUpdate=false;renderer.shadowMap.needsUpdate=true;
  const pmrem=new THREE.PMREMGenerator(renderer),room=new RoomEnvironment();scene.environment=pmrem.fromScene(room,.04,.1,100,{size:64}).texture;scene.environmentIntensity=.45;room.dispose();pmrem.dispose();
  document.getElementById('viewport').append(renderer.domElement);
  const bounds=new THREE.Box3().setFromObject(root),size=bounds.getSize(new THREE.Vector3()),centre=bounds.getCenter(new THREE.Vector3());
  const radius=Math.max(size.x,size.y,size.z,1);
  const camera=new THREE.PerspectiveCamera(38,width/height,Math.max(radius/2000,.01),radius*100);
  const controls=new OrbitControls(camera,renderer.domElement);controls.target.copy(centre);
  const sky=new THREE.HemisphereLight(0xd6e5f2,0x777165,2);scene.add(sky);
  const sun=new THREE.DirectionalLight(0xfff0d8,3);sun.position.copy(centre).add(new THREE.Vector3(radius,radius*1.7,radius*.8));sun.castShadow=true;
  sun.shadow.mapSize.set(2048,2048);sun.shadow.camera.left=-radius;sun.shadow.camera.right=radius;sun.shadow.camera.top=radius;sun.shadow.camera.bottom=-radius;sun.shadow.camera.far=radius*8;sun.shadow.normalBias=.025;sun.target.position.copy(centre);scene.add(sun,sun.target);
  const floor=new THREE.Mesh(new THREE.PlaneGeometry(radius*5,radius*5),new THREE.MeshStandardMaterial({color:0xa5aaa5,roughness:.95}));floor.rotation.x=-Math.PI/2;floor.position.y=bounds.min.y-.03;floor.receiveShadow=true;scene.add(floor);
  if(config.isolated_stage){floor.visible=false;scene.background.set('#000000');}
  function draw(){controls.update();renderer.render(scene,camera);}
  // Exact evidence camera in the asset's metric frame: no search, no reframing.
  function pose(c){renderer.setSize(c.render_width,c.render_height);camera.fov=c.fov_vertical_deg;camera.aspect=c.render_width/c.render_height;camera.near=.5;camera.far=20000;camera.updateProjectionMatrix();
    camera.position.set(...c.position);controls.target.set(...c.target);camera.lookAt(controls.target);draw();}
  function view(azimuth=35,elevation=28,scale=1) {if(camera.fov!==38||renderer.domElement.width!==width){renderer.setSize(width,height);camera.fov=38;camera.aspect=width/height;camera.near=Math.max(radius/2000,.01);camera.far=radius*100;camera.updateProjectionMatrix();controls.target.copy(centre);}
    const a=azimuth*Math.PI/180,e=elevation*Math.PI/180;let distance=radius*1.9;const axis=new THREE.Vector3(Math.sin(a)*Math.cos(e),Math.sin(e),Math.cos(a)*Math.cos(e));
    for(let iteration=0;iteration<(config.isolated_stage?4:1);iteration++){
      camera.position.copy(centre).addScaledVector(axis,distance);camera.lookAt(centre);camera.updateMatrixWorld(true);
      if(config.isolated_stage){let extent=0;for(const x of [bounds.min.x,bounds.max.x])for(const y of [bounds.min.y,bounds.max.y])for(const z of [bounds.min.z,bounds.max.z]){const p=new THREE.Vector3(x,y,z).project(camera);extent=Math.max(extent,Math.abs(p.x),Math.abs(p.y));}distance*=Math.max(.65,Math.min(1.5,extent/.9));}
    }
    camera.position.copy(centre).addScaledVector(axis,distance*scale);camera.lookAt(centre);draw();
  }
  // A design may set its own daylight look; night and the isolated black stage are unchanged.
  const look={background:'#ccd6dc',ground:'#a5aaa5',sky:2,sun:3,exposure:1,...(root.userData.look??{})};
  renderer.toneMappingExposure=look.exposure;floor.material.color.set(look.ground);
  function state(v){const s=applyState(root,v);renderer.shadowMap.autoUpdate=Number(s.wind??0)>0;renderer.shadowMap.needsUpdate=true;sky.intensity=s.night?.18:look.sky;sun.intensity=s.night?.12:look.sun;scene.environmentIntensity=s.night?.02:.45;scene.background.set(config.isolated_stage?'#000000':(s.night?'#101923':look.background));draw();return s;}
  function lookdev(mode){renderer.shadowMap.needsUpdate=true;if(mode==='grazing'){sky.intensity=.35;sun.intensity=4;sun.position.copy(centre).add(new THREE.Vector3(radius*1.5,radius*.25,radius*.1));}else{sky.intensity=look.sky;sun.intensity=look.sun;sun.position.copy(centre).add(new THREE.Vector3(radius,radius*1.7,radius*.8));}draw();}
  function manifest(){let triangles=0,meshCount=0,geometryBytes=0;const parts=[],geometries=new Set(),materials=new Set();root.traverse(o=>{if(o.isMesh){meshCount++;const g=o.geometry;const positionCount=g?.attributes?.position?.count??0;triangles+=(g?.index?.count??positionCount)/3*(o.isInstancedMesh?o.count:1);for(const m of Array.isArray(o.material)?o.material:[o.material])materials.add(m);if(g&&!geometries.has(g)){geometries.add(g);geometryBytes+=(g.index?.array?.byteLength??0)+Object.values(g.attributes).reduce((n,a)=>n+(a.array?.byteLength??0),0);}parts.push({name:o.name,geometry:g?.uuid??null,position:o.getWorldPosition(new THREE.Vector3()).toArray()});}});return {triangles,parts,bounds:{min:bounds.min.toArray(),max:bounds.max.toArray()},probes:semanticProbes(root),performance:{meshCount,uniqueGeometries:geometries.size,uniqueMaterials:materials.size,geometryBytes,drawCalls:renderer.info.render.calls,textures:renderer.info.memory.textures,note:'One rendered frame; geometryBytes counts CPU attribute buffers, not total GPU memory or city throughput.'},profile:{three:THREE.REVISION,toneMapping:'ACESFilmic',exposure:renderer.toneMappingExposure,colorSpace:renderer.outputColorSpace,environment:'RoomEnvironment',environmentIntensity:scene.environmentIntensity}};}
  const partNodes=(root.userData.components??[]).map(v=>[v.instance+'/'+v.component.id,v.pivot]);
  const collectParts=(asset,prefix)=>asset.traverse(o=>{if(o.isMesh&&o.name&&!partNodes.some(([,node])=>node===o))partNodes.push([prefix+o.name,o]);});
  for(const asset of root.userData.factoryAssets??[])collectParts(asset,(asset.userData.instanceId??asset.name)+'/');
  if(!partNodes.length)collectParts(root,'');
  const originals=partNodes.map(([id,o])=>({id,o,local:o.position.clone(),world:o.getWorldPosition(new THREE.Vector3())}));
  function explode(amount=0){
    renderer.shadowMap.needsUpdate=true;
    for(const p of originals)p.o.position.copy(p.local);root.updateMatrixWorld(true);
    if(amount)for(const p of originals){const desired=p.world.clone().sub(centre).multiplyScalar(1+amount).add(centre);p.o.position.copy(p.o.parent.worldToLocal(desired));p.o.updateMatrixWorld(true);}draw();
  }
  function pick(x,y){const rect=renderer.domElement.getBoundingClientRect(),ray=new THREE.Raycaster();ray.setFromCamera(new THREE.Vector2((x-rect.left)/rect.width*2-1,-(y-rect.top)/rect.height*2+1),camera);const hit=ray.intersectObject(root,true)[0];if(!hit)return null;const owner=hit.object.userData.instanceOwners?.[hit.instanceId];if(owner)return owner.asset+'/'+owner.component;let node=hit.object;while(node&&node!==root){const p=partNodes.find(([,o])=>o===node);if(p)return p[0];node=node.parent;}return null;}
  renderer.domElement.addEventListener('click',e=>{document.getElementById('selection').textContent=pick(e.clientX,e.clientY)??'No part';});
  function geometry(){root.updateMatrixWorld(true);const meshes=[],measured={};
    for(const [id,node] of partNodes)measured[id]=node.getWorldPosition(new THREE.Vector3()).toArray();
    root.traverse(o=>{if(!o.isMesh)return;const g=o.geometry,p=g.attributes.position,n=g.attributes.normal;if(!p?.count)return;const exportMatrix=o.isInstancedMesh?new THREE.Matrix4():o.matrixWorld,normalMatrix=new THREE.Matrix3().getNormalMatrix(exportMatrix),vertices=[],normals=[];
      for(let i=0;i<p.count;i++){vertices.push(new THREE.Vector3().fromBufferAttribute(p,i).applyMatrix4(exportMatrix).toArray());if(n)normals.push(new THREE.Vector3().fromBufferAttribute(n,i).applyMatrix3(normalMatrix).normalize().toArray());}
      const instances=[];if(o.isInstancedMesh){const matrix=new THREE.Matrix4();for(let i=0;i<o.count;i++){o.getMatrixAt(i,matrix);instances.push({matrix:new THREE.Matrix4().multiplyMatrices(o.matrixWorld,matrix).toArray(),owner:o.userData.instanceOwners?.[i]??null});}}
      meshes.push({id:o.name,vertices,normals,indices:g.index?Array.from(g.index.array):Array.from({length:p.count},(_,i)=>i),instances,coordinateFrame:o.isInstancedMesh?'local vertices with per-instance world matrix':'world'});
    });
    const parts=partNodes.map(([id,node])=>{let triangles=0;node.traverse(o=>{if(o.isMesh)triangles+=(o.geometry.index?.count??o.geometry.attributes.position?.count??0)/3;});return {name:id,kind:'part',triangles};}).filter(p=>p.triangles>0);
    return {meshes,measured,parts:{model:root.name,parts,unnamedMeshes:meshes.filter(m=>!m.id).length,integralMeshes:meshes.length}};
  }
  const white=new THREE.MeshBasicMaterial({color:0xffffff});
  const clayMaterial=new THREE.MeshStandardMaterial({color:0xaaaaaa,roughness:.85});
  function clay(enabled){scene.overrideMaterial=enabled?clayMaterial:null;draw();}
  function silhouette(){scene.overrideMaterial=white;const oldFloor=floor.visible;floor.visible=false;const oldBackground=scene.background.clone();scene.background.set('#000000');draw();const data=renderer.domElement.toDataURL('image/png');scene.overrideMaterial=null;floor.visible=oldFloor;scene.background.copy(oldBackground);draw();return data;}
  // Top-down height of the model on a measured grid, for comparison with a sampled height field.
  // Grid axes follow the layout: +u along `angle_rad` in plan (x east, north), +v 90 degrees left of it.
  function heightMap(l){
    const a=l.angle_rad,y0=-2,y1=bounds.max.y+5;
    const cam=new THREE.OrthographicCamera(l.u0-l.step/2,l.u0+(l.nu-.5)*l.step,l.v0+(l.nv-.5)*l.step,l.v0-l.step/2,.1,y1+60);
    cam.position.set(0,y1+50,0);cam.up.set(-Math.sin(a),0,-Math.cos(a));cam.lookAt(0,0,0);cam.updateMatrixWorld(true);
    const encode=new THREE.ShaderMaterial({side:THREE.DoubleSide,uniforms:{y0:{value:y0},y1:{value:y1}},
      vertexShader:'varying float vY;void main(){vec4 p=vec4(position,1.);\n#ifdef USE_INSTANCING\np=instanceMatrix*p;\n#endif\nvec4 w=modelMatrix*p;vY=w.y;gl_Position=projectionMatrix*viewMatrix*w;}',
      fragmentShader:'uniform float y0;uniform float y1;varying float vY;void main(){float h=clamp((vY-y0)/(y1-y0),0.,1.)*.999;vec3 c=fract(h*vec3(1.,255.,65025.));c-=c.yzz*vec3(1./255.,1./255.,0.);gl_FragColor=vec4(c,1.);}'});
    const target=new THREE.WebGLRenderTarget(l.nu,l.nv,{minFilter:THREE.NearestFilter,magFilter:THREE.NearestFilter,depthBuffer:true});
    const old={floor:floor.visible,background:scene.background,clear:renderer.getClearColor(new THREE.Color()),alpha:renderer.getClearAlpha()};
    floor.visible=false;scene.background=null;scene.overrideMaterial=encode;renderer.setClearColor(0x000000,1);renderer.setRenderTarget(target);renderer.clear();renderer.render(scene,cam);
    const pixels=new Uint8Array(l.nu*l.nv*4);renderer.readRenderTargetPixels(target,0,0,l.nu,l.nv,pixels);
    renderer.setRenderTarget(null);scene.overrideMaterial=null;scene.background=old.background;floor.visible=old.floor;renderer.setClearColor(old.clear,old.alpha);target.dispose();encode.dispose();draw();
    const heights=new Array(l.nu*l.nv);
    for(let i=0;i<heights.length;i++){const r=pixels[4*i],g=pixels[4*i+1],b=pixels[4*i+2];heights[i]=r+g+b===0?null:Math.round((y0+(r/255+g/65025+b/16581375)/.999*(y1-y0))*100)/100;}
    return heights;
  }
  // Deterministic sanity checks on kit parts: is every raised part resting on or joined to
  // something, and is anything a thin sheet standing clear of the roof behind it?
  function structure(){
    root.updateMatrixWorld(true);
    const parts=root.userData.components??[],ray=new THREE.Raycaster(),down=new THREE.Vector3(0,-1,0),issues=[];
    const hosts=new Set(['walls','roof','band','ground','tier','parapet','cornice']),surface=new Set(['window','curtainWall','ribbonWindows','fins','frameGrid','storefront','tree','columns','arcade','stairs']);
    const topAt=(list,x,z)=>{ray.set(new THREE.Vector3(x,1e4,z),down);ray.far=2e4;const hit=ray.intersectObjects(list,true)[0];return hit?hit.point.y:-Infinity;};
    let checked=0;
    for(const part of parts){
      const kind=part.component.kind;if((root.userData.objectKind??'building')==='building'&&(hosts.has(kind)||surface.has(kind)))continue;
      const box=new THREE.Box3().setFromObject(part.pivot);if((root.userData.objectKind??'building')!=='building'&&box.min.y<-.25)issues.push({id:part.component.id,kind,problem:'below_ground',bottom_m:box.min.y,top_m:box.max.y});if(box.isEmpty()||box.min.y<=((root.userData.objectKind??'building')==='building'?.6:.25))continue;
      if(++checked>400)break;
      const size=box.getSize(new THREE.Vector3()),c=box.getCenter(new THREE.Vector3()),others=parts.filter(p=>p!==part&&p.component.kind!=='ground').map(p=>p.pivot);
      const tops=[[0,0],[.3,.3],[-.3,.3],[.3,-.3],[-.3,-.3]].map(([dx,dz])=>topAt(others,c.x+dx*size.x,c.z+dz*size.z));
      const seated=tops.filter(t=>t>=box.min.y-.35).length;let joined=seated>=3;
      for(let k=0;k<8&&!joined;k++){ray.set(c,new THREE.Vector3(Math.cos(k*Math.PI/4),0,Math.sin(k*Math.PI/4)));ray.far=Math.hypot(size.x,size.z)/2+.5;joined=ray.intersectObjects(others,true).length>0;}
      const where={part:part.component.id,kind,x:+c.x.toFixed(1),z:+c.z.toFixed(1),bottom_m:+box.min.y.toFixed(2),top_m:+box.max.y.toFixed(2)};
      if(!joined){const support=Math.max(...tops),found=Number.isFinite(support);issues.push({...where,problem:'unsupported',support_found:found,gap_below_m:found?+(box.min.y-support).toFixed(2):null});}
      const inverse=part.pivot.matrixWorld.clone().invert(),local=new THREE.Box3();
      part.pivot.traverse(o=>{if(o.isMesh){o.geometry.computeBoundingBox();local.union(o.geometry.boundingBox.clone().applyMatrix4(new THREE.Matrix4().multiplyMatrices(inverse,o.matrixWorld)));}});
      const extent=local.getSize(new THREE.Vector3()),thin=Math.min(extent.x,extent.z),host=Math.max(0,topAt(others,c.x,c.z));
      if(thin<.5&&Math.max(extent.x,extent.z)>2&&extent.y>3&&box.max.y-host>2.5)issues.push({...where,problem:'thin_sheet_above_host',thickness_m:+thin.toFixed(2),rises_above_host_m:+(box.max.y-host).toFixed(2)});
    }
    return {checked,issues};
  }
  window.worldscale={view,pose,state,lookdev,manifest,geometry,explode,pick,silhouette,clay,heightMap,structure,root,renderer};
  const params=new URLSearchParams(location.search);view(Number(params.get('azimuth')??35),Number(params.get('elevation')??28));state({hour:13,wetness:0,wind:0});
  const hour=document.getElementById('hour'),wet=document.getElementById('wetness'),wind=document.getElementById('wind');
  const change=()=>state({hour:Number(hour.value),wetness:Number(wet.value),wind:Number(wind.value)});hour.oninput=change;wet.oninput=change;wind.oninput=change;
  document.getElementById('explode').oninput=e=>explode(Number(e.target.value));
  renderer.setAnimationLoop(time=>{tick(root,time/1000);draw();});window.worldscaleReady=true;
}
