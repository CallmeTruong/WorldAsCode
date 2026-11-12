// Pure, deterministic tree descriptions. Position never depends on shape seed.
export function treeRandom(seed){
 let state=2166136261;for(const c of String(seed))state=Math.imul(state^c.charCodeAt(0),16777619)>>>0;
 return ()=>{state=(state+0x6d2b79f5)>>>0;let n=state;n=Math.imul(n^(n>>>15),n|1);n^=n+Math.imul(n^(n>>>7),n|61);return ((n^(n>>>14))>>>0)/4294967296;};
}
export function describeTree(seed,options={}){
 const random=treeRandom(seed),families=['rounded','spreading','columnar','palm'];
 const family=options.family||families[Math.floor(random()*3)]; // palms require a source hint, not random climate changes
 if(!families.includes(family))throw Error('UNKNOWN_TREE_FAMILY');
 const height=options.height??(family==='palm'?9+random()*5:5+random()*6);
 const radius=options.crownRadius??(family==='columnar'?height*.14:height*(.23+random()*.1));
 if(!Number.isFinite(height)||!Number.isFinite(radius)||height<1||height>40||radius<.2||radius>15)throw Error('TREE_DIMENSION_LIMIT');
 const wood=[],crowns=[],fronds=[];const lean=[(random()-.5)*height*.07,(random()-.5)*height*.07];
 const trunkTop=family==='palm'?height*.88:height*.61;
 wood.push({start:[0,0,0],end:[lean[0],trunkTop,lean[1]],radius:height*.025});
 if(family==='palm'){
  const count=9+Math.floor(random()*5),phase=random()*Math.PI*2;
  for(let i=0;i<count;i++){const a=phase+i*Math.PI*2/count,length=radius*(1.1+random()*.45);
   fronds.push({start:[lean[0],trunkTop,lean[1]],end:[lean[0]+Math.cos(a)*length,trunkTop+radius*(.1+random()*.4),lean[1]+Math.sin(a)*length],width:radius*(.20+random()*.08),shade:.78+random()*.3});}
 }else{
  const count=family==='spreading'?9:6+Math.floor(random()*3);
  for(let i=0;i<count;i++){
   const a=i*Math.PI*2/count+random()*.4,extent=radius*(family==='columnar'?.4:.65+random()*.2);
   const end=[lean[0]+Math.cos(a)*extent,height*(.62+random()*.16),lean[1]+Math.sin(a)*extent];
   wood.push({start:[lean[0]*.6,trunkTop*(.62+random()*.2),lean[1]*.6],end,radius:height*(.009+random()*.004)});
   for(let j=0;j<3;j++){const r=radius*(.38+random()*.20);
    crowns.push({position:[end[0]+(random()-.5)*radius*.6,end[1]+(random()-.3)*radius*.6,end[2]+(random()-.5)*radius*.6],
     scale:[r*(family==='spreading'?1.25:1),r*(family==='columnar'?2.1:.8+random()*.4),r],rotation:random()*Math.PI,shade:.7+random()*.45});}
  }
 }
 return {seed:String(seed),family,height,crownRadius:radius,wood,crowns,fronds};
}
function segmentRecord(start,end,radius,extra={}){
 const d=end.map((v,i)=>v-start[i]),length=Math.hypot(...d),n=d.map(v=>v/length);
 let q=[n[2],0,-n[0],1+n[1]],norm=Math.hypot(...q);q=norm<1e-8?[1,0,0,0]:q.map(v=>v/norm);
 return {position:start.map((v,i)=>(v+end[i])/2),scale:[radius,length/2,radius],quaternion:q,...extra};
}
export function treeBatches(placements,options={}){
 const detail=options.clusterDetail??1;if(!Number.isInteger(detail)||detail<1||detail>4)throw Error('TREE_DETAIL_LIMIT');
 const wood=[],crowns=[],fronds=[],metadata=[];
 for(const t of placements){
  if(!Array.isArray(t.position)||t.position.length!==2||!t.position.every(Number.isFinite))throw Error('TREE_POSITION_REQUIRED');
  const spec=describeTree(t.seed??t.id,{height:t.height,crownRadius:t.crown_radius,family:t.family});
  const offset=v=>[v[0]+t.position[0],v[1],v[2]+t.position[1]];
  for(const b of spec.wood)wood.push(segmentRecord(offset(b.start),offset(b.end),b.radius));
  const leafRandom=treeRandom(String(t.seed??t.id)+':foliage');
  for(const c of spec.crowns){
   if(detail===1){crowns.push({...c,position:offset(c.position)});continue;}
   for(let i=0;i<detail*3;i++){
    const a=leafRandom()*Math.PI*2,z=leafRandom()*2-1,r=Math.sqrt(1-z*z),v=[Math.cos(a)*r,z,Math.sin(a)*r];
    const size=.38+leafRandom()*.17;
    crowns.push({...c,position:offset(c.position.map((p,k)=>p+v[k]*c.scale[k]*.64)),scale:c.scale.map(s=>s*size),shade:c.shade*(.87+leafRandom()*.26)});
   }
  }
  for(const f of spec.fronds){const v=segmentRecord(offset(f.start),offset(f.end),f.width,{shade:f.shade});v.scale[1]*=2;v.position=offset(f.start);fronds.push(v);}
  metadata.push({id:t.id,position:[...t.position],seed:String(t.seed??t.id),family:spec.family,evidence:t.evidence||'unspecified'});
 }
 return {wood,crowns,fronds,metadata};
}
// Closed, curved palm frond; shared across all seeds and instances.
export function frondMeshData(){
 const positions=[],indices=[],steps=10;
 for(let i=0;i<=steps;i++){const t=i/steps,w=.025+.48*Math.sin(Math.PI*t),z=-.3*t*t;
  positions.push(-w,t,z-.015,w,t,z-.015,w,t,z+.015,-w,t,z+.015);}
 for(let i=0;i<steps;i++)for(let j=0;j<4;j++){const a=i*4+j,b=i*4+(j+1)%4,c=(i+1)*4+j,d=(i+1)*4+(j+1)%4;indices.push(a,b,c,b,d,c);}
 indices.push(0,2,1,0,3,2);const n=steps*4;indices.push(n,n+1,n+2,n,n+2,n+3);
 return {positions,indices};
}
