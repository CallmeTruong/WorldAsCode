// Synthetic, seeded material channels. Tiles are measured in metres via UVs;
// these are authored surfaces, never recovered source PBR.
import * as THREE from 'three';

function random(seed) {
  let s = 2166136261;
  for (const c of String(seed)) s = Math.imul(s ^ c.charCodeAt(0), 16777619);
  return () => { s += 0x6D2B79F5; let t = Math.imul(s ^ s >>> 15, 1 | s); t ^= t + Math.imul(t ^ t >>> 7, 61 | t); return ((t ^ t >>> 14) >>> 0) / 4294967296; };
}
function texture(canvas, colour, scale) {
  const t = new THREE.CanvasTexture(canvas);
  t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(1 / scale, 1 / scale);
  t.anisotropy = 8;
  if (colour) t.colorSpace = THREE.SRGBColorSpace;
  return t;
}
export function surfaceMaps(color, surface, seed = 0) {
  const size = 512, type = surface.type, tileMetres = surface.scale ?? 2.4;
  if (!(tileMetres > 0)) throw Error('KIT_INVALID_SURFACE_SCALE');
  const canvases = Array.from({length: 3}, () => { const c = document.createElement('canvas'); c.width = c.height = size; return c; });
  const [a, h, r] = canvases.map(c => c.getContext('2d'));
  const rng = random(seed), base = new THREE.Color(color), secondary = new THREE.Color(surface.color2 ?? color);
  if(['asphalt','concrete','bark','foliage','soil'].includes(type)){
    a.fillStyle='#'+base.getHexString();a.fillRect(0,0,size,size);
    h.fillStyle='#888';h.fillRect(0,0,size,size);r.fillStyle='#ddd';r.fillRect(0,0,size,size);
    if(type==='foliage'){
      a.clearRect(0,0,size,size);a.fillStyle='#'+base.getHexString();
      const leaf=new Path2D();leaf.moveTo(256,18);leaf.bezierCurveTo(490,160,420,365,256,494);leaf.bezierCurveTo(80,360,35,165,256,18);a.fill(leaf);
      a.save();a.clip(leaf);const gradient=a.createLinearGradient(90,0,410,0);gradient.addColorStop(0,'rgba(0,0,0,.20)');gradient.addColorStop(.5,'rgba(255,255,255,.10)');gradient.addColorStop(1,'rgba(0,0,0,.05)');a.fillStyle=gradient;a.fillRect(0,0,size,size);
      a.strokeStyle='#'+base.clone().multiplyScalar(1.22).getHexString();a.lineWidth=3;a.beginPath();a.moveTo(256,470);a.lineTo(256,55);a.stroke();
      for(let y=110;y<460;y+=45)for(const s of [-1,1]){a.lineWidth=1.2;a.beginPath();a.moveTo(256,y+25);a.quadraticCurveTo(256+s*55,y,256+s*(120-Math.abs(y-250)*.22),y-30);a.stroke();}a.restore();
      const alpha=document.createElement('canvas');alpha.width=alpha.height=size;const c=alpha.getContext('2d');c.fillStyle='#000';c.fillRect(0,0,size,size);c.fillStyle='#fff';c.fill(leaf);
      if(surface.cluster){
        const original=document.createElement('canvas');original.width=original.height=size;original.getContext('2d').drawImage(canvases[0],0,0);
        a.clearRect(0,0,size,size);c.fillStyle='#000';c.fillRect(0,0,size,size);
        for(let j=0;j<5;j++)for(const side of [-1,1]){
          const y=100+j*73,angle=side*(.64+rng()*.15),scale=.30+rng()*.06;
          a.save();a.translate(256,y);a.rotate(angle);a.scale(scale,scale);a.translate(-256,-475);a.drawImage(original,0,0);a.restore();
          c.save();c.translate(256,y);c.rotate(angle);c.scale(scale,scale);c.translate(-256,-475);c.fillStyle='#fff';c.fill(leaf);c.restore();
        }
        for(const context of [a,c]){context.strokeStyle=context===c?'#fff':'#'+base.clone().multiplyScalar(.55).getHexString();context.lineWidth=4;context.beginPath();context.moveTo(256,490);context.lineTo(256,55);context.stroke();}
      }
      return {map:texture(canvases[0],true,1),bumpMap:texture(canvases[1],false,1),roughnessMap:texture(canvases[2],false,1),alphaMap:texture(alpha,false,1)};
    }
    const image=a.getImageData(0,0,size,size),height=h.getImageData(0,0,size,size),rough=r.getImageData(0,0,size,size);
    for(let i=0;i<image.data.length;i+=4){const noise=rng(),delta=(noise-.5)*(type==='asphalt'?15:9);for(let k=0;k<3;k++)image.data[i+k]+=delta;const v=100+noise*55;for(let k=0;k<3;k++){height.data[i+k]=v;rough.data[i+k]=190+noise*50;}}
    a.putImageData(image,0,0);h.putImageData(height,0,0);r.putImageData(rough,0,0);
    if(type==='bark'){
      for(let x=-10;x<size+15;x+=7+rng()*14){a.strokeStyle='#'+base.clone().multiplyScalar(.65+rng()*.3).getHexString();h.strokeStyle='#444';a.lineWidth=1+rng()*4;h.lineWidth=a.lineWidth;
        for(const c of [a,h]){c.beginPath();c.moveTo(x,0);c.bezierCurveTo(x+12,170,x-10,320,x+5,size);c.stroke();}}
    }
    if(type==='concrete'){
      const spacing=size/(tileMetres/(surface.unit_m??.6));for(const c of [a,h]){c.strokeStyle=c===a?'#'+base.clone().multiplyScalar(.65).getHexString():'#555';c.lineWidth=Math.max(1,size/tileMetres*.004);
        for(let x=0;x<size;x+=spacing){c.beginPath();c.moveTo(x,0);c.lineTo(x,size);c.moveTo(0,x);c.lineTo(size,x);c.stroke();}}
    }
    if(type==='asphalt'&&surface.cracks){for(let i=0;i<4;i++){a.strokeStyle='#'+base.clone().multiplyScalar(.65).getHexString();h.strokeStyle='#444';for(const c of [a,h]){c.lineWidth=1;c.beginPath();let x=rng()*size,y=rng()*size;c.moveTo(x,y);for(let j=0;j<6;j++){x+=(rng()-.5)*45;y+=10+rng()*20;c.lineTo(x,y);}c.stroke();}}}
    return {map:texture(canvases[0],true,tileMetres),bumpMap:texture(canvases[1],false,tileMetres),roughnessMap:texture(canvases[2],false,tileMetres)};
  }
  a.fillStyle = '#' + base.clone().multiplyScalar(.73).getHexString(); a.fillRect(0, 0, size, size);
  h.fillStyle = '#444'; h.fillRect(0, 0, size, size);
  r.fillStyle = '#ddd'; r.fillRect(0, 0, size, size);
  // Physical tile size controls course count, rather than squeezing a fixed
  // eight courses into a fraction of a metre.
  const course = surface.course_m ?? (type === 'brick' ? .075 : type === 'slate' ? .24 : .6);
  const rows = Math.max(1, Math.round(tileMetres / course));
  const cols = Math.max(1, Math.round(tileMetres / (surface.unit_width_m ?? (type === 'brick' ? .23 : type === 'slate' ? .32 : .8))));
  const ch = size / rows, cw = size / cols;
  for (let row = 0; row < rows; row++) for (let col = -1; col <= cols; col++) {
    const x = (col + (row % 2) / 2) * cw, y = row * ch, gap = type === 'brick' ? Math.max(.8, size / tileMetres * .008) : 1;
    const value = .89 + rng() * .2;
    a.fillStyle = '#' + base.clone().lerp(secondary, rng() * .22).multiplyScalar(value).getHexString();
    a.fillRect(x + gap, y + gap, cw - gap, ch - gap);
    h.fillStyle = type === 'slate' ? `rgb(${180 + row % 2 * 20},${180 + row % 2 * 20},${180 + row % 2 * 20})` : '#ccc';
    h.fillRect(x + gap, y + gap, cw - gap, ch - gap);
    const rough = Math.round(185 + rng() * 45); r.fillStyle = `rgb(${rough},${rough},${rough})`;
    r.fillRect(x + gap, y + gap, cw - gap, ch - gap);
  }
  // Low amplitude pore variation at an independent frequency, without random
  // colour speckles dominating the architecture.
  const image = a.getImageData(0, 0, size, size);
  for (let i = 0; i < image.data.length; i += 4) {
    const delta = (rng() - .5) * 5;
    for (let c = 0; c < 3; c++) image.data[i + c] += delta;
  }
  a.putImageData(image, 0, 0);
  return {map: texture(canvases[0], true, tileMetres), bumpMap: texture(canvases[1], false, tileMetres), roughnessMap: texture(canvases[2], false, tileMetres)};
}

export function metricUVs(geometry) {
  const p = geometry.attributes.position, n = geometry.attributes.normal;
  if (!p || !n) return geometry;
  const uv = [];
  for (let i = 0; i < p.count; i++) {
    const nx = Math.abs(n.getX(i)), ny = Math.abs(n.getY(i)), nz = Math.abs(n.getZ(i));
    uv.push(nx > ny && nx > nz ? p.getZ(i) : p.getX(i), ny >= nx && ny >= nz ? p.getZ(i) : p.getY(i));
  }
  geometry.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
  return geometry;
}
