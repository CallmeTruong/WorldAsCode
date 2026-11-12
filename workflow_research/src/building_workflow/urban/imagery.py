"""AOI-first imagery discovery. Catalog reads only; never orders or activates assets."""
import math
import os
from datetime import datetime,timezone
from pathlib import Path
import httpx
from dotenv import dotenv_values
from shapely.geometry import shape,box
from ..config import ROOT
from ..provider import write_json


def validate_bbox(bounds):
    if len(bounds)!=4 or any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in bounds):raise ValueError('INVALID_BBOX')
    w,s,e,n=bounds
    if not -180<=w<e<=180 or not -85<=s<n<=85:raise ValueError('INVALID_BBOX')
    # Discovery is paged per small AOI, not an unbounded city-wide request.
    if (e-w)*111320*math.cos(math.radians((s+n)/2))>2500 or (n-s)*111320>2500:raise ValueError('DISCOVERY_AOI_LIMIT_2500M')
    return list(bounds)


def _request(client,method,url,**kwargs):
    try:
        response=client.request(method,url,**kwargs)
        if response.status_code!=200:
            return None,{'status':'auth_required' if response.status_code==401 else 'access_denied' if response.status_code==403 else 'rate_limited' if response.status_code==429 else 'provider_error','http_status':response.status_code}
        return response.json(),None
    except (httpx.HTTPError,ValueError) as error:
        # Never serialize exception strings/URLs: headers and signed links can contain secrets.
        return None,{'status':'provider_error','error_type':type(error).__name__}


def mapillary_catalog(bounds,token,client,limit=100):
    validate_bbox(bounds)
    if not 1<=limit<=500:raise ValueError('CATALOG_LIMIT')
    if not token:return {'provider':'mapillary','status':'missing_credentials','required_variable':'MAPILLARY_ACCESS_TOKEN','assets':[]}
    payload,error=_request(client,'GET','https://graph.mapillary.com/images',
        params={'bbox':','.join(map(str,bounds)),'fields':'id,geometry,captured_at,compass_angle,is_pano,sequence','limit':limit},headers={'Authorization':'OAuth '+token})
    if error:return {'provider':'mapillary',**error,'assets':[]}
    assets=[]
    for row in payload.get('data',[]):
        geometry=row.get('geometry',{})
        if geometry.get('type')!='Point':continue
        assets.append({'id':str(row['id']),'provider':'mapillary','geometry':geometry,'captured_at':row.get('captured_at'),
            'heading_deg':row.get('compass_angle'),'is_panorama':bool(row.get('is_pano')),'sequence_id':row.get('sequence'),
            'source_page':'https://www.mapillary.com/app/?pKey='+str(row['id']),
            'license':'CC-BY-SA; preserve creator attribution and verify intended derivative distribution',
            'evidence_state':'catalog_candidate_not_visually_verified'})
    return {'provider':'mapillary','status':'catalog_available' if assets else 'no_catalog_results','assets':assets,
        'truncated':bool(payload.get('paging',{}).get('next')),'note':'One bounded page; missing entries are not proof of no coverage. Pagination is scheduled as additional bounded jobs. Signed image URLs are never persisted.'}


