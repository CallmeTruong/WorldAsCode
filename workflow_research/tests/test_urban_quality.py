import json
from pathlib import Path
from PIL import Image
import pytest
from building_workflow.urban.style import NEUTRAL, presentation_settings
from building_workflow.urban.objects import reference_signature, footprint_sheet
from building_workflow.urban.reuse import cell_artifacts
from building_workflow.urban.quality import inspect_objects,object_view_name
from building_workflow.urban.quality import patch_fragment


def test_factual_reference_content_invalidates_signature(tmp_path):
    image=tmp_path/'a.jpg';Image.new('RGB',(10,10),'red').save(image)
    manifest=tmp_path/'refs.json';manifest.write_text(json.dumps({'objects':[{'object_id':'one','images':['a.jpg']}]}))
    before=reference_signature(manifest)
    Image.new('RGB',(10,10),'blue').save(image)
    assert before!=reference_signature(manifest)
    manifest.write_text(json.dumps({'objects':[{'images':['../outside.jpg']}]}))
    with pytest.raises(ValueError,match='PATH'):reference_signature(manifest)


def test_presentation_controls_cannot_override_materials():
    class Fake:
        settings=type('Settings',(),{'vision_model':'test'})()
        def call(self,*args):return {**presentation_settings(NEUTRAL),'palette':{'building':'#ff0000'}}
    with pytest.raises(ValueError,match='PRESENTATION'):presentation_settings(NEUTRAL,Fake())
    assert 'palette' not in NEUTRAL and 'texture_strength' not in NEUTRAL


def test_object_patch_does_not_require_exported_factory_and_rejects_ambiguous_anchor():
    fragment='function buildObservedObject(b:any) {const roofHeight=4; return new THREE.Group();}'
    assert 'roofHeight=3' in patch_fragment(fragment,[{'old':'roofHeight=4','new':'roofHeight=3'}])
    with pytest.raises(ValueError,match='ANCHOR'):patch_fragment('a a',[{'old':'a','new':'b'}])
    fragment=';'.join(f'part_{i}=0' for i in range(18))
    assert patch_fragment(fragment,[{'old':f'part_{i}=0','new':f'part_{i}=1'} for i in range(18)]).count('=1')==18


def test_repair_prompt_contains_actual_gate_failures_not_truncated_metadata(tmp_path):
    from building_workflow.urban.generate import PROXY_SOURCE,repair_source
    (tmp_path/'building-generator.ts').write_text(PROXY_SOURCE)
    (tmp_path/'urban-geometry-checks.json').write_text(json.dumps({'meshes':['x'*10000],'lodPlanPresent':False,'failures':['part-0042 openEdges=8']}))
    class Fake:
        settings=type('Settings',(),{'code_model':'test'})()
        def call(self,stage,prompt,*args):
            assert 'ACTUAL_GATE_FAILURES' in prompt and 'part-0042 openEdges=8' in prompt
            assert 'Do not add LOD' in prompt and 'x'*100 not in prompt
            return {'edits':[{'old':PROXY_SOURCE,'new':PROXY_SOURCE+'\n// checked'}]}
    repair_source(tmp_path,Fake(),RuntimeError('GATE_FAILED'))


def test_explicit_code_resume_does_not_allow_changed_input_or_budget(tmp_path):
    from building_workflow.urban.runner import update_run_config
    config={'implementation_hash':'old','images':'frozen','max_calls':12}
    update_run_config(tmp_path,config)
    with pytest.raises(ValueError):update_run_config(tmp_path,{**config,'implementation_hash':'new'})
    update_run_config(tmp_path,{**config,'implementation_hash':'new'},True)
    assert len(list((tmp_path/'config-history').glob('*.json')))==1
    with pytest.raises(ValueError):update_run_config(tmp_path,{**config,'images':'changed'},True)
    with pytest.raises(ValueError):update_run_config(tmp_path,{**config,'max_calls':20},True)


def test_reusable_object_module_tracks_final_validated_source(tmp_path):
    from building_workflow.urban.objects import sync_object_sources,compose_sources
    from building_workflow.urban.generate import PROXY_SOURCE
    item={'object_id':'one','function':'buildObserved_one','folder':'objects/one'}
    folder=tmp_path/item['folder'];folder.mkdir(parents=True)
    (folder/'generator.ts').write_text('function buildObserved_one(b:any) { return null; }')
    (tmp_path/'object-observations.json').write_text(json.dumps({'objects':[item]}))
    fragment='function buildObserved_one(b:any) { const m=new THREE.MeshStandardMaterial({color:0x123456});return new THREE.Group(); }'
    (tmp_path/'building-generator.ts').write_text(fragment+'\nexport function build(params:any={}) {return buildObserved_one(params);}')
    (tmp_path/'base-building-generator.ts').write_text(PROXY_SOURCE)
    sync_object_sources(tmp_path)
    assert '0x123456' in (folder/'generator.ts').read_text()
    assert len(list((folder/'source-history').glob('*.ts')))==1
    compose_sources(tmp_path,[item])
    assert '0x123456' in (tmp_path/'building-generator.ts').read_text()


