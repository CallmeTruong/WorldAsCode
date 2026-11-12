"""Bounded provider capture for held-out buildings through the SDK viewer.

No provider token enters the evidence bundle or application prompts.
"""

import math
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from . import georef, massing
from .artifacts import file_hash, write_json


def capture_site(osm, way, out, height, url='http://127.0.0.1:8767/'):
    out=Path(out)
    if out.exists():
        raise ValueError('USE_NEW_EVIDENCE_DIRECTORY')
    out.mkdir(parents=True)
    ring,tags=georef.osm_way(osm,way)
    lon,lat=georef.centroid(ring)
    frame=georef.Frame(lon,lat)
    plan=[[p[0],-p[2]] for p in (frame.model(*p) for p in ring)]
    if georef.area(plan)<0:
        plan.reverse()
    grown=massing.offset(plan,-1.0) or plan
    def unproject(x,n):
        return [lon+math.degrees(x/frame.east_radius),lat+math.degrees(n/frame.north_radius)]
    clipping=[unproject(x,n) for x,n in grown]
    span=max(math.hypot(x,n) for x,n in plan)*2
    distance=max(90,span*1.35,height*2.3)
    captures=out/'captures'
    captures.mkdir()
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1080})
        page.set_default_timeout(120000)
        page.goto(url+'?sse=3&cache=256',wait_until='load')
        page.wait_for_function('() => window.__GOOGLE_REFERENCE_READY__ || window.__GOOGLE_REFERENCE_FAILURE__',timeout=60000)
        if page.evaluate('!!window.__GOOGLE_REFERENCE_FAILURE__'):
            raise RuntimeError('PROVIDER_CONNECTION_FAILED')
        # The SDK otherwise follows wall-clock time: night captures introduce
        # blue lighting and a star field unrelated to the source materials.
        page.evaluate('lon=>{viewer.clock.currentTime=Cesium.JulianDate.addSeconds(Cesium.JulianDate.fromIso8601("2026-06-21T12:00:00Z"),-lon*240,new Cesium.JulianDate());viewer.clock.shouldAnimate=false;viewer.scene.skyBox.show=false;viewer.scene.sun.show=false;viewer.scene.moon.show=false;viewer.scene.backgroundColor=Cesium.Color.BLACK;viewer.scene.requestRender();}',lon)
        page.locator('header').evaluate('el=>el.style.display="none"')
        page.evaluate('p=>window.setEvidenceTarget(...p)',[lon,lat,height/2])
        page.evaluate('p=>window.setEvidenceView(...p)',[0,-55,distance*1.3])
        # Surrounding samples estimate ground; record all samples, never claim survey.
        outer=massing.offset(plan,-9) or plan
        samples=page.evaluate('p=>window.sampleEvidenceHeights(p)',[unproject(x,n) for x,n in outer])
        values=sorted(s['height'] for s in samples if s.get('height') is not None and math.isfinite(s['height']))
        if len(values)<2:
            raise RuntimeError('INSUFFICIENT_GROUND_SAMPLES')
        ground=sum(values[:2])/2
        target={'longitude':lon,'latitude':lat,'height':ground+height*.48}
        page.evaluate('p=>window.setEvidenceTarget(p.longitude,p.latitude,p.height)',target)
        page.evaluate('p=>window.clipEvidenceFootprint(p)',clipping)
        views=[]
        for name,heading,pitch in [('north',0,-25),('east',90,-25),('south',180,-25),('west',270,-25),('overhead',0,-89.8)]:
            page.evaluate('p=>window.setEvidenceView(...p)',[heading,pitch,distance])
            deadline=time.monotonic()+120
            stable=0
            while time.monotonic()<deadline:
                page.wait_for_timeout(350)
                stats=page.evaluate('window.googleEvidenceStats()')
                stable=stable+1 if stats['tilesLoaded'] and stats['selectedTiles']>0 else 0
                if stable>=3:
                    break
            if stable<3:
                raise RuntimeError('CAPTURE_TILES_NOT_READY:'+name)
            path=captures/(name+'.png')
            page.screenshot(path=str(path))
            views.append({'view':name,'heading_deg':heading,'pitch_deg':pitch,'range_m':distance,
                          'sha256':file_hash(path),'stats':stats})
            print('captured '+str(way)+' '+name,flush=True)
        browser.close()
    manifest={'target':target,'views':views,'source':'Google Photorealistic 3D Tiles via Cesium ion',
              'lighting':'Fixed approximate local solar noon on June solstice; black sky, no star field',
              'ground_samples':samples,'ground_estimate_m':ground,'osm_sha256':file_hash(osm),
              'uncertainty':'Ground: mean of lowest two surrounding mesh samples, not surveyed. OSM footprint approximate. Clipping may retain adjacent/overhanging surfaces; inspect all views.'}
    write_json(captures/'capture-manifest.json',manifest)
    result=georef.build_evidence(out,ring,manifest,captures,ground,height,'way/'+str(way),
        tags.get('name:en',tags.get('name','')),tags,
        height_source='OSM height or explicit benchmark prior; refit against calibrated views')
    return result


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--osm',type=Path,required=True)
    parser.add_argument('--way',required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--height',type=float,required=True)
    parser.add_argument('--url',default='http://127.0.0.1:8767/')
    args=parser.parse_args()
    try:
        capture_site(args.osm,args.way,args.out,args.height,args.url)
    except Exception as exc:
        write_json(args.out/'failure.json',{'status':'capture-failed','error':str(exc),
                   'way':args.way,'note':'No evidence bundle admitted; partial images are not accepted as a complete capture.'})
        raise
