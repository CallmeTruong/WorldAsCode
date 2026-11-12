import * as THREE from 'three';
import {build} from 'generated-city';
import {geometryTools} from './urban-geometry-tools.mjs';
self.onmessage=({data})=>{
  try{
    const root=build({city:data,tools:geometryTools});
    if(!root?.isObject3D)throw Error('INVALID_ROOT');
    root.updateMatrixWorld(true);
    // Parametric geometry JSON reconstructs constructor parameters and loses
    // attribute-space rotate/translate edits. Bake exact emitted attributes.
    const baked=new Map(),byContent=new Map();
    root.traverse(o=>{if(o.isMesh){
      const g=o.geometry;
      if(!baked.has(g.uuid)){
        if(!g.getAttribute('normal'))g.computeVertexNormals();
        if(Object.values(g.morphAttributes).some(a=>a.length))throw Error('MORPH_GEOMETRY_UNSUPPORTED');
        // Separately constructed equal boxes/columns used to serialize and pass
        // through the expensive topology gate hundreds of times. Share exact
        // attribute/index/group matches; transforms and materials stay per mesh.
        const key=JSON.stringify({attributes:Object.entries(g.attributes).sort(([a],[b])=>a.localeCompare(b)).map(([name,a])=>[name,a.itemSize,a.normalized,Array.from(a.array)]),index:g.index?Array.from(g.index.array):null,groups:g.groups,drawRange:g.drawRange});
        if(!byContent.has(key))byContent.set(key,new THREE.BufferGeometry().copy(g));
        baked.set(g.uuid,byContent.get(key));
      }
      o.geometry=baked.get(g.uuid);
    }});
    const unique=new Map(), objects=[];let meshes=0,instances=0,triangles=0,vertices=0;
    root.traverse(o=>{
      if(o.isMesh){
        if(++meshes>8000)throw Error('MESH_LIMIT');
        const geometry=o.geometry,p=geometry.getAttribute('position');
        if(!p || p.count>300000)throw Error('GEOMETRY_VERTEX_LIMIT');
        if(!geometry.getAttribute('normal'))geometry.computeVertexNormals();
        const amount=o.isInstancedMesh?o.count:1;
        instances+=amount;if(instances>30000)throw Error('INSTANCE_LIMIT');
        const tri=(geometry.index?geometry.index.count:p.count)/3;
        triangles+=tri*amount;if(triangles>500000)throw Error('TRIANGLE_LIMIT');
        if(o.isInstancedMesh){
          const matrix=new THREE.Matrix4();
          for(let i=0;i<o.count;i++){
            o.getMatrixAt(i,matrix);
            if(!matrix.elements.every(Number.isFinite)||matrix.determinant()<=1e-12)throw Error('INVALID_INSTANCE_TRANSFORM');
          }
          o.computeBoundingBox();o.computeBoundingSphere();
        }
        if(!o.matrixWorld.elements.every(Number.isFinite)||o.matrixWorld.determinant()<=1e-12)throw Error('INVALID_WORLD_TRANSFORM');
        if(!unique.has(geometry.uuid)){
          const v=[],n=[],normal=geometry.getAttribute('normal');vertices+=p.count;
          if(vertices>500000)throw Error('UNIQUE_VERTEX_LIMIT');
          for(let i=0;i<p.count;i++){
            const a=[p.getX(i),p.getY(i),p.getZ(i)];
            if(!a.every(Number.isFinite))throw Error('NONFINITE_GEOMETRY');
            v.push(a);n.push([normal.getX(i),normal.getY(i),normal.getZ(i)]);
          }
          const indices=geometry.index?Array.from(geometry.index.array):Array.from({length:p.count},(_,i)=>i);
          if(indices.length%3||indices.some(i=>i<0||i>=p.count))throw Error('INVALID_INDICES');
          unique.set(geometry.uuid,{id:`geometry-${unique.size}`,role:'architectural',vertices:v,normals:n,indices});
        }
      }
      if(o.userData?.objectId){
        const b=new THREE.Box3().setFromObject(o);
        const surfaces=[];o.traverse(q=>{if(q.isMesh)for(const m of (Array.isArray(q.material)?q.material:[q.material]))surfaces.push({name:m.name,role:m.userData?.textureRole||null});});
        objects.push({id:o.userData.objectId,min:b.min.toArray(),max:b.max.toArray(),surfaces});
      }
    });
    const scene=root.toJSON();
    if(scene.images?.length||scene.textures?.length)throw Error('GENERATED_TEXTURE_FORBIDDEN');
    if(!meshes||objects.length!==data.buildings.length || new Set(objects.map(o=>o.id)).size!==objects.length)throw Error('OBJECT_COVERAGE');
    self.postMessage({ok:true,scene,geometry:{meshes:Array.from(unique.values()),triangleBudget:500000},
      metrics:{mesh_objects:meshes,instance_count:instances,rendered_triangles:triangles,unique_geometries:unique.size,objects}});
  }catch(e){self.postMessage({ok:false,error:String(e)});}
};
