import copy,json,subprocess
import pytest
from building_workflow.config import ROOT
from building_workflow.urban.coordinated import validate_observations,validate_review,work_order,review_better
from building_workflow.urban.scene_first import DIMENSIONS


def observations():
    return {'objects':[{'owner':'way/1/0','features':[{'id':'roof-1','part':'roof','observation':'Connected pitched wings with readable ridges.','evidence_views':['west'],'confidence':'high','importance':'identity'}]}],'shared_scene_features':[{'id':'street-grid','observation':'Shared streets'}],'style_contract':[{'id':'style-detail','observation':'Readable architectural detail','application':'Model visible relief.'}]}


def review():
    return {'scores':dict.fromkeys(DIMENSIONS,4),'issues':[], 'object_checks':[{'owner':'way/1/0','features':[{'id':'roof-1','status':'matched','evidence':'Paired west views.'}]}],'style_checks':[{'id':'style-detail','status':'matched','evidence':'Visible relief.'}]}


def test_missing_identity_and_style_block_optimistic_scores():
    r=review();r['object_checks'][0]['features'][0]['status']='missing'
    result=validate_review(r,observations());assert not result['accepted']
    assert result['issues'][0]['id']=='roof-1' and result['issues'][0]['gate_added']
    r=review();r['style_checks'][0]['status']='missing';assert not validate_review(r,observations())['accepted']


def test_critic_cannot_skip_features_or_style():
    r=review();r['object_checks'][0]['features']=[]
    with pytest.raises(ValueError,match='FEATURE_COVERAGE'):validate_review(r,observations())
    r=review();r['style_checks']=[]
    with pytest.raises(ValueError,match='STYLE_COVERAGE'):validate_review(r,observations())
    assert validate_observations(observations(),{'buildings':[{'id':'way/1/0'}]})


def test_critic_may_separately_report_shared_scene_without_losing_target_checks():
    r=review();r['object_checks'].append({'owner':'shared_scene','features':[{'id':'street-grid','status':'partial'}]})
    result=validate_review(r,observations());assert result['accepted']
    assert len(result['object_checks'])==1 and result['shared_checks'][0]['owner']=='shared_scene'
    r=review();r['object_checks'].append({'owner':'scene','features':[{'id':'street-grid','status':'partial'}]})
    assert validate_review(r,observations())['accepted']
    r=review();r['object_checks'].append({'owner':'imagined neighbor','features':[{'id':'unknown','status':'matched'}]})
    with pytest.raises(ValueError,match='UNKNOWN_OWNER'):validate_review(r,observations())


def test_planner_routes_actual_critic_issues_and_progress_tracks_stable_ids():
    r=review();r['issues']=[{'id':'minor','severity':'minor','owner':'scene','evidence':'x','repair':'x'}, {'id':'roof-1','severity':'major','owner':'way/1/0','evidence':'No ridges.','repair':'Replace roof.'}]
    plan=work_order(r,observations(),1);assert plan['tasks'][0]['id']=='roof-1'
    better=copy.deepcopy(r);better['issues']=better['issues'][:1];assert review_better(r,better)
    better['scores']['identity']=1;assert not review_better(r,better)


def test_trusted_roof_tools_are_closed_and_keep_local_dimensions():
    code="""import * as THREE from 'three';import {gableRoof,hipRoof,extrudeFootprint} from './runtime/urban-geometry-tools.mjs';
const material=new THREE.MeshStandardMaterial();const meshes=[gableRoof({length:12,width:8,eave:10,rise:4,center:[3,5],rotation:.4,material}),hipRoof({length:15,width:10,eave:9,rise:3,inset:2,material}),extrudeFootprint({outer:[[0,0],[8,0],[8,8],[0,8]],holes:[[[2,2],[2,6],[6,6],[6,2]]],height:4,material})];
console.log(JSON.stringify(meshes.map(mesh=>{const g=mesh.geometry,p=g.attributes.position,n=g.attributes.normal;return {vertices:Array.from({length:p.count},(_,i)=>[p.getX(i),p.getY(i),p.getZ(i)]),normals:Array.from({length:n.count},(_,i)=>[n.getX(i),n.getY(i),n.getZ(i)]),indices:g.index?Array.from(g.index.array):Array.from({length:p.count},(_,i)=>i)};})));"""
    output=subprocess.run(['node','--input-type=module','-e',code],cwd=ROOT,capture_output=True,text=True,check=True)
    meshes=json.loads(output.stdout)
    from building_workflow.skills import geometry_gate
    result=geometry_gate({'meshes':[dict(m,id='roof-tool-'+str(i),role='architectural') for i,m in enumerate(meshes)],'triangleBudget':10000})
    assert result['passed'],result


