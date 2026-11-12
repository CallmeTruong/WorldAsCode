"""Bounded Google/OSM measured reconstruction experiment, independent of city."""
import argparse
import hashlib
import json
import math
import re
import time
from pathlib import Path
import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright
from shapely.geometry import Polygon,Point
from shapely.ops import unary_union
from building_workflow.config import ROOT
from building_workflow.provider import write_json
from building_workflow.urban.style import canonical_hash
from building_workflow.urban.measured import LocalFrame,sample_plan,compile_surfaces,ground_surfaces,projection_candidates,bake_assignments


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--city',type=Path,required=True);parser.add_argument('--run-id',required=True);parser.add_argument('--reference-url',default='http://127.0.0.1:8767/')
    parser.add_argument('--spacing',type=float,default=2.5);parser.add_argument('--max-adaptive-views',type=int,default=6);args=parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,80}',args.run_id):raise ValueError('RUN_ID')
    if not 1.5<=args.spacing<=8 or not 0<=args.max_adaptive_views<=12:raise ValueError('MEASUREMENT_LIMITS')
    from urllib.parse import urlparse
    url=urlparse(args.reference_url)
    if url.hostname not in ['localhost','127.0.0.1'] or url.scheme!='http' or url.username or url.password or url.query:raise ValueError('LOCAL_SERVICE_REQUIRED')
    run=ROOT/'runs/urban'/args.run_id;run.mkdir(parents=True,exist_ok=True);started=time.monotonic()
    city=json.loads(args.city.read_text(encoding='utf-8'));signature=canonical_hash({'city':city,'spacing':args.spacing,'max_adaptive_views':args.max_adaptive_views,'contract':'measured-global-1'})
    config=run/'measured-config.json'
    if config.exists() and json.loads(config.read_text())['input_hash']!=signature:raise ValueError('INPUT_CHANGED_NEW_RUN_REQUIRED')
    write_json(config,{'input_hash':signature,'provider':'Google Photorealistic 3D Tiles via Cesium ion + OSM','spacing':args.spacing,'max_adaptive_views':args.max_adaptive_views})
    write_json(run/'city.json',city)
    print(json.dumps({'stage':'start','buildings':len(city['buildings'])}),flush=True)
    timings={};views=[];visibility=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1440,'height':1080});page.set_default_timeout(180000);page.goto(args.reference_url.rstrip('/')+'/?sse=8&cache=128')
        for _ in range(120):
            if page.evaluate('()=>window.__GOOGLE_REFERENCE_READY__===true'):break
            if page.evaluate('()=>window.__GOOGLE_REFERENCE_FAILURE__===true'):raise RuntimeError('PROVIDER_CONNECTION')
            page.wait_for_timeout(250)
        page.locator('header').evaluate('(e)=>e.style.display="none"')
        page.evaluate('()=>{tileset.maximumScreenSpaceError=8;}')
        def wait_view():
            stable=0
            for _ in range(100):
                page.wait_for_timeout(200)
                if page.evaluate('()=>tileset.tilesLoaded'):stable+=1
                else:stable=0
                if stable>=3:break
        origin=city['origin'];frame=LocalFrame(origin,0)
        ground_file=run/'ground-evidence.json'
        if ground_file.exists():ground_info=json.loads(ground_file.read_text())
        else:
            occupied=unary_union([Polygon(b['outer'],b['holes']) for b in city['buildings']]);probes=[]
            for road in city['roads']:
                for p in road['points']:
                    if occupied.distance(Point(*p))>3 and len(probes)<25:probes.append(p)
            t=time.monotonic();measured=page.evaluate('p=>sampleEvidenceHeights(p)',frame.lonlat(probes));h=[v['height'] for v in measured if v['height'] is not None]
            if len(h)<3:raise ValueError('GROUND_COVERAGE')
            ground_info={'median_height_m':float(np.median(h)),'samples':measured,'positions':probes};write_json(ground_file,ground_info);timings['ground_sampling']=time.monotonic()-t
        ground=ground_info['median_height_m'];frame=LocalFrame(origin,ground)
        plans=sample_plan(city,args.spacing);samples=[];t=time.monotonic()
        (run/'measurements').mkdir(exist_ok=True)
        for plan in plans:
            path=run/'measurements'/(hashlib.sha256(plan['id'].encode()).hexdigest()[:12]+'.json')
            if path.exists():sample=json.loads(path.read_text())
            else:
                heights=[]
                for offset in range(0,len(plan['points']),400):
                    chunk=plan['points'][offset:offset+400];result=page.evaluate('p=>sampleEvidenceHeights(p)',frame.lonlat(chunk));heights.extend(v['height'] for v in result)
                sample={**plan,'heights':heights};write_json(path,sample)
            samples.append(sample);print(json.dumps({'stage':'sample','id':plan['id'],'samples':len(plan['points'])}),flush=True)
        timings['roof_sampling']=time.monotonic()-t
        t=time.monotonic();raw,audit=compile_surfaces(city,samples,ground);regularized,regular_audit=compile_surfaces(city,samples,ground,True);terrain,bounds=ground_surfaces(city);raw.append(terrain);regularized.append(terrain);timings['numeric_compile']=time.monotonic()-t
        write_json(run/'geometry-audit.json',{'raw':audit,'regularized':regular_audit,'ground_bounds':bounds,'ground_height_m':ground})
        center=[(bounds[0]+bounds[2])/2,(bounds[1]+bounds[3])/2];lon,lat=frame.lonlat([center])[0];span=math.hypot(bounds[2]-bounds[0],bounds[3]-bounds[1]);max_height=max(h['roof_range_m'][1] if h['roof_range_m'] else 0 for h in audit)
        def capture(name,heading,pitch,distance,target,object_id=None,held_out=False):
            cache_path=run/(name+'-view.json');depth_path=run/(name+'-depth.npy')
            if cache_path.exists() and depth_path.exists():
                cached=json.loads(cache_path.read_text())
                if cached['camera']['viewport']==[1440,1080]:
                    views.append(cached);visibility.append(np.load(depth_path,allow_pickle=False).tolist());return
            page.evaluate('p=>{setEvidenceTarget(...p);clipEvidenceFootprint(null);}',target)
            if object_id:
                b=next(b for b in city['buildings'] if b['id']==object_id);ring=Polygon(b['outer'],b['holes']).buffer(2).exterior.coords
                page.evaluate('p=>clipEvidenceFootprint(p)',frame.lonlat(list(ring)[:-1]))
            page.evaluate('p=>setEvidenceView(...p)',[heading,pitch,distance]);wait_view()
            quality=page.evaluate('()=>inspectEvidenceFrame()')
            if not object_id and name!='overhead' and quality['median_surface_distance_m'] and quality['median_surface_distance_m']<distance*.2:
                pitch=-65;page.evaluate('p=>setEvidenceView(...p)',[heading,pitch,distance]);wait_view()
            path=run/(name+'.jpg');page.screenshot(path=str(path),type='jpeg',quality=95,timeout=60000)
            camera=page.evaluate('()=>googleEvidenceStats().camera');stats=page.evaluate('()=>googleEvidenceStats()')
            item={'id':name,'image':path.name,'camera':camera,'local_camera':frame.local_camera(camera),'heading':heading,'pitch':pitch,'range':distance,'object_id':object_id,'held_out':held_out,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'stats':{k:v for k,v in stats.items() if k!='camera'}}
            views.append(item)
            if held_out:
                empty=np.full((sum(len(p['faces']) for p in raw),3),float('nan'));visibility.append(empty.tolist());np.save(depth_path,empty);write_json(cache_path,item);return
            candidate=projection_candidates(raw,frame,camera);ids=np.flatnonzero(candidate['valid']);uv=candidate['uv'][ids]
            queries=[[int(i),float(p[0]*1440),float(p[1]*1080)] for i,p in zip(ids,uv)]
            hit=np.full((len(candidate['faces']),3),float('nan'));t=time.monotonic()
            for offset in range(0,len(queries),1500):
                values=page.evaluate('''rows=>rows.map(([i,x,y])=>{const p=viewer.scene.pickPosition(new Cesium.Cartesian2(x,y));return p?[i,p.x,p.y,p.z]:[i,null,null,null];})''',queries[offset:offset+1500])
                for row in values:
                    if row[1] is not None:hit[row[0]]=row[1:]
            visibility.append(hit.tolist());np.save(depth_path,hit);item['depth_queries']=len(queries);item['depth_seconds']=time.monotonic()-t
            write_json(cache_path,item)
            print(json.dumps({'stage':'view','name':name,'depth_queries':len(queries),'depth_seconds':round(item['depth_seconds'],2)}),flush=True)
        t=time.monotonic()
        for name,h,p in [('overhead',0,-89.8),('south',0,-38),('west',90,-38),('north',180,-38),('east',270,-38)]:
            capture(name,h,p,max(span*1.05,max_height*2),[lon,lat,ground+max_height*.25])
        timings['common_capture']=time.monotonic()-t
        # Ask for additional evidence only when depth-supported appearance is missing.
        used={};t=time.monotonic()
        for index in range(args.max_adaptive_views):
            _,coverage=bake_assignments(raw,frame,views,visibility);candidates=[c for c in coverage if c['id']!='ground' and c['projected_area_coverage']<.9 and used.get(c['id'],0)<3]
            if not candidates:break
            worst=min(candidates,key=lambda c:c['projected_area_coverage']);identifier=worst['id'];b=next(b for b in city['buildings'] if b['id']==identifier);poly=Polygon(b['outer'],b['holes']);x0,z0,x1,z1=poly.bounds
            # Choose complementary sides deterministically; the trigger is measured
            # coverage, not a mandatory camera count for every building.
            count=used.get(identifier,0);heading=[45,225,135][count];used[identifier]=count+1
            lonb,latb=frame.lonlat([b['center']])[0];h=next(a for a in audit if a['id']==identifier)['roof_range_m'];height=h[1] if h else b['height']
            capture('adaptive-'+str(index),heading,-15,max(75,math.hypot(x1-x0,z1-z0)*1.2,height*.85),[lonb,latb,ground+height*.48],identifier)
        timings['adaptive_capture']=time.monotonic()-t
        # A new angle is reserved for validation, never used as an appearance map.
        capture('validation',67,-48,max(span*1.05,max_height*2),[lon,lat,ground+max_height*.25],held_out=True)
        browser.close()
    t=time.monotonic();variants={};coverage={}
    for name,parts in [('measured',raw),('regularized',regularized)]:
        groups,report=bake_assignments(parts,frame,views,visibility);variants[name]=groups;coverage[name]=report
    timings['projection_compile']=time.monotonic()-t;timings['total_seconds']=time.monotonic()-started
    clean_visibility=[np.asarray(v).tolist() for v in visibility] # missing depth stored separately as null
    for values in clean_visibility:
        for point in values:
            for i,v in enumerate(point):
                if not math.isfinite(v):point[i]=None
    write_json(run/'visibility.json',clean_visibility)
    write_json(run/'source-views.json',{'provider':'Google Photorealistic 3D Tiles via Cesium ion','views':views,'ground_height_m':ground,'origin':origin})
    write_json(run/'measured-scene.json',{'provider':'Google Photorealistic 3D Tiles / OSM','representation':'sampled roof-field and polygon-wall reconstruction; depth-tested projected captured appearance, not intrinsic PBR','city':city,'bounds':bounds,'views':views,'variants':variants,'coverage':coverage,'ground_height_m':ground})
    write_json(run/'measured-result.json',{'status':'experimental','timings':timings,'samples':sum(len(s['points']) for s in samples),'model_calls':0,'coverage':coverage,'adaptive_views':sum(used.values()),'limitations':['Height fields do not recover undercuts or facade relief. Source imagery contains baked lighting and source blur. Footprint/source registration may differ. Unknown projections remain explicit fallback. No global optimum claimed.']})
    print(json.dumps({'stage':'complete','timings':timings,'coverage':coverage}),flush=True)


if __name__=='__main__':main()
