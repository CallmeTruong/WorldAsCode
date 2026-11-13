let viewer,tileset,configuration;
const evidence={tileLoads:0,tileFailures:0,renderErrors:0,selectedTiles:0,tilesLoaded:false};
window.googleEvidenceStats=()=>({...evidence,tilesLoaded:tileset?.tilesLoaded||false,selectedTiles:tileset?._selectedTiles?.length||0,
  source:'Google Photorealistic 3D Tiles via Cesium ion',sdk:Cesium.VERSION,
  camera:viewer?{longitude:Cesium.Math.toDegrees(viewer.camera.positionCartographic.longitude),latitude:Cesium.Math.toDegrees(viewer.camera.positionCartographic.latitude),height:viewer.camera.positionCartographic.height,position_ecef:[viewer.camera.positionWC.x,viewer.camera.positionWC.y,viewer.camera.positionWC.z],direction_ecef:[viewer.camera.directionWC.x,viewer.camera.directionWC.y,viewer.camera.directionWC.z],up_ecef:[viewer.camera.upWC.x,viewer.camera.upWC.y,viewer.camera.upWC.z],view_matrix:Cesium.Matrix4.toArray(viewer.camera.viewMatrix),projection_matrix:Cesium.Matrix4.toArray(viewer.camera.frustum.projectionMatrix),viewport:[viewer.canvas.width,viewer.canvas.height],fov_vertical_deg:Cesium.Math.toDegrees(viewer.camera.frustum.fovy),origin:{longitude:configuration.longitude,latitude:configuration.latitude,height:0}}:null});
