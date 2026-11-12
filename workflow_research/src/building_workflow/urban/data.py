import hashlib
import json
import math
import re
from pathlib import Path
import xml.etree.ElementTree as ET
import httpx
from pyproj import Transformer
from shapely import make_valid
from shapely.geometry import Polygon, LineString, Point, box, MultiPolygon
from shapely.ops import unary_union, polygonize
from ..config import ROOT
from ..provider import write_json
from .style import canonical_hash


def tags(element):
    return {v.get('k'):v.get('v') for v in element.findall('tag')}


def seed(identifier):
    return int(hashlib.sha256(identifier.encode()).hexdigest()[:8],16)


def polygons(geometry):
    if geometry.is_empty:return []
    if geometry.geom_type=='Polygon':return [geometry]
    return [p for g in geometry.geoms for p in polygons(g)] if hasattr(geometry,'geoms') else []


def polygon_data(poly):
    return {'outer':[[round(x,5),round(z,5)] for x,z in list(poly.exterior.coords)[:-1]],
        'holes':[[[round(x,5),round(z,5)] for x,z in list(ring.coords)[:-1]] for ring in poly.interiors]}


def number(value):
    if value is None:return None
    match=re.match(r'^\s*(\d+(?:\.\d+)?)\s*(m|meters?|metres?)?\s*$',value)
    return float(match.group(1)) if match else None


def assemble_rings(ways, node_positions):
    lines=[]
    for way in ways:
        ids=[n.get('ref') for n in way.findall('nd')]
        if len(ids)<2 or any(n not in node_positions for n in ids):
            raise ValueError('MISSING_RING_NODES')
        lines.append(LineString([node_positions[n] for n in ids]))
    result=list(polygonize(unary_union(lines)))
    if not result:raise ValueError('INCOMPLETE_RING')
    # Ensure all linework belongs to rings, rather than dropping open fragments.
    if unary_union(lines).difference(unary_union([p.boundary for p in result])).length>.01:
        raise ValueError('OPEN_RING_FRAGMENT')
    return result