def test_controller_passes_critic_feedback_to_coder_and_rechecks_real_result(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from building_workflow.urban import coordinated as module
    parent=tmp_path/'parent';parent.mkdir();run=tmp_path/'run';run.mkdir()
    seed="import * as THREE from 'three'; export function build(params:any={}) { return new THREE.Group(); }"
    (parent/'building-generator.ts').write_text(seed)
    (run/'city.json').write_text('{}')
    flow=module.SceneWorkflow.__new__(module.SceneWorkflow)
    flow.parent=parent;flow.run=run;flow.source=run/'building-generator.ts';flow.city={};flow.events=[];flow.max_repairs=1;flow.resume=False
    flow.training=[];flow.details=[];flow.held=[]
    flow.api=SimpleNamespace(usage={},trace=lambda *a,**k:None,save_usage=lambda:None)
    flow.observer=lambda:observations()
    def render(stage):
        result={'ok':True,'metrics':{'source_sha256':__import__('hashlib').sha256(flow.source.read_bytes()).hexdigest()}}
        (run/'urban-runtime-result.json').write_text(json.dumps(result));return result
    flow.render=render
    initial=review();initial['scores']=dict.fromkeys(DIMENSIONS,2);initial['accepted']=False
    initial['issues']=[{'id':'roof-1','owner':'way/1/0','severity':'major','part':'roof','evidence':'Render is flat.','repair':'Replace with connected pitched wings.'}]
    fixed=review();fixed['accepted']=True;reviews=iter([initial,fixed,fixed]);received=[];checked=[]
    def critic(index,obs,previous=None,tasks=None,validation=False):
        checked.append((index,previous,tasks,validation));return next(reviews),[]
    flow.critic=critic
    def coder(index,order,obs,images):
        received.append(order);flow.source.write_text(seed+'\n// coded by workflow node')
    flow.coder=coder
    monkeypatch.setattr(module,'make_report',lambda *a:None)
    monkeypatch.setattr(module,'validate_evidence_captures',lambda *a:{})
    result=flow.execute()
    assert result['accepted']
    assert received[0]['tasks'][0]['repair']=='Replace with connected pitched wings.'
    assert checked[1][1] is initial and checked[1][2] is received[0]
    assert checked[-1][-1] is True
    assert [e['node'] for e in flow.events]==['observe','validate-initial','critic-0','plan-1','code-1','validate-1','critic-1','heldout-critic']


def test_evidence_gate_rejects_changed_pixels_or_wrong_isolation(tmp_path):
    import hashlib
    from building_workflow.urban.coordinated import validate_evidence_captures
    (tmp_path/'renders').mkdir();(tmp_path/'building-generator.ts').write_text('source')
    image=tmp_path/'renders/evidence-detail.png';image.write_bytes(b'pixels')
    view={'id':'detail','object_id':'way/1/0','local_camera':{'position':[1,2,3]}}
    record={'id':'detail','object_id':'way/1/0','mode':'isolated-object','visible_object_ids':['way/1/0'],'camera':view['local_camera'],'sha256':hashlib.sha256(image.read_bytes()).hexdigest()}
    data={'contract':'matching-source-visibility-v2','source_sha256':hashlib.sha256(b'source').hexdigest(),'views':[record]}
    path=tmp_path/'evidence-captures.json';path.write_text(json.dumps(data))
    assert validate_evidence_captures(tmp_path,[view])
    record['mode']='whole-scene';path.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='VISIBILITY'):validate_evidence_captures(tmp_path,[view])
    record['mode']='isolated-object';path.write_text(json.dumps(data));image.write_bytes(b'stale different pixels')
    with pytest.raises(ValueError,match='IMAGE_CHANGED'):validate_evidence_captures(tmp_path,[view])
