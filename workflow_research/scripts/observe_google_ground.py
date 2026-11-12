"""Observe shared overhead street evidence once; retain approximate mesh-projected extents."""
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright
from building_workflow.provider import Provider,write_json
from building_workflow.config import Settings


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--longitude',type=float,required=True);p.add_argument('--latitude',type=float,required=True);p.add_argument('--url',default='http://127.0.0.1:8767/');p.add_argument('--style-image',type=Path);p.add_argument('--ground-height',type=float,default=0);p.add_argument('--range',type=float,default=370)
    args=p.parse_args();run=args.output;run.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1440,'height':1080});page.goto(args.url)
        for _ in range(100):
            if page.evaluate('()=>window.__GOOGLE_REFERENCE_READY__===true'):break
            page.wait_for_timeout(300)
        page.evaluate('p=>setEvidenceTarget(...p)',[args.longitude,args.latitude,args.ground_height]);page.evaluate('r=>setEvidenceView(0,-89.8,r)',args.range)
        for _ in range(100):
            page.wait_for_timeout(300)
            if page.evaluate('()=>googleEvidenceStats().tilesLoaded'):break
        page.locator('header').evaluate('(e)=>e.style.display="none"')
        photo=run/'overhead.png';page.screenshot(path=str(photo),timeout=45000)
        api=Provider(Settings.load(),run,max_calls=2,max_tokens=50000,max_seconds=300)
        images=[photo]+([args.style_image] if args.style_image else [])
        prompt='''First image is FACTUAL Tokyo overhead 3D Tiles. Optional second image is artistic STYLE only. Identify clearly visible zebra crossing extents, at most 12. Return JSON {crosswalks:[{id:string,corners:[[x,y],[x,y],[x,y],[x,y]],confidence:0..1}],surface_materials:{road:{albedo_multiplier:0.1..1,evidence:string},pavement:{albedo_multiplier:0.1..1,evidence:string}},tree_cluster_detail:1..4,uncertainty:[strings]}. Coordinates normalized 0..1, top-left origin, first image only. Four corners ordered p0->p1 along WALKING direction across roadway, p1->p2 across the crossing width, p2->p3 back along crossing, then close. Mark only actual visible crossings, no inferred filling. Surface multipliers adjust a generic light asphalt/paving scan to the intrinsic material appearance; avoid cast shadows, keep road and pavement distinct, do not copy a style palette. These are uncertain visual estimates, not calibrated reflectance. Tree cluster detail describes how finely canopy clusters should be subdivided for the desired style, not species, colors or new positions.'''
        raw=api.call('shared-ground-observe',prompt,images,api.settings.vision_model,4500)
        projected=[]
        for feature in raw.get('crosswalks',[])[:12]:
            ring=feature.get('corners',[])
            if len(ring)!=4 or any(len(p)!=2 or any(not isinstance(v,(int,float)) or not 0<=v<=1 for v in p) for p in ring):continue
            hits=[page.evaluate('p=>inspectEvidencePoint(...p)',[x*1440,y*1080]) for x,y in ring]
            if all(hits):projected.append({**feature,'lonlat':[[h['longitude'],h['latitude']] for h in hits]})
        raw['crosswalks']=projected;raw['camera']=page.evaluate('()=>googleEvidenceStats().camera');raw['source']='Google 3D Tiles overhead + VLM observations, not survey'
        write_json(run/'ground-observations.json',raw);api.save_usage();browser.close();print('Projected crosswalk candidates: '+str(len(projected)))


if __name__=='__main__':main()
