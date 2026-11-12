"""Deterministic per-cell build inputs and dependency invalidation evidence."""
import json
from pathlib import Path
from shapely.geometry import Polygon,box,Point
from .data import polygons,polygon_data
from .style import canonical_hash
from ..provider import write_json


def cell_artifacts(city,style_profile,run:Path):
    result=[];byid={b['id']:b for b in city['buildings']}
    for cell in city['cells']:
        bounds=box(*cell['bounds']);surfaces={}
        for role,parts in city['surfaces'].items():
            surfaces[role]=[polygon_data(p) for part in parts for p in polygons(Polygon(part['outer'],part['holes']).intersection(bounds))]
        geometry={'cell_id':cell['id'],'bounds':cell['bounds'],'owned_buildings':[byid[k] for k in cell['owned']],
            'referenced_buildings':[byid[k] for k in cell['references']], 'canonical_surface_fragments':surfaces,
                  'trees':[t for t in city.get('trees',[]) if bounds.covers(Point(t['position']))],
                  'lamps':[t for t in city.get('lamps',[]) if bounds.covers(Point(t['position']))],
                  'parks':[polygon_data(p) for part in city.get('parks',[]) for p in polygons(Polygon(part['outer'],part['holes']).intersection(bounds))],
                  'source_sha256':canonical_hash((run/'building-generator.ts').read_text(encoding='utf-8')) if (run/'building-generator.ts').exists() else None,
                  'asset_registry':json.loads((run/'asset-manifest.json').read_text()) if (run/'asset-manifest.json').exists() else None}
        record={'geometry_input_hash':canonical_hash(geometry),'material_profile_hash':canonical_hash(style_profile),'data':geometry}
        path=run/'cells'/f'{cell["id"]}.json';previous=json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
        status='reused' if previous==record else 'material_only' if previous and previous['geometry_input_hash']==record['geometry_input_hash'] else 'geometry_changed'
        if previous!=record:write_json(path,record)
        result.append({'id':cell['id'],'status':status,'geometry_input_hash':record['geometry_input_hash'],'material_profile_hash':record['material_profile_hash']})
    write_json(run/'cell-build-manifest.json',result)
    return result
