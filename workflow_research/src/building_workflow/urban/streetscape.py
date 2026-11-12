"""Deterministic, explicitly inferred streetscape tools on shared OSM topology."""
import copy
import math
from shapely.geometry import Point,Polygon,LineString,box
from shapely.ops import unary_union
from .data import seed


def decorate_streets(city,options,context=None):
    city=copy.deepcopy(city);context=context or city
    # Rebuild only our inferred layer so new agent spacing/toggles take effect.
    city['trees']=[t for t in city['trees'] if not t.get('context_generated') and t.get('evidence')!='inferred OSM-sidewalk context; approximate position']
    city['lamps']=[t for t in city['lamps'] if not t.get('context_generated') and t.get('evidence')!='inferred context light; approximate position']
    spacing=options.get('tree_spacing_m',14)
    if type(spacing) not in (int,float) or not 8<=spacing<=40:raise ValueError('STREET_TREE_SPACING')
    for key in ('curbs','extend_tree_rows','add_lamps','inferred_lane_dashes','include_core'):
        if key in options and type(options[key]) is not bool:raise ValueError('STREETSCAPE_OPTION')
    bounds=box(*city['bounds']);core=box(*city.get('core_bounds',city['bounds']))
    occupied=unary_union([Polygon(b['outer'],b.get('holes',[])) for b in context['buildings']]).buffer(1)
    motor=unary_union([Polygon(p['outer'],p.get('holes',[])) for p in city['surfaces']['road']])
    walks=unary_union([Polygon(p['outer'],p.get('holes',[])) for p in city['surfaces']['pavement']])
    used=[Point(t['position']) for t in city['trees']];ids={t['id'] for t in city['trees']}
    lamp_ids={t['id'] for t in city['lamps']}
    tree_count=lamp_count=0
    for road in city['roads']:
        road.pop('markings_inferred',None);road.pop('inferred_marking_evidence',None)
        if options.get('inferred_lane_dashes') and not road['walk'] and not road['area'] and road['width']>=8:
            road['markings_inferred']=True;road['inferred_marking_evidence']='Illustrative inferred centreline, not verified lane topology.'
        if road['walk'] or road['area'] or not options.get('extend_tree_rows'):continue
        line=LineString(road['points'])
        for index in range(max(0,int((line.length-8)/spacing)+1)):
            distance=8+index*spacing
            if distance>=line.length:continue
            p=line.interpolate(distance);q=line.interpolate(min(distance+.2,line.length));dx=q.x-p.x;dz=q.y-p.y;n=math.hypot(dx,dz)
            if n<.01:continue
            for side in (-1,1):
                offset=road['width']/2+1.7;pt=Point(p.x-dz/n*offset*side,p.y+dx/n*offset*side)
                if not bounds.buffer(-2).contains(pt) or (not options.get('include_core') and core.covers(pt)):continue
                if occupied.contains(pt) or motor.contains(pt) or not walks.buffer(.2).contains(pt):continue
                if any(pt.distance(old)<6 for old in used):continue
                identifier=f'{road["id"]}/context-tree/{index}/{side}'
                if identifier in ids:continue
                city['trees'].append({'id':identifier,'position':[pt.x,pt.y],'seed':seed(identifier),'evidence':'inferred OSM-sidewalk context; approximate position','context_generated':True})
                ids.add(identifier);used.append(pt);tree_count+=1
                if options.get('add_lamps') and side==1 and index%3==0:
                    identifier+='/lamp'
                    if identifier not in lamp_ids:
                        city['lamps'].append({'id':identifier,'position':[pt.x+dx/n*1.5,pt.y+dz/n*1.5],'heading':math.atan2(dz,dx),'evidence':'inferred context light; approximate position','context_generated':True})
                        lamp_ids.add(identifier);lamp_count+=1
    city['context_curbs']=options.get('curbs',False)
    city['streetscape_audit']={'method':'Shared OSM topology with deterministic seeds; inferred rows, lights and markings are not source-verified positions.','added_trees':tree_count,'added_lamps':lamp_count,'options':options}
    return city
