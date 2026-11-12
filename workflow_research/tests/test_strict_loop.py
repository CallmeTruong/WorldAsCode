import copy
import pytest
from building_workflow.urban.strict_loop import acceptance,nonregressing,DIMENSIONS

def review():
    return {'scores':dict.fromkeys(DIMENSIONS,4),'issues':[],'evidence_sufficient':True,'action':'accept'}

def test_each_dimension_and_evidence_block_acceptance():
    good=review();assert acceptance(good)
    for d in DIMENSIONS:
        bad=copy.deepcopy(good);bad['scores'][d]=3;assert not acceptance(bad)
    for severity in ('major','critical'):
        bad=review();bad['issues']=[{'severity':severity}];assert not acceptance(bad)
    bad=review();bad['evidence_sufficient']=False;assert not acceptance(bad)
    bad=review();bad['action']='request_evidence';assert not acceptance(bad)

def test_reject_invalid_review_and_average_score_regression():
    bad=review();bad['scores']['roof']=float('nan')
    with pytest.raises(ValueError):acceptance(bad)
    old=review();new=review();new['scores']['facade']=5;new['scores']['roof']=3
    assert not nonregressing(old,new)
    new['scores']['roof']=4;assert nonregressing(old,new)
    assert not nonregressing(old,old)
    old['issues']=[{'severity':'major'}];new=copy.deepcopy(old);new['issues']=[]
    assert nonregressing(old,new)


def test_regressing_patch_rolls_back_and_heldout_never_enters_patch(tmp_path,monkeypatch):
    import hashlib,json
    from types import SimpleNamespace
    from building_workflow.urban import strict_loop as loop
    identifier='way/1/0';key=hashlib.sha256(identifier.encode()).hexdigest()[:12]
    run=tmp_path/'run';evidence=tmp_path/'evidence';run.mkdir();evidence.mkdir()
    component=run/'components'/key/'generator.ts';component.parent.mkdir(parents=True)
    original='function buildComponent(b:any) { return new THREE.Group(); }';component.write_text(original)
    (run/'building-generator.ts').write_text('parent')
    (run/'city.json').write_text(json.dumps({'buildings':[{'id':identifier}]}))
    (run/'scene-plan.json').write_text(json.dumps({'buildings':[{'object_id':identifier}]}))
    (evidence/'source-views.json').write_text(json.dumps({'views':[{'id':n,'held_out':n=='reserved'} for n in ['overhead','south','west','reserved']]}))
    monkeypatch.setattr(loop,'capture_city',lambda *a,**k:{'ok':True})
    monkeypatch.setattr(loop,'sync_scene_components',lambda *a:None)
    monkeypatch.setattr(loop,'capture_with_repair',lambda *a,**k:None)
    monkeypatch.setattr(loop,'compose_scene',lambda *a:(run/'building-generator.ts').write_text('candidate'))
    monkeypatch.setattr(loop,'paired_images',lambda run,e,views,*a:[tmp_path/(v['id']+'.jpg') for v in views])
    monkeypatch.setattr(loop,'target_packet',lambda *a:{})
    initial=review();initial['scores']['roof']=2;initial['action']='repair'
    candidate=copy.deepcopy(initial);candidate['scores']['roof']=3;candidate['scores']['facade']=3
    outputs=iter([initial,{'edits':[{'old':'return new THREE.Group();','new':'const g=new THREE.Group(); return g;'}]},candidate,review()]);calls=[]
    def call(stage,prompt,images,*args):calls.append((stage,[p.name for p in images]));return next(outputs)
    provider=SimpleNamespace(settings=SimpleNamespace(model='gpt-6-sol',review_model='gpt-6-sol',code_model='gpt-6-sol'),usage={},call=call,save_usage=lambda:None)
    result=loop.run_target(run,evidence,identifier,provider,max_repairs=1)
    assert result['status']=='stagnated' and not result['accepted']
    assert component.read_text()==original and (run/'building-generator.ts').read_text()=='parent'
    assert all('reserved.jpg' not in images for stage,images in calls if not stage.endswith('heldout'))


def test_target_packet_uses_same_local_origin_for_camera_and_footprint():
    from building_workflow.urban.strict_loop import target_packet
    b={'center':[100,200],'outer':[[99,198],[103,198],[103,202]],'height':20}
    views=[{'id':'south','local_camera':{'position':[110,50,220],'direction':[0,-1,-1],'up':[0,1,0],'fov':45,'aspect':4/3}}]
    packet=target_packet(b,views)
    assert packet['local_building']['outer'][0]==[-1,-2]
    assert packet['views'][0]['camera_target_local']['position']==[10,50,20]
    assert packet['edges'][0]['length_m']==4


def test_runtime_restore_rejects_stale_source(tmp_path):
    import json
    from building_workflow.urban.strict_loop import restore_runtime
    run=tmp_path/'run';checkpoint=tmp_path/'checkpoint';run.mkdir();checkpoint.mkdir()
    (checkpoint/'building-generator.ts').write_text('source')
    (checkpoint/'urban-runtime-result.json').write_text(json.dumps({'ok':True,'metrics':{'source_sha256':'stale'}}))
    with pytest.raises(RuntimeError,match='RESTORED_RUNTIME_SOURCE_MISMATCH'):restore_runtime(run,checkpoint)


def test_legacy_checkpoint_invalidates_rejected_capture_manifest(tmp_path):
    import json,hashlib
    from building_workflow.urban.strict_loop import snapshot_runtime,restore_runtime
    run=tmp_path/'run';run.mkdir();checkpoint=tmp_path/'checkpoint'
    (run/'building-generator.ts').write_text('accepted source')
    (run/'urban-runtime-result.json').write_text(json.dumps({'ok':True,'metrics':{'source_sha256':hashlib.sha256(b'accepted source').hexdigest()}}))
    snapshot_runtime(run,checkpoint)
    (run/'building-generator.ts').write_text('rejected source')
    (run/'evidence-captures.json').write_text(json.dumps({'contract':'matching-source-visibility-v2','source_sha256':'rejected','views':[]}))
    restore_runtime(run,checkpoint)
    assert (run/'building-generator.ts').read_text()=='accepted source'
    assert json.loads((run/'evidence-captures.json').read_text())['contract']=='invalidated'
    assert json.loads((run/'invalidated-evidence-captures.json').read_text())['source_sha256']=='rejected'
