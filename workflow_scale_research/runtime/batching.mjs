// Static asset instances. Geometry/material identity and instance ownership are
// preserved; moving parts and skinned/morph geometry require a separate path.
import * as THREE from 'three';

function streams(g) {
  return [g.index,...Object.keys(g.attributes).sort().map(k=>g.attributes[k])].filter(Boolean);
}
function signature(g) {
  let hash=2166136261;
  for(const a of streams(g)) {
    if(a.isInterleavedBufferAttribute)throw Error('BATCH_INTERLEAVED_UNSUPPORTED');
    const bytes=new Uint8Array(a.array.buffer,a.array.byteOffset,a.array.byteLength);
    for(const byte of bytes)hash=Math.imul(hash^byte,16777619);
  }
  return [hash>>>0,JSON.stringify(g.groups),JSON.stringify(g.drawRange),Object.keys(g.attributes).sort().join(',')].join(':');
}
function equal(a,b) {
  const x=streams(a),y=streams(b);
  if(x.length!==y.length)return false;
  return x.every((s,i)=>s.itemSize===y[i].itemSize&&s.normalized===y[i].normalized&&s.array.constructor===y[i].array.constructor&&s.array.length===y[i].array.length&&s.array.every((v,j)=>v===y[i].array[j]));
}
export function batchStaticAssets(prototype, placements) {
  if(!placements.length||new Set(placements.map(p=>p.id)).size!==placements.length)throw Error('BATCH_UNIQUE_ASSET_IDS_REQUIRED');
  prototype.updateWorldMatrix(true,true);
  const buckets=new Map(),groups=[];
  prototype.traverseVisible(node=>{
    if(!node.isMesh)return;
    if(node.isSkinnedMesh||node.morphTargetInfluences?.length||node.isInstancedMesh)throw Error('BATCH_STATIC_MESHES_ONLY');
    const materials=Array.isArray(node.material)?node.material:[node.material];
    const key=signature(node.geometry)+':'+materials.map(m=>m.uuid).join(',')+':'+[node.castShadow,node.receiveShadow,node.renderOrder,node.layers.mask].join(',');
    const bucket=buckets.get(key)??[];
    let group=bucket.find(g=>equal(g.geometry,node.geometry));
    if(!group){group={geometry:node.geometry,material:node.material,renderOrder:node.renderOrder,layers:node.layers.mask,parts:[]};bucket.push(group);groups.push(group);buckets.set(key,bucket);}
    let owner=node;while(!owner.name&&owner.parent&&owner!==prototype)owner=owner.parent;
    group.parts.push({matrix:node.matrixWorld.clone(),component:owner.name,castShadow:node.castShadow,receiveShadow:node.receiveShadow});
  });
  const root=new THREE.Group();root.name='static-assets';
  root.userData.look={...(prototype.userData.look??{})};
  for(const [groupIndex,group] of groups.entries()) {
    const mesh=new THREE.InstancedMesh(group.geometry,group.material,group.parts.length*placements.length),owners=[];
    mesh.name='batch-'+groupIndex;let index=0;
    mesh.renderOrder=group.renderOrder;mesh.layers.mask=group.layers;
    mesh.castShadow=group.parts.some(p=>p.castShadow);mesh.receiveShadow=group.parts.some(p=>p.receiveShadow);
    for(const placement of placements) {
      const position=placement.position??[0,0,0],yaw=placement.yaw??0;
      if(!position.every(Number.isFinite)||!Number.isFinite(yaw))throw Error('BATCH_INVALID_TRANSFORM');
      const transform=new THREE.Matrix4().makeRotationY(yaw);transform.setPosition(...position);
      for(const part of group.parts){mesh.setMatrixAt(index++,transform.clone().multiply(part.matrix));owners.push({asset:placement.id,component:part.component});}
    }
    mesh.userData.instanceOwners=owners;mesh.instanceMatrix.needsUpdate=true;mesh.computeBoundingBox();mesh.computeBoundingSphere();root.add(mesh);
  }
  root.userData.batching={assets:placements.length,prototypeMeshes:groups.reduce((n,g)=>n+g.parts.length,0),drawGroups:groups.length,scope:'Static replicas; not a factual district reconstruction.'};
  return root;
}

export function resolveBatchHit(hit){return hit.object.userData.instanceOwners?.[hit.instanceId]??null;}
