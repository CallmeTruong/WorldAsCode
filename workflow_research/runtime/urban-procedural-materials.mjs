// Optional surface tools, not a compulsory asset catalog. Colours come from the agent.
export function proceduralSurface(THREE,recipe,baseColor){
 const allowed=['none','asphalt','paving','brick','slate','grass'];
 if(!allowed.includes(recipe.pattern||'none'))throw Error('SURFACE_PATTERN');
 if(!Number.isFinite(recipe.tile_m)||recipe.tile_m<.1||recipe.tile_m>100)throw Error('SURFACE_SCALE');
 const canvas=document.createElement('canvas');canvas.width=canvas.height=256;
 const ctx=canvas.getContext('2d'),color=new THREE.Color(baseColor);
 ctx.fillStyle='#'+color.getHexString();ctx.fillRect(0,0,256,256);
 let seed=(recipe.seed??17)>>>0;
 const random=()=>{seed=(Math.imul(1664525,seed)+1013904223)>>>0;return seed/4294967296;};
 const strength=recipe.pattern==='grass'?.12:.035;
 for(let i=0;i<6000;i++){ctx.fillStyle=random()<.5?`rgba(255,255,255,${strength})`:`rgba(0,0,0,${strength})`;ctx.fillRect(random()*256,random()*256,1+random()*2,1+random()*2);}
 if(['paving','brick','slate'].includes(recipe.pattern)){
  const rows=Math.max(2,Math.min(32,recipe.rows|| (recipe.pattern==='brick'?20:8)));
  const cols=Math.max(2,Math.min(32,recipe.columns||8));
  ctx.strokeStyle=recipe.pattern==='brick'?'rgba(210,205,190,.5)':'rgba(20,25,30,.25)';ctx.lineWidth=recipe.pattern==='brick'?1.2:.7;
  for(let r=0;r<rows;r++){
   ctx.beginPath();ctx.moveTo(0,r*256/rows);ctx.lineTo(256,r*256/rows);ctx.stroke();
   for(let c=-1;c<=cols;c++){const x=(c+(r%2)*.5)*256/cols;ctx.beginPath();ctx.moveTo(x,r*256/rows);ctx.lineTo(x,(r+1)*256/rows);ctx.stroke();}
  }
 }
 const map=new THREE.CanvasTexture(canvas);map.colorSpace=THREE.SRGBColorSpace;map.wrapS=map.wrapT=THREE.RepeatWrapping;map.repeat.setScalar(1/recipe.tile_m);
 return {color:map};
}
