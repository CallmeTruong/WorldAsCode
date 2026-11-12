import * as THREE from 'three';
import {build} from 'generated-building';

// This bundle runs only inside a network-denied dedicated browser Worker.
self.onmessage = () => {
  try {
    const root = build({});
    if (!root?.isObject3D) throw Error('build must return a Three.js Object3D');
    root.updateMatrixWorld(true);
    const meshes = [];
    let triangleCount = 0, verticesTotal = 0;
    root.traverse(obj => {
      if (!obj.isMesh) return;
      if (obj.isInstancedMesh) throw Error('Use named ordinary meshes for measurable research baseline');
      const g = obj.geometry;
      const p = g.getAttribute('position');
      if (!p || p.count > 150000) throw Error('invalid vertex budget');
      verticesTotal += p.count;
      if (verticesTotal > 300000 || meshes.length >= 1200) throw Error('scene budget exceeded');
      if (!g.getAttribute('normal')) g.computeVertexNormals();
      const n = g.getAttribute('normal');
      const positions = [], normals = [];
      for(let i=0;i<p.count;i++) {
        const v = [p.getX(i),p.getY(i),p.getZ(i)];
        if (!v.every(Number.isFinite)) throw Error('nonfinite geometry');
        positions.push(v); normals.push([n.getX(i),n.getY(i),n.getZ(i)]);
      }
      const indices = g.index ? Array.from(g.index.array) : Array.from({length:p.count}, (_,i)=>i);
      triangleCount += indices.length / 3;
      if (indices.length % 3 || triangleCount > 50000) throw Error('triangle budget exceeded');
      const bounds = new THREE.Box3().setFromObject(obj);
      if (![...bounds.min.toArray(), ...bounds.max.toArray()].every(Number.isFinite)) throw Error('nonfinite bounds');
      meshes.push({id:obj.name || `mesh-${meshes.length}`, vertices:positions, normals, indices,
        bounds:[bounds.min.toArray(),bounds.max.toArray()], role:'architectural'});
    });
    if (!meshes.length) throw Error('empty scene');
    const bounds = new THREE.Box3().setFromObject(root);
    const size = bounds.getSize(new THREE.Vector3());
    if (size.toArray().some(v=>v<=0 || v>10000)) throw Error('invalid scene dimensions');
    self.postMessage({ok:true, scene:root.toJSON(), geometry:{meshes, triangleBudget:50000},
      bounds:{min:bounds.min.toArray(),max:bounds.max.toArray()}, triangles:triangleCount});
  } catch(error) { self.postMessage({ok:false,error:String(error)}); }
};
