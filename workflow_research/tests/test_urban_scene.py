import copy
import json
from pathlib import Path
import pytest
from PIL import Image
from building_workflow.urban.scene import scene_inputs,validate_plan,placement_checks,compose_scene


def inputs(tmp_path):
    Image.new('RGB',(30,20),'white').save(tmp_path/'a.png')
    manifest=tmp_path/'scene.json'
    manifest.write_text(json.dumps({'views':[{'id':'train','image':'a.png'},{'id':'test','image':'a.png','held_out':True}]}))
    return manifest


def test_scene_input_hash_includes_image_content_and_requires_validation_view(tmp_path):
    manifest=inputs(tmp_path);before=scene_inputs(manifest)[2]
    Image.new('RGB',(30,20),'red').save(tmp_path/'a.png')
    assert scene_inputs(manifest)[2]!=before
    data=json.loads(manifest.read_text());data['views'][1].pop('held_out');manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='HELD_OUT'):scene_inputs(manifest)


def test_scene_input_blocks_path_escape_and_duplicate_ids(tmp_path):
    manifest=inputs(tmp_path);data=json.loads(manifest.read_text());data['views'][0]['image']='../secret.png'
    manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='IMAGE_PATH'):scene_inputs(manifest)
    data['views'][0]['image']='a.png';data['views'][1]['id']='train';manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='VIEW_ID'):scene_inputs(manifest)


def test_scene_plan_requires_complete_unique_ids_and_known_evidence():
    city={'buildings':[{'id':'one'}]}
    item={'object_id':'one','visibility':'partial','evidence_views':['north'],'massing':'L','roof':'gables','materials':'brick','required_texture_roles':['brick'],'uncertainty':['rear hidden']}
    plan={'buildings':[item]};assert validate_plan(plan,city,{'north'})==plan
    broken=copy.deepcopy(plan);broken['buildings']*=2
    with pytest.raises(ValueError,match='COVERAGE'):validate_plan(broken,city,{'north'})
    with pytest.raises(ValueError,match='UNKNOWN_VIEW'):validate_plan(plan,city,{'south'})
    broken=copy.deepcopy(plan);broken['buildings'][0]['required_texture_roles']=['made-up']
    with pytest.raises(ValueError,match='TEXTURE_ROLE'):validate_plan(broken,city,{'north'})


def test_placement_gate_catches_missing_anchor_and_floating_geometry():
    city={'buildings':[{'id':'one','outer':[[20,30],[30,30],[30,40],[20,40]]}]}
    good={'id':'one','min':[20,0,30],'max':[30,12,40]}
    assert placement_checks(city,[good])==[]
    assert placement_checks(city,[{'id':'one','min':[0,0,0],'max':[10,12,10]}])
    assert placement_checks(city,[{**good,'min':[20,4,30]}])
    assert placement_checks(city,[])==['object coverage mismatch']


def test_component_wrapper_owns_world_anchor_and_removes_nested_identity(tmp_path):
    import hashlib
    key=hashlib.sha256(b'one').hexdigest()[:12]
    folder=tmp_path/'components'/key;folder.mkdir(parents=True)
    (folder/'generator.ts').write_text('function buildComponent(b:any){const g=new THREE.Group();return g;}')
    compose_scene(tmp_path,{'buildings':[{'object_id':'one'}]})
    source=(tmp_path/'building-generator.ts').read_text()
    assert 'center:[0,0]' in source and 'anchor.position.set(x,0,z)' in source
    assert 'delete o.userData.objectId' in source and "throw Error('MISSING_COMPONENT:'" in source


