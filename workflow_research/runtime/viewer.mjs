import * as THREE from 'three';

const renderer = new THREE.WebGLRenderer({antialias:true, preserveDrawingBuffer:true});
renderer.setSize(800,800);
renderer.setPixelRatio(1);
renderer.setClearColor(0xe8edf2);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.2;
document.body.style.margin = '0';
document.body.appendChild(renderer.domElement);
const scene = new THREE.Scene();
scene.add(new THREE.HemisphereLight(0xffffff,0x8899aa,2.5));
const sun = new THREE.DirectionalLight(0xffffff,3.5);
sun.position.set(-30,50,40); scene.add(sun);
let model, bounds, camera;
window.loadModel = (data) => {
  if (data.images?.length || data.textures?.length) throw Error('Texture and image loading forbidden');
  model = new THREE.ObjectLoader().parse(data);
  scene.add(model); model.updateMatrixWorld(true);
  bounds = new THREE.Box3().setFromObject(model);
  return {min:bounds.min.toArray(),max:bounds.max.toArray()};
};
window.captureView = ({azimuth=0,elevation=0}) => {
  const center = bounds.getCenter(new THREE.Vector3());
  const span = bounds.getSize(new THREE.Vector3()).length();
  const distance = span * 1.65;
  const a=azimuth*Math.PI/180,e=elevation*Math.PI/180;
  camera = new THREE.PerspectiveCamera(35,1,Math.max(span/1000,0.001),span*30);
  camera.position.copy(center).add(new THREE.Vector3(Math.sin(a)*Math.cos(e),Math.sin(e),Math.cos(a)*Math.cos(e)).multiplyScalar(distance));
  camera.lookAt(center); camera.updateProjectionMatrix();
  renderer.render(scene,camera);
};
window.__IMG2THREEJS_READY__ = true;
window.__IMG2THREEJS_CAPTURE__ = {
  setCamera: async ({azimuthDegrees=0,elevationDegrees=0}) => window.captureView({azimuth:azimuthDegrees,elevation:elevationDegrees}),
  capturePass: async () => { renderer.render(scene,camera); }
};
