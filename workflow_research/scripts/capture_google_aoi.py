"""Bounded multi-view capture and optional approximate canopy observation for any AOI."""
import argparse
import hashlib
import json
from pathlib import Path
import time
from playwright.sync_api import sync_playwright
from building_workflow.provider import Provider,write_json
from building_workflow.config import Settings


def main():
    p=argparse.ArgumentParser();p.add_argument('--url',default='http://127.0.0.1:8767/');p.add_argument('--output',type=Path,required=True)
    p.add_argument('--longitude',type=float,required=True);p.add_argument('--latitude',type=float,required=True);p.add_argument('--height',type=float,default=20)
    p.add_argument('--pitch',type=float,default=-25);p.add_argument('--range',type=float,default=180);p.add_argument('--trees',action='store_true');p.add_argument('--overhead-only',action='store_true')
    p.add_argument('--city',type=Path);p.add_argument('--object-id',help='Isolate an OSM footprint in 3D Tiles to avoid neighboring-building occlusion')
    args=p.parse_args();run=args.output;run.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True,chromium_sandbox=True)
        page=browser.new_page(viewport={'width':1440,'height':1080});page.set_default_timeout(60000)
        page.goto(args.url,wait_until='load')
        for _ in range(100):
            if page.evaluate('()=>!!window.__GOOGLE_REFERENCE_READY__'):break
            if page.evaluate('()=>!!window.__GOOGLE_REFERENCE_FAILURE__'):raise RuntimeError('GOOGLE_REFERENCE_CONNECTION_FAILED')
            page.wait_for_timeout(300)
        else:raise RuntimeError('GOOGLE_REFERENCE_START_TIMEOUT')
        page.locator('header').evaluate('el=>el.style.display="none"')
        page.evaluate('p=>window.setEvidenceTarget(...p)',[args.longitude,args.latitude,args.height])
        if args.city and args.object_id:
            from pyproj import Transformer
            from shapely.geometry import Polygon
            city=json.loads(args.city.read_text(encoding='utf-8'));building=next(b for b in city['buildings'] if b['id']==args.object_id)
            project=Transformer.from_crs('EPSG:4326',city['origin']['projection'],always_xy=True);ex,ny=project.transform(city['origin']['longitude'],city['origin']['latitude'])
            inverse=Transformer.from_crs(city['origin']['projection'],'EPSG:4326',always_xy=True)
            ring=list(Polygon(building['outer']).buffer(2).exterior.coords)[:-1]
            page.evaluate('p=>window.clipEvidenceFootprint(p)',[inverse.transform(ex+x,ny-z) for x,z in ring])
        views=[('north',0,args.pitch),('east',90,args.pitch),('south',180,args.pitch),('west',270,args.pitch),('overhead',0,-89.8)]
        if args.overhead_only:views=views[-1:]
        metadata=[]
        for name,heading,pitch in views:
            page.evaluate('p=>window.setEvidenceView(...p)',[heading,pitch,args.range])
            for _ in range(80):
                page.wait_for_timeout(250);stats=page.evaluate('window.googleEvidenceStats()')
                if stats['tilesLoaded'] and stats['tileLoads']>0:break
            frame=page.evaluate('window.inspectEvidenceFrame()');adapted=False
            if frame['median_surface_distance_m'] is not None and frame['median_surface_distance_m']<args.range*.2 and name!='overhead':
                pitch=min(pitch,-60);page.evaluate('p=>window.setEvidenceView(...p)',[heading,pitch,args.range]);adapted=True
                for _ in range(60):
                    page.wait_for_timeout(250)
                    if page.evaluate('window.googleEvidenceStats().tilesLoaded'):break
                frame=page.evaluate('window.inspectEvidenceFrame()')
            path=run/(name+'.png');page.screenshot(path=str(path),timeout=45000)
            metadata.append({'view':name,'heading_deg':heading,'pitch_deg':pitch,'range_m':args.range,'depth_quality':frame,'adapted_for_occlusion':adapted,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'stats':page.evaluate('window.googleEvidenceStats()')})
            print(json.dumps({'captured':name,'selected_tiles':stats['selectedTiles']}),flush=True)
        write_json(run/'capture-manifest.json',{'target':{'longitude':args.longitude,'latitude':args.latitude,'height':args.height},'views':metadata,
            'source':'Google Photorealistic 3D Tiles via Cesium ion','isolated_object_id':args.object_id,
            'uncertainty':'Rendered photogrammetry; clipping uses an approximate OSM footprint. Occlusion, texture artifacts, acquisition age and mesh error remain. View names indicate camera heading, not verified building face identity.'})
        if args.trees:
            api=Provider(Settings.load(),run,max_calls=2,max_tokens=35000,max_seconds=300)
            observations=api.call('overhead-tree-crowns',
                'Inspect this real rendered overhead urban scene. Identify individual tree CANOPY centers, including autumn yellow/brown trees. Exclude cars, shadows, roof HVAC and grass. Return JSON {crowns:[{id:string,x:number,y:number,radius_px:number,confidence:number}],uncertainty:[strings]}. x,y are NORMALIZED image coordinates 0..1, origin top left. Mark only visible trees, no invented filling. Max 70 centers. Radius estimated in pixels. This is oblique photogrammetry at almost top-down, not a surveyed orthophoto; exact trunk positions and species are unknown. No style colors or forced tree shapes.',
                [run/'overhead.png'],api.settings.vision_model,5000)
            candidates=[]
            for c in observations.get('crowns',[])[:70]:
                if not isinstance(c.get('x'),(int,float)) or not isinstance(c.get('y'),(int,float)) or not 0<=c['x']<=1 or not 0<=c['y']<=1:continue
                if c.get('confidence',0)<.6:continue
                point=page.evaluate('p=>window.inspectEvidencePoint(...p)',[c['x']*1440,c['y']*1080])
                if point:candidates.append({**c,**point,'position_evidence':'VLM canopy center + pickPosition on rendered 3D tile mesh; approximate trunk XY','position_uncertainty_m':5})
            write_json(run/'tree-crown-candidates.json',{'source_image':'overhead.png','image_sha256':hashlib.sha256((run/'overhead.png').read_bytes()).hexdigest(),'crowns':candidates,'uncertainty':observations.get('uncertainty',[]),'not_surveyed':True})
            api.save_usage();print(json.dumps({'tree_candidates':len(candidates)}),flush=True)
        browser.close()


if __name__=='__main__':main()