window.setEvidenceView=(heading=0,pitch=-30,range=260)=>{
 const center=Cesium.Cartesian3.fromDegrees(configuration.longitude,configuration.latitude,configuration.target_height||15);
 viewer.camera.lookAt(center,new Cesium.HeadingPitchRange(Cesium.Math.toRadians(heading),Cesium.Math.toRadians(pitch),range));
 viewer.camera.lookAtTransform(Cesium.Matrix4.IDENTITY);viewer.scene.requestRender();
};
window.inspectEvidencePoint=(x,y)=>{
 const point=viewer.scene.pickPosition(new Cesium.Cartesian2(x,y));if(!point)return null;
 const c=Cesium.Cartographic.fromCartesian(point);return {longitude:Cesium.Math.toDegrees(c.longitude),latitude:Cesium.Math.toDegrees(c.latitude),height:c.height,evidence:'picked streamed mesh position; not surveyed ground/tree trunk'};
};
window.inspectEvidenceFrame=()=>{
 const distances=[];for(const [u,v] of [[.5,.5],[.3,.5],[.7,.5],[.5,.3],[.5,.7]]){
  const p=viewer.scene.pickPosition(new Cesium.Cartesian2(u*viewer.canvas.clientWidth,v*viewer.canvas.clientHeight));
  if(p)distances.push(Cesium.Cartesian3.distance(p,viewer.camera.positionWC));
 }
 distances.sort((a,b)=>a-b);return {sample_count:distances.length,median_surface_distance_m:distances.length?distances[Math.floor(distances.length/2)]:null,
  note:'Depth-based occlusion heuristic, not a semantic or visual quality acceptance.'};
};
window.setEvidenceTarget=(longitude,latitude,height=15)=>{configuration.longitude=longitude;configuration.latitude=latitude;configuration.target_height=height;};
window.configureEvidenceCapture=(options)=>{
 viewer.clock.currentTime=Cesium.JulianDate.addSeconds(Cesium.JulianDate.fromIso8601(options.solarNoonDate+'T12:00:00Z'),-configuration.longitude*240,new Cesium.JulianDate());
 viewer.clock.shouldAnimate=false;viewer.scene.skyBox.show=false;viewer.scene.sun.show=false;viewer.scene.moon.show=false;
 viewer.scene.backgroundColor=Cesium.Color.BLACK;viewer.scene.requestRender();
};
window.clipEvidenceFootprint=(coordinates)=>{
 if(!coordinates){if(tileset.clippingPolygons)tileset.clippingPolygons.enabled=false;return;}
 tileset.clippingPolygons=new Cesium.ClippingPolygonCollection({polygons:[new Cesium.ClippingPolygon({positions:Cesium.Cartesian3.fromDegreesArray(coordinates.flat())})],inverse:true});
 viewer.scene.requestRender();
};
// Surface positions under a pixel grid of the current frame, read from the depth buffer.
// Returns flat [longitude, latitude, height, ...] in degrees and metres; far faster than
// most-detailed height sampling when a whole area is needed.
window.pickEvidenceGrid=(step=4,x0=0,y0=0,x1=null,y1=null)=>{
 viewer.scene.render();const w=x1??viewer.canvas.clientWidth,h=y1??viewer.canvas.clientHeight,out=[];
 for(let y=y0+step/2;y<h;y+=step)for(let x=x0+step/2;x<w;x+=step){
  const p=viewer.scene.pickPosition(new Cesium.Cartesian2(x,y));if(!p)continue;
  const c=Cesium.Cartographic.fromCartesian(p);if(!Number.isFinite(c.height))continue;
  out.push(Cesium.Math.toDegrees(c.longitude),Cesium.Math.toDegrees(c.latitude),c.height);}
 return out;
};
window.sampleEvidenceHeights=async(points)=>{
 const samples=points.map(p=>Cesium.Cartographic.fromDegrees(p[0],p[1]));
 const values=await viewer.scene.sampleHeightMostDetailed(samples);
 return values.map((p,i)=>({longitude:points[i][0],latitude:points[i][1],height:Number.isFinite(p.height)?p.height:null,evidence:'streamed mesh surface height, not survey'}));
};
(async()=>{try{
 configuration=await (await fetch('/config',{cache:'no-store'})).json();
 Cesium.Ion.defaultAccessToken=configuration.ionToken;
 viewer=new Cesium.Viewer('scene',{globe:false,geocoder:false,baseLayerPicker:false,baseLayer:false,animation:false,timeline:false,sceneModePicker:false,
  homeButton:false,navigationHelpButton:false,fullscreenButton:false,selectionIndicator:false,infoBox:false,showRenderLoopErrors:false,
  requestRenderMode:true,maximumRenderTimeChange:Infinity});
 viewer.scene.renderError.addEventListener(()=>evidence.renderErrors++);
 const query=new URLSearchParams(location.search),sse=Math.min(16,Math.max(2,Number(query.get('sse'))||4)),cacheMB=Math.min(512,Math.max(64,Number(query.get('cache'))||512));
 tileset=await Cesium.createGooglePhotorealistic3DTileset({maximumScreenSpaceError:sse,cacheBytes:cacheMB*1024*1024,maximumCacheOverflowBytes:cacheMB*1024*1024/2});viewer.scene.primitives.add(tileset);
 tileset.tileLoad.addEventListener(()=>{evidence.tileLoads++;});tileset.tileFailed.addEventListener(()=>{evidence.tileFailures++;});
 viewer.scene.frameState?.creditDisplay?.addStaticCredit(new Cesium.Credit('Google Maps'));
 window.setEvidenceView(270,-35,300);window.__GOOGLE_REFERENCE_READY__=true;
 document.getElementById('status').textContent='Connected. Inspecting local coverage / loading tiles.';
 document.querySelectorAll('[data-h]').forEach(b=>b.onclick=()=>window.setEvidenceView(Number(b.dataset.h)));
 document.getElementById('top').onclick=()=>window.setEvidenceView(0,-89,370);
 setInterval(()=>{const s=window.googleEvidenceStats();document.getElementById('status').textContent=`${s.tileLoads} tiles loaded / ${s.selectedTiles} selected / ${s.tileFailures} failed`;},1000);
}catch(error){document.getElementById('status').textContent='Connection failed; check token permissions or provider availability.';window.__GOOGLE_REFERENCE_FAILURE__=true;}})();
