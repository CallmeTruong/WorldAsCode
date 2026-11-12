import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';

const W=1440,H=1080;
const renderer=new THREE.WebGLRenderer({antialias:true,preserveDrawingBuffer:true});renderer.setSize(W,H);renderer.setPixelRatio(1);renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.NoToneMapping;
renderer.shadowMap.enabled=true;renderer.shadowMap.type=THREE.PCFSoftShadowMap;renderer.debug.onShaderError=()=>{throw Error('MEASURED_SHADER_FAILED');};document.body.appendChild(renderer.domElement);
const scene=new THREE.Scene();scene.background=new THREE.Color(0xe9eeed);
let camera=new THREE.OrthographicCamera(-200,200,150,-150,.1,10000),data,selected=null,mode='source',variant='regularized',root=new THREE.Group();scene.add(root);
const controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=true;
const hemi=new THREE.HemisphereLight(0xdfeeff,0x7e7868,.35);scene.add(hemi);
const sun=new THREE.DirectionalLight(0xfff5df,2.5);sun.position.set(-200,400,200);sun.castShadow=true;sun.shadow.mapSize.set(4096,4096);Object.assign(sun.shadow.camera,{left:-250,right:250,top:250,bottom:-250,far:1200});sun.shadow.normalBias=.015;scene.add(sun);
const textures=[],materials=new Map(),geometries=new Map();
function material(source,id){
 const key=mode+':'+source+':'+id;if(materials.has(key))return materials.get(key);
 let m;
 if(mode==='coverage')m=new THREE.MeshBasicMaterial({color:source>=0?0x83b4a0:0xc05d79,side:THREE.DoubleSide});
 else if(mode==='geometry')m=new THREE.MeshStandardMaterial({color:0xa3b2b5,roughness:.9,side:THREE.DoubleSide});
 else if(source>=0){
  m=mode==='relight'?new THREE.MeshStandardMaterial({map:textures[source],roughness:.87,metalness:0,side:THREE.DoubleSide}):new THREE.MeshBasicMaterial({map:textures[source],toneMapped:false,side:THREE.DoubleSide});
 }else{
  m=new THREE.MeshStandardMaterial({color:id==='ground'?0x8f9689:0x949e9c,roughness:.95,side:THREE.DoubleSide});m.name='unobserved_fallback';
 }
 materials.set(key,m);return m;
}
function rebuild(){
 root.clear();
 for(const entry of data.variants[variant]){
  let object=root.children.find(o=>o.userData.objectId===entry.object_id);
  if(!object){object=new THREE.Group();object.name=entry.object_id;object.userData.objectId=entry.object_id;root.add(object);}
  const key=variant+':'+entry.object_id+':'+entry.source_view;
  let g=geometries.get(key);
  if(!g){g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(entry.positions,3));if(entry.uv.length)g.setAttribute('uv',new THREE.Float32BufferAttribute(entry.uv,2));g.computeVertexNormals();g.computeBoundingSphere();geometries.set(key,g);}
  const mesh=new THREE.Mesh(g,material(entry.source_view,entry.object_id));mesh.castShadow=mode!=='source';mesh.receiveShadow=mode!=='source';object.add(mesh);
 }
 root.children.forEach(o=>o.visible=selected===null||o.userData.objectId===selected);renderer.render(scene,camera);
}
window.initMeasured=async payload=>{
 data=payload;const loader=new THREE.TextureLoader();
 for(const view of data.views){const t=await loader.loadAsync(view.image);t.colorSpace=THREE.SRGBColorSpace;t.anisotropy=Math.min(8,renderer.capabilities.getMaxAnisotropy());textures.push(t);}
 rebuild();window.measuredView('overview');window.__MEASURED_READY__=true;
 renderer.setAnimationLoop(()=>{controls.update();renderer.render(scene,camera);});
};
window.measuredVariant=value=>{if(!data.variants[value])throw Error('UNKNOWN_VARIANT');variant=value;rebuild();};
window.measuredMode=value=>{if(!['source','relight','geometry','coverage'].includes(value))throw Error('UNKNOWN_MODE');mode=value;rebuild();};
window.measuredSelect=value=>{selected=value||null;rebuild();window.measuredView('overview');};
window.measuredView=name=>{
 if(name.startsWith('source:')){
  const view=data.views[Number(name.split(':')[1])],p=view.local_camera;
  camera=new THREE.PerspectiveCamera(p.fov,p.aspect,.3,10000);camera.position.fromArray(p.position);camera.up.fromArray(p.up).normalize();camera.lookAt(camera.position.clone().add(new THREE.Vector3().fromArray(p.direction)));controls.object=camera;controls.target.copy(camera.position).addScaledVector(new THREE.Vector3().fromArray(p.direction),view.range);renderer.render(scene,camera);return;
 }
 const target=selected?root.children.find(o=>o.userData.objectId===selected):root;
 const bounds=new THREE.Box3().setFromObject(target),center=bounds.getCenter(new THREE.Vector3()),size=bounds.getSize(new THREE.Vector3());
 const span=Math.max(Math.hypot(size.x,size.z)*1.18,size.y*1.7,25);
 camera=new THREE.OrthographicCamera(-span/2,span/2,span*H/W/2,-span*H/W/2,.1,10000);controls.object=camera;
 const direction=name==='top'?new THREE.Vector3(0,1,.0001):name==='north'?new THREE.Vector3(430,440,-500).normalize():new THREE.Vector3(-560,490,80).normalize();
 camera.position.copy(center).addScaledVector(direction,span*3);controls.target.copy(center);camera.lookAt(center);controls.update();renderer.render(scene,camera);
};
window.measuredStats=()=>{renderer.render(scene,camera);return {draw_calls:renderer.info.render.calls,triangles:renderer.info.render.triangles,textures:renderer.info.memory.textures,geometries:renderer.info.memory.geometries,variant,mode};};
window.pauseMeasured=()=>renderer.setAnimationLoop(null);
window.measuredFingerprint=()=>{let hash=2166136261,count=0;root.traverse(o=>{if(o.isMesh){count++;for(const x of o.geometry.attributes.position.array)hash=Math.imul(hash^(Math.round(x*10000)|0),16777619)>>>0;}});return {hash:hash.toString(16),meshes:count};};