def build_city(run: Path, snapshot: Path | None=None, size=400.0, longitude=106.702, latitude=10.775, grid=2, inferred_streetscape=False):
    if not 50<=size<=1000 or not 1<=grid<=10:raise ValueError('AOI_LIMITS')
    snapshot=snapshot or ROOT.parent/'docs/research/2026-11-12-district1-osm.osm'
    tree=ET.parse(snapshot).getroot()
    elements={(e.tag,e.get('id')):e for e in tree if e.tag in ['node','way','relation']}
    audit={'source':str(snapshot),'sha256':hashlib.sha256(snapshot.read_bytes()).hexdigest(),
        'attribution':'© OpenStreetMap contributors, ODbL','license':'https://www.openstreetmap.org/copyright',
        'relation_fetches':[],'excluded':[],'assumptions':['Unrecorded building heights/floors/road widths are estimates, not surveyed facts.',
            'Flat local ground is a pilot assumption; terrain has not been measured.', 'Facades and procedural streetscape additions are inferred, not photographic reconstruction.']}
    # The small-map response may omit relation members. Fetch only these bounded
    # building relations, or explicitly exclude partial geometry.
    partial=set()
    for relation in list(e for e in elements.values() if e.tag=='relation' and 'building' in tags(e)):
        missing=[m.get('ref') for m in relation.findall('member') if m.get('type')=='way' and ('way',m.get('ref')) not in elements]
        if missing:
            cache=run/f'osm-relation-{relation.get("id")}.osm'
            try:
                if not cache.exists():
                    response=httpx.get(f'https://api.openstreetmap.org/api/0.6/relation/{relation.get("id")}/full',timeout=25,
                        headers={'User-Agent':'WorldAsCodeResearch/0.1'})
                    response.raise_for_status();cache.write_bytes(response.content)
                extra=ET.parse(cache).getroot()
                for e in extra:
                    if e.tag in ['node','way','relation']:elements[(e.tag,e.get('id'))]=e
                audit['relation_fetches'].append({'id':relation.get('id'),'status':'complete_response_saved','sha256':hashlib.sha256(cache.read_bytes()).hexdigest()})
            except Exception as exc:
                partial.add(relation.get('id'));audit['excluded'].append({'id':'relation/'+relation.get('id'),'reason':type(exc).__name__+': incomplete relation'})
    zone=max(1,min(60,int((longitude+180)//6)+1));epsg=(32600 if latitude>=0 else 32700)+zone
    project=Transformer.from_crs('EPSG:4326',f'EPSG:{epsg}',always_xy=True)
    lon,lat=longitude,latitude
    ex,ny=project.transform(lon,lat)
    positions={e.get('id'):(project.transform(float(e.get('lon')),float(e.get('lat')))[0]-ex,
        -(project.transform(float(e.get('lon')),float(e.get('lat')))[1]-ny)) for e in elements.values() if e.tag=='node'}
    bounds=box(-size/2,-size/2,size/2,size/2)
    cells=[]
    for row in range(grid):
        for col in range(grid):
            x0=-size/2+col*size/grid;z0=-size/2+row*size/grid
            cells.append({'id':f'cell-{row}-{col}','bounds':[x0,z0,x0+size/grid,z0+size/grid],'owned':[],'references':[]})
    building_polys=[];suppressed=set()
    for rel in [e for e in elements.values() if e.tag=='relation' and 'building' in tags(e)]:
        members=[m for m in rel.findall('member') if m.get('type')=='way']
        suppressed.update(m.get('ref') for m in members)
        if rel.get('id') in partial:continue
        try:
            outer=[elements[('way',m.get('ref'))] for m in members if m.get('role') in ['outer','']]
            inner=[elements[('way',m.get('ref'))] for m in members if m.get('role')=='inner']
            shape=unary_union(assemble_rings(outer,positions))
            if inner:shape=shape.difference(unary_union(assemble_rings(inner,positions)))
            for i,poly in enumerate(polygons(make_valid(shape))):building_polys.append((f'relation/{rel.get("id")}/{i}',poly,tags(rel)))
        except Exception as exc:audit['excluded'].append({'id':'relation/'+rel.get('id'),'reason':str(exc)[:160]})
    for way in [e for e in elements.values() if e.tag=='way' and 'building' in tags(e) and e.get('id') not in suppressed]:
        ids=[n.get('ref') for n in way.findall('nd')]
        if len(ids)<4 or ids[0]!=ids[-1] or any(n not in positions for n in ids):
            audit['excluded'].append({'id':'way/'+way.get('id'),'reason':'incomplete or open footprint'});continue
        for i,poly in enumerate(polygons(make_valid(Polygon([positions[n] for n in ids])))):
            building_polys.append((f'way/{way.get("id")}/{i}',poly,tags(way)))
    buildings=[];shapes=[]
    for identifier,poly,metadata in sorted(building_polys):
        if not poly.intersects(bounds) or poly.area<5:continue
        if poly.area>40000:
            audit['excluded'].append({'id':identifier,'reason':'implausibly large building footprint for pilot'});continue
        floor=number(metadata.get('building:levels'));height=number(metadata.get('height'))
        estimated=height is None
        floors=int(floor) if floor else max(2,round(height/3.6)) if height else 4
        h=height if height else floors*3.6
        if h>260 or floors>70:
            audit['excluded'].append({'id':identifier,'reason':'out of pilot height budget'});continue
        touched=[c for c in cells if poly.intersection(box(*c['bounds'])).area>.01]
        if not touched:continue
        owner=max(touched,key=lambda c:poly.intersection(box(*c['bounds'])).area)['id']
        b={'id':identifier,'name':metadata.get('name',identifier),'type':metadata.get('building','yes'),
            **polygon_data(poly),'height':round(h,3),'floors':floors,'height_evidence':'inferred' if estimated else 'OSM height tag',
            'floor_evidence':'OSM levels tag' if floor else 'inferred','facade_evidence':'inferred; no facade photo supplied',
            'area':poly.area,'center':[poly.centroid.x,poly.centroid.y],'owner':owner,'cells':[c['id'] for c in touched],
            'seed':seed(identifier),'metadata':metadata}
        buildings.append(b);shapes.append(poly)
        for c in touched:c['owned' if c['id']==owner else 'references'].append(identifier)
    occupied=unary_union(shapes)
    roads=[];roadshapes=[];walkshapes=[];sidewalkshapes=[]
    default_width={'secondary':14,'tertiary':11,'residential':7,'service':4,'pedestrian':15,'footway':2.2,'steps':2}
    for way in sorted([e for e in elements.values() if e.tag=='way' and 'highway' in tags(e)],key=lambda e:e.get('id')):
        metadata=tags(way);kind=metadata['highway']
        if kind not in default_width:continue
        if metadata.get('tunnel')=='yes' or metadata.get('bridge')=='yes' or metadata.get('layer','0')!='0':
            audit['excluded'].append({'id':'way/'+way.get('id'),'reason':'non-ground road requires elevation model'});continue
        ids=[n.get('ref') for n in way.findall('nd')]
        if len(ids)<2 or any(n not in positions for n in ids):continue
        line=LineString([positions[n] for n in ids])
        if not line.intersects(bounds.buffer(20)) or line.length<.1:continue
        width=number(metadata.get('width')) or default_width[kind]
        is_area=metadata.get('area')=='yes' and ids[0]==ids[-1]
        surface=(make_valid(Polygon([positions[n] for n in ids])) if is_area else line.buffer(width/2,cap_style='round',join_style='round')).intersection(bounds)
        walk=kind in ['pedestrian','footway','steps']
        (walkshapes if walk else roadshapes).append(surface)
        if not walk:sidewalkshapes.append(line.buffer(width/2+2.8).intersection(bounds))
        roads.append({'id':'way/'+way.get('id'),'name':metadata.get('name',''),'kind':kind,'width':width,
            'width_evidence':'OSM area polygon' if is_area else 'OSM width tag' if metadata.get('width') else 'inferred','node_ids':ids,'area':is_area,
            'points':[[round(x,5),round(z,5)] for x,z in line.coords],'length':line.length,'walk':walk,
            'phase_m':0,'marking_evidence':'unknown; no lane topology validated'})
    motor=make_valid(unary_union(roadshapes).difference(occupied))
    walks=make_valid(unary_union(walkshapes+sidewalkshapes).difference(motor).difference(occupied))
    surfaces={"road":[polygon_data(p) for p in polygons(motor)],"pavement":[polygon_data(p) for p in polygons(walks)]}
    vegetation=[];lamps=[]
    for node in [e for e in elements.values() if e.tag=='node']:
        metadata=tags(node);pos=positions[node.get('id')]
        if not bounds.contains(Point(pos)):continue
        if metadata.get('natural')=='tree':vegetation.append({'id':'node/'+node.get('id'),'position':list(pos),'seed':seed(node.get('id')),'evidence':'OSM tree node'})
        if metadata.get('highway')=='street_lamp':lamps.append({'id':'node/'+node.get('id'),'position':list(pos),'evidence':'OSM street_lamp node'})
    used=[Point(v['position']) for v in vegetation]
    for road in (roads if inferred_streetscape else []):
        line=LineString(road['points'])
        for index,d in enumerate(range(8,int(line.length),14)):
            p=line.interpolate(d);q=line.interpolate(min(d+.2,line.length));dx=q.x-p.x;dz=q.y-p.y;n=math.hypot(dx,dz)
            if n<.01:continue
            for side in [-1,1]:
                offset=road['width']/2+(1.8 if road['walk'] else 1.7)
                pt=Point(p.x-dz/n*offset*side,p.y+dx/n*offset*side)
                if not bounds.buffer(-2).contains(pt) or occupied.buffer(1).contains(pt) or motor.contains(pt):continue
                if any(pt.distance(old)<4 for old in used):continue
                identifier=f'{road["id"]}/tree/{index}/{side}'
                vegetation.append({'id':identifier,'position':[pt.x,pt.y],'seed':seed(identifier),'evidence':'inferred procedural streetscape'});used.append(pt)
                if index%3==0 and side==1:lamps.append({'id':identifier+'/lamp','position':[pt.x+1.2,pt.y+1.2],'heading':math.atan2(dz,dx),'evidence':'inferred procedural streetscape'})
    parks=[]
    for way in [e for e in elements.values() if e.tag=='way']:
        metadata=tags(way)
        if metadata.get('leisure') not in ['park','garden'] and metadata.get('landuse') not in ['grass','forest']:continue
        ids=[n.get('ref') for n in way.findall('nd')]
        if len(ids)>3 and ids[0]==ids[-1] and all(n in positions for n in ids):
            poly=make_valid(Polygon([positions[n] for n in ids])).intersection(bounds).difference(occupied).difference(motor).difference(walks)
            parks.extend(polygon_data(p) for p in polygons(poly))
    candidates=[]
    for road in roads:
        if not road['walk'] or road['area']:continue
        line=LineString(road['points'])
        for fraction in [.25,.5,.75]:
            p=line.interpolate(fraction,normalized=True);q=line.interpolate(min(line.length,line.length*fraction+5))
            if not bounds.buffer(-20).contains(p) or not walks.contains(p):continue
            clearance=occupied.distance(p)
            if clearance<3:continue
            dx=q.x-p.x;dz=q.y-p.y;norm=math.hypot(dx,dz)
            if norm<.1:continue
            candidates.append((min(clearance,18)-p.distance(Point(0,0))*.03,
                {'position':[p.x,2.1,p.y],'target':[p.x+dx/norm*60,8,p.y+dz/norm*60],
                 'source':road['id'],'evidence':'camera placed on OSM-derived pedestrian path; eye height assumed'}))
    street_camera=max(candidates,key=lambda p:p[0])[1] if candidates else None
    seam={};all_surfaces=unary_union([motor,walks])
    fragments=[all_surfaces.intersection(box(*c['bounds'])) for c in cells]
    seam['symmetric_difference_area_m2']=all_surfaces.symmetric_difference(unary_union(fragments)).area
    seam['overlap_area_m2']=sum(p.area for p in fragments)-unary_union(fragments).area
    seam['object_ids_unique']=len({b['id'] for b in buildings})==len(buildings)
    seam['one_owner_per_building']=all(sum(b['id'] in c['owned'] for c in cells)==1 for b in buildings)
    seam['method']='Global canonical surfaces clipped to cell bounds; global XY texture coordinates. Full building emitted once by owner.'
    city={'id':'urban-aoi-'+canonical_hash([lon,lat,size])[:12],'origin':{'longitude':lon,'latitude':lat,'projection':f'EPSG:{epsg}','local_x':'east','local_z':'south','up':'y'},
        'bounds':[-size/2,-size/2,size/2,size/2],'cells':cells,'buildings':buildings,'roads':roads,'surfaces':surfaces,'parks':parks,
        'trees':vegetation,'lamps':lamps,'source_audit':audit,'street_camera':street_camera,'ground_elevation':{'value':0,'evidence':'inferred flat local plane'}}
    city['geometry_input_hash']=canonical_hash(city)
    write_json(run/'city.json',city);write_json(run/'boundary-checks.json',seam)
    return city
