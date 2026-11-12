import * as THREE from 'three';

// Subtract a frame-aligned plan rectangle from a triangulated roof shell.
// Interpolate existing metric UVs at every cut, preserving the host planes.
export function cutRoofOpening(mesh, frame, width, front, back) {
  const original = mesh.geometry;
  const geometry = original.index ? original.toNonIndexed() : original;
  const p=geometry.attributes.position, uv=geometry.attributes.uv;
  const c=Math.cos(frame.yaw??0),s=Math.sin(frame.yaw??0);
  const planes=[v=>(v[0]-frame.x)*c-(v[2]-frame.z)*s+width/2,
    v=>width/2-((v[0]-frame.x)*c-(v[2]-frame.z)*s),
    v=>(v[0]-frame.x)*s+(v[2]-frame.z)*c-back,
    v=>front-((v[0]-frame.x)*s+(v[2]-frame.z)*c)];
  function clip(poly, distance, inside) {
    if(!poly.length)return [];
    const out=[];
    for(let i=0;i<poly.length;i++){
      const a=poly[i],b=poly[(i+1)%poly.length],da=distance(a),db=distance(b);
      const ina=inside?da>=0:da<=0,inb=inside?db>=0:db<=0;
      if(ina)out.push(a);
      if(ina!==inb){const t=da/(da-db);out.push(a.map((v,k)=>v+t*(b[k]-v)));}
    }
    return out;
  }
  const positions=[],uvs=[];
  for(let i=0;i<p.count;i+=3){
    let remainder=[0,1,2].map(k=>[p.getX(i+k),p.getY(i+k),p.getZ(i+k),uv?.getX(i+k)??0,uv?.getY(i+k)??0]);
    const fragments=[];
    for(const distance of planes){
      const outside=clip(remainder,distance,false);if(outside.length>=3)fragments.push(outside);
      remainder=clip(remainder,distance,true);if(remainder.length<3)break;
    }
    for(const poly of fragments)for(let j=1;j+1<poly.length;j++){
      const a=new THREE.Vector3(...poly[0].slice(0,3)),b=new THREE.Vector3(...poly[j].slice(0,3)),d=new THREE.Vector3(...poly[j+1].slice(0,3));
      if(b.sub(a).cross(d.sub(a)).lengthSq()<1e-15)continue;
      for(const v of [poly[0],poly[j],poly[j+1]]){positions.push(...v.slice(0,3));uvs.push(...v.slice(3));}
    }
  }
  const result=new THREE.BufferGeometry();result.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));result.setAttribute('uv',new THREE.Float32BufferAttribute(uvs,2));result.computeVertexNormals();
  mesh.geometry=result;
  if(geometry!==original)geometry.dispose();original.dispose();
}