def test_cell_dependencies_include_furniture_and_referenced_object(tmp_path):
    city={'cells':[{'id':'a','bounds':[0,0,10,10],'owned':[],'references':['one']}],
          'buildings':[{'id':'one','height':8}],'surfaces':{},'trees':[{'id':'t','position':[2,2],'seed':1}]}
    original=cell_artifacts(city,NEUTRAL,tmp_path)
    city['trees'][0]['seed']=2
    assert cell_artifacts(city,NEUTRAL,tmp_path)[0]['geometry_input_hash']!=original[0]['geometry_input_hash']
    previous=cell_artifacts(city,NEUTRAL,tmp_path)
    city['buildings'][0]['height']=12
    assert cell_artifacts(city,NEUTRAL,tmp_path)[0]['geometry_input_hash']!=previous[0]['geometry_input_hash']


def test_every_observed_object_is_reviewed_and_major_issue_blocks_acceptance(tmp_path):
    items=[{'object_id':key,'folder':'objects/'+key,'observation':{},'reference':{}} for key in ['one','two']]
    (tmp_path/'object-observations.json').write_text(json.dumps({'objects':items}))
    for item in items:
        folder=tmp_path/item['folder'];folder.mkdir(parents=True);Image.new('RGB',(10,10)).save(folder/'reference-00.jpg')
    class Fake:
        settings=type('Settings',(),{'review_model':'test'})()
        count=0
        def call(self,stage,prompt,images,*args):
            self.count+=1;assert len(images)==3
            return {'accepted':True,'issues':[{'severity':'major','cause':'geometry','part':'roof'}]}
    fake=Fake();report=inspect_objects(tmp_path,fake,0)
    assert fake.count==2 and len(report['objects'])==2
    assert report['technical_valid'] and not report['visual_accepted']
    assert not any(o['accepted'] for o in report['objects'])
    assert object_view_name('one')!=object_view_name('two')


def test_footprint_diagram_preserves_holes(tmp_path):
    path=tmp_path/'footprint.png'
    footprint_sheet({'outer':[[0,0],[10,0],[10,10],[0,10]],'holes':[[[3,3],[7,3],[7,7],[3,7]]]},path)
    im=Image.open(path)
    assert im.getpixel((75+5*49,85+5*49))!=(im.getpixel((75+1*49,85+1*49)))


def test_worker_deduplicates_exact_geometry_and_preserves_baked_rotation(tmp_path):
    import subprocess
    from playwright.sync_api import sync_playwright
    from building_workflow.config import ROOT
    source=tmp_path/'generator.ts';bundle=tmp_path/'worker.js'
    source.write_text('''import * as THREE from 'three';
export function build(params:any={}) {
 const root=new THREE.Group();
 for(let i=0;i<3;i++) {const group=new THREE.Group();group.userData.objectId=String(i);
 const geo=new THREE.BoxGeometry(2,4,6);if(i<2)geo.rotateX(Math.PI/2);
 const m=new THREE.MeshStandardMaterial({color:i===0?0xff0000:0x0000ff});
 group.add(new THREE.Mesh(geo,m));group.position.x=i*10;root.add(group);} return root;
}''')
    subprocess.run(['node',str(ROOT/'runtime/urban-bundle.mjs'),'worker',str(source),str(bundle)],cwd=ROOT,check=True,capture_output=True)
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,chromium_sandbox=True);page=browser.new_page();page.set_content('<body></body>')
        result=page.evaluate('''code=>new Promise((resolve,reject)=>{const w=new Worker(URL.createObjectURL(new Blob([code],{type:'text/javascript'})));w.onmessage=e=>{w.terminate();resolve(e.data)};w.onerror=e=>reject(Error(e.message));w.postMessage({buildings:[{id:'0'},{id:'1'},{id:'2'}]});})''',bundle.read_text())
        browser.close()
    assert result['ok'] and result['metrics']['unique_geometries']==2
    assert result['metrics']['mesh_objects']==3
    first=result['metrics']['objects'][0]
    assert first['max'][1]-first['min'][1]==pytest.approx(6)
    assert first['max'][2]-first['min'][2]==pytest.approx(4)