def test_mesh_heights_change_inferred_only_and_keep_multilevel_tag_conflict():
    from building_workflow.urban.scene import apply_mesh_height_evidence
    origin={'longitude':139.7631,'latitude':35.67845}
    city={'origin':origin,'buildings':[{'id':'museum','height':10.8,'height_evidence':'inferred'},{'id':'podium','height':12,'height_evidence':'OSM height tag'}]}
    evidence={'origin':origin,'ground_samples':20,'ground_height_m':38.8,'buildings':[{'object_id':'museum','samples':3,'estimated_height_m':19.3},{'object_id':'podium','samples':6,'estimated_height_m':34.7}]}
    audit=apply_mesh_height_evidence(city,evidence)
    assert city['buildings'][0]['height']==19.3 and city['buildings'][0]['source_height']==10.8
    assert city['buildings'][1]['height']==12 and audit['objects'][1]['tag_conflict']
    changed=copy.deepcopy(evidence);changed['origin']={**origin,'longitude':106.7}
    with pytest.raises(ValueError,match='ORIGIN'):apply_mesh_height_evidence(city,changed)
    with pytest.raises(ValueError,match='GROUND'):apply_mesh_height_evidence(city,{**evidence,'ground_samples':1})


def test_observed_crosswalks_are_clipped_to_actual_road_and_low_confidence_rejected():
    from building_workflow.urban.ground import apply_ground_observations
    from pyproj import Transformer
    from shapely.geometry import Polygon
    origin={'longitude':139.7631,'latitude':35.67845,'projection':'EPSG:32654'}
    forward=Transformer.from_crs(4326,32654,always_xy=True);ex,ny=forward.transform(origin['longitude'],origin['latitude']);inverse=Transformer.from_crs(32654,4326,always_xy=True)
    road={'outer':[[-5,-5],[5,-5],[5,5],[-5,5]],'holes':[]}
    city={'origin':origin,'surfaces':{'road':[road]}}
    extent=[[-8,-2],[8,-2],[8,2],[-8,2]]
    cross={'id':'cross','confidence':.9,'lonlat':[inverse.transform(ex+x,ny-z) for x,z in extent]}
    audit=apply_ground_observations(city,{'crosswalks':[cross,{**cross,'id':'uncertain','confidence':.3}],'surface_materials':{'road':{'albedo_multiplier':.5}}})
    assert audit['stripe_polygons']>0 and audit['rejected']==['uncertain']
    polygon=Polygon(road['outer'])
    assert all(Polygon(p['outer']).difference(polygon).area<1e-6 for p in city['observed_markings'])
    assert city['surface_settings']['road']['albedo_multiplier']==.5


def test_fine_tree_clusters_are_seeded_and_keep_anchors():
    import subprocess
    from building_workflow.config import ROOT
    code="""import {treeBatches} from './runtime/urban-trees.mjs';
const p=[{id:'tree',seed:42,position:[12,34]}];
const a=treeBatches(p),b=treeBatches(p,{clusterDetail:3}),c=treeBatches(p,{clusterDetail:3});
console.log(JSON.stringify({more:b.crowns.length>a.crowns.length,same:JSON.stringify(b)===JSON.stringify(c),anchors:b.metadata[0].position}));"""
    r=subprocess.run(['node','--input-type=module','-e',code],cwd=ROOT,capture_output=True,text=True,check=True)
    data=json.loads(r.stdout);assert data=={'more':True,'same':True,'anchors':[12,34]}


def test_held_out_view_is_used_only_for_final_validation(tmp_path):
    from building_workflow.urban.scene import inspect_scene
    manifest=inputs(tmp_path)
    data=json.loads(manifest.read_text());data['views'][1]['image']='held.png';manifest.write_text(json.dumps(data))
    Image.new('RGB',(30,20),'blue').save(tmp_path/'held.png')
    (tmp_path/'scene-plan.json').write_text('{}');(tmp_path/'style-inputs').mkdir();(tmp_path/'renders').mkdir()
    for view in ['overview','north','grid']:Image.new('RGB',(30,20)).save(tmp_path/'renders'/('styled-'+view+'.png'))
    class Fake:
        settings=type('Settings',(),{'review_model':'test'})()
        def call(self,stage,prompt,images,*args):
            assert any(p.name=='held.png' for p in images)==stage.endswith('-2')
            return {'factual_accepted':True,'style_accepted':True,'issues':[]}
    assert not inspect_scene(tmp_path,manifest,Fake(),0)['held_out_included']
    assert inspect_scene(tmp_path,manifest,Fake(),2)['held_out_included']
