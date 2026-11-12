"""Project observed geographic street features onto canonical AOI road surfaces."""
from pyproj import Transformer
from shapely.geometry import Polygon
from shapely.ops import unary_union
from shapely import make_valid
from .data import polygons,polygon_data
from .style import canonical_hash


def apply_ground_observations(city, observations):
    origin=city['origin'];forward=Transformer.from_crs(4326,origin['projection'],always_xy=True)
    ex,ny=forward.transform(origin['longitude'],origin['latitude'])
    roads=unary_union([Polygon(p['outer'],p['holes']) for p in city['surfaces']['road']])
    markings=[];rejected=[]
    for feature in observations.get('crosswalks',[]):
        ring=feature.get('lonlat',[])
        if len(ring)!=4 or feature.get('confidence',0)<.65:rejected.append(feature.get('id'));continue
        points=[]
        for lon,lat in ring:
            x,y=forward.transform(lon,lat);points.append((x-ex,ny-y))
        area=make_valid(Polygon(points));length=((points[1][0]-points[0][0])**2+(points[1][1]-points[0][1])**2)**.5
        if area.is_empty or not 2<=area.area<=250 or not 2<=length<=50:rejected.append(feature.get('id'));continue
        # Detected extent is factual evidence; stripe spacing is a labeled approximation.
        def lerp(a,b,t):return (a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t)
        for i in range(int(length/.9)+1):
            a=i*.9/length;b=min(1,(i*.9+.45)/length)
            if a>=1:break
            quad=[lerp(points[0],points[1],a),lerp(points[0],points[1],b),lerp(points[3],points[2],b),lerp(points[3],points[2],a)]
            stripe=make_valid(Polygon(quad)).intersection(roads)
            markings.extend({**polygon_data(p),'source':feature['id'],'evidence':'VLM crosswalk extent + mesh projection; stripe spacing approximated'} for p in polygons(stripe) if p.area>.05)
    city['observed_markings']=markings
    surface_settings={}
    for role in ['road','pavement']:
        item=observations.get('surface_materials',{}).get(role,{})
        tint=item.get('albedo_multiplier')
        if isinstance(tint,(int,float)) and .1<=tint<=1:
            surface_settings[role]={'albedo_multiplier':tint,'evidence':item.get('evidence','visual estimate; not measured reflectance')}
    city['surface_settings']=surface_settings
    detail=observations.get('tree_cluster_detail',1)
    if isinstance(detail,int) and 1<=detail<=4:city['tree_cluster_detail']=detail
    city['geometry_input_hash']=canonical_hash({k:v for k,v in city.items() if k!='geometry_input_hash'})
    retained={p['source'] for p in markings}
    return {'crosswalks_intersecting_aoi_roads':len(retained),'outside_aoi_roads':[f.get('id') for f in observations.get('crosswalks',[]) if f.get('id') not in retained and f.get('id') not in rejected],'crosswalk_candidates':len(observations.get('crosswalks',[])),'stripe_polygons':len(markings),'rejected':rejected,'surface_settings':surface_settings}
