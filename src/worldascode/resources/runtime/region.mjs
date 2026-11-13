import * as THREE from 'three';
import {buildDesign} from './kit.mjs';

// Owned composition glue: authored recipes receive local facts, never the region root.
export function buildRegionDesign(designs,region,style={},packs=[]){
  const root=new THREE.Group();root.name=region.id;
  root.userData.objectKind='region';root.userData.components=[];root.userData.entityIndex={};root.userData.packCalls={};
  const ids=region.entities.map(e=>e.id);
  if(Object.keys(designs).length!==ids.length||ids.some(id=>typeof designs[id]!=='function'))throw Error('REGION_ENTITY_DESIGNS_MISMATCH');
  for(const entity of region.entities){
    let object;
    let seed=region.seed>>>0;for(const c of entity.id)seed=Math.imul(seed^c.charCodeAt(0),16777619)>>>0;
    try{object=buildDesign(designs[entity.id],{...entity.site,seed},style,packs);}
    catch(error){throw Error('ENTITY '+entity.id+': '+error.message);}
    object.name=entity.id;object.position.set(...entity.anchor);object.rotation.y=entity.yaw??0;root.add(object);
    for(const part of object.userData.components??[]){
      root.userData.components.push({...part,entity_id:entity.id,entity_kind:entity.kind,local_component_id:part.component.id,
        instance:entity.id,component:{...part.component,id:entity.id+'::'+part.component.id}});
    }
    for(const [name,count] of Object.entries(object.userData.packCalls??{}))root.userData.packCalls[name]=(root.userData.packCalls[name]??0)+count;
  }
  root.updateMatrixWorld(true);
  const bounds=o=>{const b=new THREE.Box3().setFromObject(o);if(b.isEmpty()||![...b.min.toArray(),...b.max.toArray()].every(Number.isFinite))throw Error('REGION_EMPTY_OR_NONFINITE_COMPONENT:'+o.name);return {min:b.min.toArray(),max:b.max.toArray()};};
  for(const object of root.children)root.userData.entityIndex[object.name]={bounds:bounds(object),component_ids:root.userData.components.filter(p=>p.entity_id===object.name).map(p=>p.component.id)};
  root.userData.componentIndex=Object.fromEntries(root.userData.components.map(p=>[p.component.id,{entity_id:p.entity_id,local_component_id:p.local_component_id,kind:p.component.kind,bounds:bounds(p.pivot)}]));
  root.userData.look=style.light??{};
  return root;
}
