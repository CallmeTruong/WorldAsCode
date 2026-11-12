import json
import subprocess
from pathlib import Path
import httpx
import pytest
from building_workflow.config import ROOT
from building_workflow.urban.imagery import discover_imagery,mapillary_catalog,planet_catalog,select_facade_candidates,validate_bbox
from building_workflow.urban.vegetation import apply_tree_observations


def test_discovery_missing_credentials_never_requests_or_orders(tmp_path):
    def forbidden(request):raise AssertionError('No credentials should mean no HTTP request')
    with httpx.Client(transport=httpx.MockTransport(forbidden)) as client:
        result=discover_imagery([139.762,35.677,139.764,35.679],tmp_path/'coverage.json',env={},client=client)
    assert all(p['status']=='missing_credentials' for p in result['providers'])
    assert not any(p['assets'] for p in result['providers'])


def test_official_catalog_requests_exclude_credentials_from_saved_evidence():
    seen=[]
    def handler(request):
        seen.append(request)
        if request.url.host=='graph.mapillary.com':
            assert request.headers['Authorization']=='OAuth test-secret'
            assert 'test-secret' not in str(request.url)
            return httpx.Response(200,json={'data':[{'id':'42','geometry':{'type':'Point','coordinates':[139.763,35.679]},'is_pano':True}],'paging':{'next':'https://secret-next?access_token=test-secret'}})
        assert request.url.path=='/data/v1/quick-search'
        query=json.loads(request.content);assert query['item_types']==['SkySatCollect']
        return httpx.Response(200,json={'features':[{'id':'sky-1','geometry':{'type':'Polygon','coordinates':[[[139.762,35.677],[139.764,35.677],[139.764,35.679],[139.762,35.679],[139.762,35.677]]]},'properties':{'gsd':.5,'cloud_cover':.02},'_permissions':['assets:download']}],'_links':{'_next':'https://signed-next?token=private'}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        m=mapillary_catalog([139.762,35.677,139.764,35.679],'test-secret',client)
        p=planet_catalog([139.762,35.677,139.764,35.679],'planet-secret',client)
    assert len(seen)==2 and m['truncated'] and p['truncated']
    assert 'secret' not in json.dumps([m,p]) and 'signed-next' not in json.dumps(p)
    assert not p['assets'][0]['analysis_rights_confirmed'] and p['assets'][0]['aoi_overlap_fraction']==pytest.approx(1)


def test_panorama_is_not_all_sides_of_building_and_wrong_heading_rejected():
    center=[139.763,35.678]
    assets=[{'id':'north-panorama','geometry':{'type':'Point','coordinates':[139.763,35.6783]},'is_panorama':True},
            {'id':'wrong-heading','geometry':{'type':'Point','coordinates':[139.7633,35.678]},'heading_deg':90,'is_panorama':False}]
    result=select_facade_candidates(center,assets)
    assert [x['asset_id'] for x in result['faces']['front']]==['north-panorama']
    assert set(result['missing_faces'])=={'left','right','back'} and not result['factual_coverage_verified']


def test_geographic_limits_and_tree_observation_positions_are_explicit(tmp_path):
    with pytest.raises(ValueError):validate_bbox([0,0,1,1])
    with pytest.raises(ValueError):validate_bbox([10,10,9,11])
    city={'origin':{'longitude':139.763,'latitude':35.678,'projection':'EPSG:32654'},'bounds':[-100,-100,100,100],'buildings':[],'trees':[]}
    p=tmp_path/'crowns.json';p.write_text(json.dumps({'image_sha256':'abc','crowns':[{'id':'one','longitude':139.763,'latitude':35.678,'confidence':.9}]}))
    first=apply_tree_observations(city,p)
    assert len(first['trees'])==1 and first['trees'][0]['position']==pytest.approx([0,0])
    original=first['trees'][0].copy();again=apply_tree_observations(city,p)
    assert len(again['trees'])==1 and again['trees'][0]==original


def test_tokyo_snapshot_uses_utm54_not_vietnam_zone(tmp_path):
    from building_workflow.urban.data import build_city
    snapshot=tmp_path/'tokyo.osm'
    snapshot.write_text('''<osm><node id="1" lat="35.6784" lon="139.7630"/><node id="2" lat="35.6784" lon="139.7632"/><node id="3" lat="35.6786" lon="139.7632"/><node id="4" lat="35.6786" lon="139.7630"/><way id="1"><nd ref="1"/><nd ref="2"/><nd ref="3"/><nd ref="4"/><nd ref="1"/><tag k="building" v="yes"/><tag k="height" v="12 m"/></way></osm>''')
    city=build_city(tmp_path,snapshot=snapshot,size=220,longitude=139.7631,latitude=35.6785)
    assert city['origin']['projection']=='EPSG:32654'
    assert len(city['buildings'])==1 and max(abs(x) for x in city['buildings'][0]['center'])<1
    assert 300<city['buildings'][0]['area']<450


def test_seeded_tree_shapes_are_deterministic_without_moving_anchor():
    code='''import {describeTree,treeBatches,frondMeshData} from './runtime/urban-trees.mjs';
const a=describeTree(123),b=describeTree(123),c=describeTree(124);
const p=treeBatches([{id:'one',position:[12,34],seed:123}]);
const q=treeBatches([{id:'one',position:[12,34],seed:124}]);
const families=new Set(Array.from({length:50},(_,i)=>describeTree(i).family));
console.log(JSON.stringify({equal:JSON.stringify(a)===JSON.stringify(b),different:JSON.stringify(a)!==JSON.stringify(c),anchors:[p.wood[0].position,q.wood[0].position],metadata:[p.metadata[0].position,q.metadata[0].position],familyCount:families.size,palm:describeTree(1,{family:'palm'}).fronds.length,finite:JSON.stringify(p).includes('null'),frond:frondMeshData().indices.length}));'''
    result=subprocess.run(['node','--input-type=module','-e',code],cwd=ROOT,capture_output=True,text=True,check=True)
    r=json.loads(result.stdout)
    assert r['equal'] and r['different'] and r['metadata']==[[12,34],[12,34]]
    assert r['familyCount']==3 and r['palm']>=9 and not r['finite'] and r['frond']>0
