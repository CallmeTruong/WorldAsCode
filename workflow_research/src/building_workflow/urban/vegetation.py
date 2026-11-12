"""Keep observed approximate tree positions independent of seeded shape generation."""
import json
import math
from pathlib import Path
from pyproj import Transformer
from shapely.geometry import Point,Polygon,box
from shapely.ops import unary_union
from .style import canonical_hash
from .data import seed


def apply_tree_observations(city,manifest_path):
    manifest=json.loads(Path(manifest_path).read_text(encoding='utf-8'))
    project=Transformer.from_crs('EPSG:4326',city['origin']['projection'],always_xy=True)
    east,north=project.transform(city['origin']['longitude'],city['origin']['latitude'])
    bounds=box(*city['bounds']);occupied=unary_union([Polygon(b['outer'],b['holes']) for b in city['buildings']])
    existing={t['id'] for t in city['trees']};audit={'accepted':[],'excluded':[],'source_image_sha256':manifest['image_sha256'],'position_meaning':'approximate canopy-center XY; not a surveyed trunk'}
    for i,c in enumerate(manifest.get('crowns',[])):
        lon,lat=c.get('longitude'),c.get('latitude')
        if not isinstance(lon,(int,float)) or not isinstance(lat,(int,float)) or not math.isfinite(lon+lat) or not -180<=lon<=180 or not -85<=lat<=85:raise ValueError('INVALID_TREE_COORDINATE')
        identifier='crown/'+canonical_hash([manifest['image_sha256'],c.get('id',i)])[:20]
        if identifier in existing:continue
        x,y=project.transform(lon,lat);p=Point(x-east,-(y-north))
        reason='outside_aoi' if not bounds.covers(p) else 'inside_building_footprint' if occupied.contains(p) else 'near_existing_tree' if any(p.distance(Point(t['position']))<3 for t in city['trees']) else None
        if reason:audit['excluded'].append({'id':identifier,'reason':reason});continue
        city['trees'].append({'id':identifier,'position':[p.x,p.y],'seed':seed(identifier),
            'evidence':'Google 3D Tiles overhead / VLM canopy candidate + depth pick; approximate XY',
            'position_uncertainty_m':c.get('position_uncertainty_m',5),'confidence':c.get('confidence'),
            'shape_evidence':'seeded procedural tree; species and exact trunk not observed'})
        existing.add(identifier);audit['accepted'].append(identifier)
    city['vegetation_observation_audit']=audit
    city['geometry_input_hash']=canonical_hash({k:v for k,v in city.items() if k!='geometry_input_hash'})
    return city
