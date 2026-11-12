import * as THREE from 'three';

function convexSolid(vertices,faces,material){
 const v=vertices.map(p=>new THREE.Vector3(...p)),center=new THREE.Vector3();v.forEach(p=>center.add(p));center.divideScalar(v.length);
 const out=[];
 for(const face of faces)for(let i=1;i<face.length-1;i++){
  const ids=[face[0],face[i],face[i+1]],a=v[ids[0]],b=v[ids[1]],c=v[ids[2]];
  const normal=b.clone().sub(a).cross(c.clone().sub(a));if(normal.lengthSq()<1e-12)throw Error('DEGENERATE_TOOL_FACE');
  if(normal.dot(a.clone().add(b).add(c).divideScalar(3).sub(center))<0)[ids[1],ids[2]]=[ids[2],ids[1]];
  for(const id of ids)out.push(...v[id].toArray());
 }
 const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(out,3));geometry.computeVertexNormals();return new THREE.Mesh(geometry,material);
}

export function gableRoof({length,width,eave,rise,center=[0,0],rotation=0,material}){
 if(![length,width,eave,rise,...center,rotation].every(Number.isFinite)||Math.min(length,width,rise)<.05)throw Error('INVALID_GABLE_DIMENSIONS');
 const a=length/2,b=width/2;
 const mesh=convexSolid([[-a,eave,-b],[a,eave,-b],[a,eave,b],[-a,eave,b],[-a,eave+rise,0],[a,eave+rise,0]],[[0,3,2,1],[0,4,3],[1,2,5],[0,1,5,4],[3,4,5,2]],material);
 mesh.position.set(center[0],0,center[1]);mesh.rotation.y=rotation;return mesh;
}

export function hipRoof({length,width,eave,rise,inset,center=[0,0],rotation=0,material}){
 if(![length,width,eave,rise,inset,...center,rotation].every(Number.isFinite)||Math.min(length,width,rise,inset)<.05||inset>=Math.min(length,width)/2)throw Error('INVALID_HIP_DIMENSIONS');
 const a=length/2,b=width/2,c=a-inset,d=b-inset;
 const mesh=convexSolid([[-a,eave,-b],[a,eave,-b],[a,eave,b],[-a,eave,b],[-c,eave+rise,-d],[c,eave+rise,-d],[c,eave+rise,d],[-c,eave+rise,d]],[[0,3,2,1],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]],material);
 mesh.position.set(center[0],0,center[1]);mesh.rotation.y=rotation;return mesh;
}

export function extrudeFootprint({outer,holes=[],base=0,height,material}){
 if(!Number.isFinite(height)||height<.02||!Number.isFinite(base)||outer.length<3)throw Error('INVALID_FOOTPRINT_SOLID');
 const points=ring=>ring.map(([x,z])=>new THREE.Vector2(x,-z));let ring=points(outer);
 if(!THREE.ShapeUtils.isClockWise(ring))ring.reverse();const shape=new THREE.Shape(ring);
 for(const hole of holes){ring=points(hole);if(THREE.ShapeUtils.isClockWise(ring))ring.reverse();shape.holes.push(new THREE.Path(ring));}
 const geometry=new THREE.ExtrudeGeometry(shape,{depth:height,bevelEnabled:false,steps:1});geometry.rotateX(-Math.PI/2);geometry.translate(0,base,0);return new THREE.Mesh(geometry,material);
}

export const geometryTools=Object.freeze({gableRoof,hipRoof,extrudeFootprint});
