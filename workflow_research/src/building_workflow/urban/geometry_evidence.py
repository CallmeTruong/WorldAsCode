"""Cached source-surface evidence to disambiguate level/ownership guesses in photographs."""
import hashlib
import json
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from shapely.geometry import Polygon,Point
from .measured import LocalFrame,project_points


def load_geometry_evidence(city,evidence):
    ground_file=evidence/'ground-evidence.json'
    if not ground_file.exists():return {'available':False,'objects':[]}
    ground=json.loads(ground_file.read_text())['median_height_m'];items=[]
    for b in city['buildings']:
        path=evidence/'measurements'/(hashlib.sha256(b['id'].encode()).hexdigest()[:12]+'.json')
        if not path.exists():continue
        d=json.loads(path.read_text());poly=Polygon(b['outer'],b.get('holes',[]));inside=poly.buffer(-2)
        if inside.is_empty:inside=poly
        points=[]
        for p,h in zip(d['points'],d['heights']):
            if h is not None and np.isfinite(h) and 1<=h-ground<=500 and inside.covers(Point(p)):
                points.append([float(p[0]),float(h-ground),float(p[1])])
        if len(points)<3:continue
        a=np.array(points);levels=np.quantile(a[:,1],[.1,.5,.9]).tolist()
        # Representative spatial anchors, not a fitted roof or a guarantee about hidden levels.
        anchors=[]
        for x in np.linspace(a[:,0].min(),a[:,0].max(),3):
            for z in np.linspace(a[:,2].min(),a[:,2].max(),3):
                index=int(np.argmin((a[:,0]-x)**2+(a[:,2]-z)**2));p=points[index]
                if p not in anchors:anchors.append(p)
        items.append({'owner':b['id'],'interior_samples':len(points),'height_p10_p50_p90_m':[round(h,2) for h in levels],
                      'height_span_m':[round(float(a[:,1].min()),2),round(float(a[:,1].max()),2)],
                      'spatial_anchors_xyz_m':anchors,'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    return {'available':True,'ground_datum_m':ground,'objects':items,'interpretation':'Heights are source mesh upper-surface samples relative to median road mesh, not survey. They may contain edge/vegetation/neighbor artifacts. Spatial interior samples constrain roof level guesses, not facade or hidden undercuts. A feature cannot be called a low podium solely from appearance if nearby source anchors are at tower-top height.'}


def label_source_heights(path,city,view,evidence):
    if not evidence.get('available'):return
    frame=LocalFrame(city['origin'],evidence['ground_datum_m'])
    with Image.open(path) as original:
        im=original.convert('RGB');draw=ImageDraw.Draw(im)
        try:font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',12)
        except OSError:font=ImageFont.load_default()
        for item in evidence['objects']:
            if view.get('object_id') and view['object_id']!=item['owner']:continue
            anchors=item['spatial_anchors_xyz_m'][::2]
            uv,valid=project_points(frame.ecef(anchors),view['camera'])
            for point,coords,ok in zip(anchors,uv,valid):
                if not ok:continue
                x,y=int(coords[0]*im.width),int(coords[1]*im.height);text=f'{point[1]:.0f}m'
                bbox=draw.textbbox((x+3,y+2),text,font=font);draw.rectangle(bbox,fill='#092c42');draw.ellipse((x-2,y-2,x+2,y+2),fill='#59d6ff');draw.text((x+3,y+2),text,font=font,fill='#c0f0ff')
        im.save(path,quality=89)