def planet_catalog(bounds,key,client,limit=50):
    validate_bbox(bounds)
    if not 1<=limit<=250:raise ValueError('CATALOG_LIMIT')
    if not key:return {'provider':'planet','status':'missing_credentials','required_variable':'PLANET_API_KEY','assets':[]}
    aoi=box(*bounds)
    query={'item_types':['SkySatCollect'],'filter':{'type':'AndFilter','config':[
        {'type':'GeometryFilter','field_name':'geometry','config':aoi.__geo_interface__},
        {'type':'RangeFilter','field_name':'cloud_cover','config':{'lte':.2}}]}}
    payload,error=_request(client,'POST','https://api.planet.com/data/v1/quick-search',params={'_page_size':limit,'_sort':'acquired desc'},
        auth=httpx.BasicAuth(key,''),json=query)
    if error:return {'provider':'planet',**error,'assets':[]}
    assets=[]
    for row in payload.get('features',[]):
        props=row.get('properties',{});geometry=row.get('geometry')
        overlap=shape(geometry).intersection(aoi).area/aoi.area if geometry else 0
        assets.append({'id':str(row['id']),'provider':'planet','item_type':props.get('item_type','SkySatCollect'),
            'geometry':geometry,'captured_at':props.get('acquired'),'gsd_m':props.get('gsd'),'cloud_fraction':props.get('cloud_cover'),
            'aoi_overlap_fraction':overlap,'catalog_permissions':row.get('_permissions',[]),
            'license':'account_contract_required','analysis_rights_confirmed':False,'cost_usd':None,
            'evidence_state':'catalog_candidate_not_ordered_or_downloaded'})
    return {'provider':'planet','status':'catalog_available' if assets else 'no_catalog_results','assets':assets,
        'truncated':bool(payload.get('_links',{}).get('_next')),'note':'No activation, order or imagery purchase. Catalog footprint overlap does not prove cloud-free usable pixels or download entitlement.'}


def select_facade_candidates(center_lon_lat,assets,front_bearing_deg=0,max_per_face=2):
    """Plan camera evidence; a 360 panorama still observes only its visible side."""
    if not 1<=max_per_face<=8:raise ValueError('VIEW_LIMIT')
    lon,lat=center_lon_lat;ranked={name:[] for name in ['front','right','back','left']}
    for asset in assets:
        if asset.get('geometry',{}).get('type')!='Point':continue
        x,y=asset['geometry']['coordinates'][:2]
        east=(x-lon)*111320*math.cos(math.radians(lat));north=(y-lat)*111320
        distance=math.hypot(east,north)
        if not 5<=distance<=180:continue
        bearing=math.degrees(math.atan2(east,north))%360
        heading=asset.get('heading_deg');error=0
        if not asset.get('is_panorama'):
            if not isinstance(heading,(int,float)):continue
            error=abs((heading-(bearing+180)+180)%360-180)
            if error>60:continue
        face=['front','right','back','left'][int(((bearing-front_bearing_deg+45)%360)//90)]
        ranked[face].append({'asset_id':asset['id'],'distance_m':round(distance,2),'bearing_deg':round(bearing,2),
            'heading_error_deg':round(error,2),'state':'candidate_requires_visibility_and_identity_check','score':distance+error})
    for face in ranked:
        ranked[face]=sorted(ranked[face],key=lambda v:(v['score'],v['asset_id']))[:max_per_face]
        for item in ranked[face]:item.pop('score')
    return {'faces':ranked,'missing_faces':[name for name,items in ranked.items() if not items],
        'factual_coverage_verified':False,'inference_policy':'Missing facades may reuse observed construction grammar with an inferred label; never claim measured backside accuracy.'}


def discover_imagery(bounds,output,env=None,client=None):
    bounds=validate_bbox(bounds);env=env if env is not None else {**dotenv_values(ROOT.parent/'.env'),**os.environ}
    own=client is None;client=client or httpx.Client(timeout=30,follow_redirects=False)
    try:
        report={'created_at':datetime.now(timezone.utc).isoformat(),'bbox_wsen':bounds,'scope':'bounded metadata discovery; no paid orders',
            'providers':[mapillary_catalog(bounds,env.get('MAPILLARY_ACCESS_TOKEN'),client),planet_catalog(bounds,env.get('PLANET_API_KEY') or env.get('PL_API_KEY'),client)],
            'cesium_role':'Visualization/context and user-owned licensed assets; account access alone is not a reconstruction/analysis license for third-party imagery.',
            'acceptance':'Do not call an AOI reconstruction-ready until per-facade visibility, overhead resolution/age/clouds, georegistration and derivative rights are verified.'}
    finally:
        if own:client.close()
    write_json(Path(output),report);return report
