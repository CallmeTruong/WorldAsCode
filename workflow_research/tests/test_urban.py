import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import pytest
from PIL import Image
from shapely.geometry import Polygon,LineString,box
from shapely.ops import unary_union
from building_workflow.config import ROOT
from building_workflow.urban.data import assemble_rings,polygon_data,number,seed
from building_workflow.urban.style import UrbanStyle,NEUTRAL,canonical_hash,extract_style
from building_workflow.urban.assets import browser_assets


def way(refs):
    w=ET.Element('way')
    for ref in refs:ET.SubElement(w,'nd',ref=ref)
    return w


def test_split_reversed_rings_and_missing_member_fail():
    p={'a':(0,0),'b':(4,0),'c':(4,4),'d':(0,4)}
    rings=assemble_rings([way(['a','b','c']),way(['a','d','c'])],p)
    assert sum(r.area for r in rings)==16
    with pytest.raises(ValueError):assemble_rings([way(['a','b','c'])],p)
    with pytest.raises(ValueError):assemble_rings([way(['a','missing','c'])],p)


def test_courtyard_and_tile_union_keep_holes():
    p=Polygon([(0,0),(10,0),(10,10),(0,10)],holes=[[(3,3),(7,3),(7,7),(3,7)]])
    data=polygon_data(p)
    reconstructed=Polygon(data['outer'],data['holes'])
    assert reconstructed.area==84 and len(data['holes'])==1
    parts=[p.intersection(box(0,0,5,10)),p.intersection(box(5,0,10,10))]
    assert p.symmetric_difference(unary_union(parts)).area<1e-9


def test_global_road_surface_tiling_no_gap_or_overlap():
    surface=unary_union([LineString([(-10,-8),(8,10)]).buffer(2),LineString([(-10,5),(10,-5)]).buffer(2)])
    clipped=surface.intersection(box(-10,-10,10,10))
    pieces=[clipped.intersection(box(x,z,x+10,z+10)) for x in [-10,0] for z in [-10,0]]
    assert clipped.symmetric_difference(unary_union(pieces)).area<1e-9
    assert abs(sum(p.area for p in pieces)-clipped.area)<1e-9


def test_style_profile_is_not_fixed_to_user_palette():
    a=UrbanStyle.model_validate(NEUTRAL)
    raw=json.loads(json.dumps(NEUTRAL));raw['artistic_intent']='Expressive ink-wash architecture with loose edges';raw['name']='Alternative arbitrary style'
    b=UrbanStyle.model_validate(raw)
    assert a.artistic_intent!=b.artistic_intent and canonical_hash(a.model_dump())!=canonical_hash(b.model_dump())
    raw['palette']={'building':'#ffffff'}
    with pytest.raises(ValueError):UrbanStyle.model_validate(raw)


def test_safe_style_folder_rejects_empty_or_oversized(tmp_path):
    folder=tmp_path/'refs';folder.mkdir();run=tmp_path/'run';run.mkdir()
    with pytest.raises(ValueError,match='1_TO_20'):extract_style(folder,run,None)
    for i in range(21):(folder/f'{i}.png').write_bytes(b'not-an-image')
    with pytest.raises(ValueError,match='1_TO_20'):extract_style(folder,run,None)


def test_asset_registry_rejects_changed_file_or_path_escape(tmp_path):
    texture=tmp_path/'test.jpg';texture.write_bytes(b'bytes')
    item={'road':{'physical_tile_m':4,'maps':{'color':{'file':'test.jpg','sha256':'wrong'}}}}
    with pytest.raises(ValueError,match='ASSET_CHANGED'):browser_assets(tmp_path,item)
    item['road']['maps']['color']['file']='../outside.jpg'
    with pytest.raises(ValueError,match='PATH_ESCAPE'):browser_assets(tmp_path,item)


def test_metric_height_parser_does_not_silently_accept_feet():
    assert number('26 m')==26 and number('193')==193
    assert number('80 ft') is None
    assert seed('way/123')==seed('way/123') and seed('way/123')!=seed('way/124')


def test_real_saved_pilot_contracts_if_present():
    run=ROOT/'runs/urban/district1-pilot'
    if not (run/'urban-runtime-result.json').exists():pytest.skip('real pilot has not been executed')
    result=json.loads((run/'urban-runtime-result.json').read_text())
    if not result.get('ok'):pytest.skip('real pilot currently being repaired')
    city=json.loads((run/'city.json').read_text(encoding='utf-8'));boundary=json.loads((run/'boundary-checks.json').read_text())
    assert len(city['cells'])==4 and len(city['buildings'])>0
    assert boundary['one_owner_per_building'] and boundary['object_ids_unique']
    assert boundary['symmetric_difference_area_m2']<1e-6
    assert result['metrics']['style_only_same_geometry']
    assert len(result['metrics']['objects'])==len(city['buildings'])
    for mode in ['neutral','styled']:
        for view in ['overview','north','grid','street','detail','seam']:
            im=Image.open(run/'renders'/f'{mode}-{view}.png')
            assert im.width==1440 and im.height==1080


def test_cell_cache_rebuild_and_style_invalidation(tmp_path):
    from building_workflow.urban.reuse import cell_artifacts
    city={'cells':[{'id':'a','bounds':[0,0,10,10],'owned':['one'],'references':[]},
                   {'id':'b','bounds':[10,0,20,10],'owned':['two'],'references':[]}],
          'buildings':[{'id':'one','height':8},{'id':'two','height':10}],
          'surfaces':{'road':[{'outer':[[0,0],[20,0],[20,2],[0,2]],'holes':[]}]}}
    initial=cell_artifacts(city,{'name':'first'},tmp_path)
    assert all(r['status']=='geometry_changed' for r in initial)
    repeated=cell_artifacts(city,{'name':'first'},tmp_path)
    assert all(r['status']=='reused' for r in repeated)
    restyled=cell_artifacts(city,{'name':'second'},tmp_path)
    assert all(r['status']=='material_only' for r in restyled)
    assert [r['geometry_input_hash'] for r in initial]==[r['geometry_input_hash'] for r in restyled]
    city['buildings'][0]['height']=15
    changed=cell_artifacts(city,{'name':'second'},tmp_path)
    assert changed[0]['status']=='geometry_changed' and changed[1]['status']=='reused'
