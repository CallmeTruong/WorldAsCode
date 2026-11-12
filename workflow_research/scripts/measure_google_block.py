"""Bounded roof/road height evidence; samples are photogrammetric, not surveyed."""
import argparse
import json
from pathlib import Path
from statistics import median
from pyproj import Transformer
from shapely.geometry import Polygon,Point
from shapely.ops import unary_union
from playwright.sync_api import sync_playwright
from building_workflow.provider import write_json


def main():
    p=argparse.ArgumentParser();p.add_argument('--city',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--url',default='http://127.0.0.1:8767/')
    args=p.parse_args();city=json.loads(args.city.read_text(encoding='utf-8'))
    origin=city['origin'];forward=Transformer.from_crs(4326,origin['projection'],always_xy=True);ex,ny=forward.transform(origin['longitude'],origin['latitude']);back=Transformer.from_crs(origin['projection'],4326,always_xy=True)
    polygons={b['id']:Polygon(b['outer'],b['holes']) for b in city['buildings']};occupied=unary_union(list(polygons.values()))
    probes=[]
    for road in city['roads']:
        for x,z in road['points']:
            if len(probes)>=20:break
            if occupied.distance(Point(x,z))>3:probes.append({'kind':'ground','position':[x,z]})
    for identifier,poly in polygons.items():
        inside=poly.buffer(-2)
        if inside.is_empty:inside=poly
        points=[inside.representative_point()];a,b,c,d=inside.bounds
        for u,v in [(0.25,.25),(.75,.25),(.25,.75),(.75,.75),(.5,.5)]:
            q=Point(a+(c-a)*u,b+(d-b)*v)
            if inside.contains(q):points.append(q)
        probes.extend({'kind':'roof','object_id':identifier,'position':[q.x,q.y]} for q in points[:6])
    coordinates=[back.transform(ex+q['position'][0],ny-q['position'][1]) for q in probes]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True);page=browser.new_page();page.goto(args.url)
        for _ in range(100):
            if page.evaluate('()=>window.__GOOGLE_REFERENCE_READY__===true'):break
            page.wait_for_timeout(300)
        page.set_default_timeout(120000)
        measured=page.evaluate('p=>window.sampleEvidenceHeights(p)',coordinates);browser.close()
    ground=[v['height'] for q,v in zip(probes,measured) if q['kind']=='ground' and v['height'] is not None]
    reference=median(ground) if len(ground)>=3 else None;buildings=[]
    for identifier in polygons:
        heights=sorted(v['height'] for q,v in zip(probes,measured) if q.get('object_id')==identifier and v['height'] is not None)
        buildings.append({'object_id':identifier,'samples':len(heights),'absolute_surface_heights_m':heights,'estimated_height_m':max(heights)-reference if heights and reference is not None else None,'uncertainty':'Sparse roof mesh samples may hit podiums, vegetation or rooftop equipment; compare with OSM/visual evidence.'})
    result={'source':'Google Photorealistic 3D Tiles via Cesium ion','origin':origin,'not_surveyed':True,'ground_samples':len(ground),'ground_height_m':reference,'ground_range_m':[min(ground),max(ground)] if ground else None,'buildings':buildings,'probes':[dict(q,**v) for q,v in zip(probes,measured)]}
    write_json(args.output,result);print(json.dumps({'ground_samples':len(ground),'ground_height_m':reference,'buildings':[{k:v for k,v in b.items() if k in ['object_id','samples','estimated_height_m']} for b in buildings]}))


if __name__=='__main__':main()
