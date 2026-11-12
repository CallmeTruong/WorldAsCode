"""Orchestration contracts; mocked scores do not establish visual quality."""

import json

from worldscale import adaptive, kit_evolution
from worldscale.artifacts import file_hash, write_json


def test_consumer_repairs_new_option_usage_before_rewriting_kit(tmp_path, monkeypatch):
    source=tmp_path/'source'
    (source/'attempt-0').mkdir(parents=True)
    (source/'attempt-0/design.mjs').write_text('original design')
    evidence=tmp_path/'evidence.json'
    write_json(evidence,{'fixture':True})
    write_json(source/'result.json',{'best_attempt':0,'evidence_sha256':file_hash(evidence)})
    write_json(source/'site.json',{})
    write_json(source/'style.json',{})
    write_json(source/'fit.json',{'evidence_path':str(evidence)})
    (source/'reference-details.jpg').touch()
    monkeypatch.setattr(adaptive.georef,'load_evidence',lambda path:{'path':str(evidence)})
    calls=[]

    def propose(provider,folder,base,history,images,site):
        folder.mkdir()
        kit=kit_evolution.snapshot(folder/'runtime')
        write_json(folder/'permissions.json',{'added_methods':[], 'consumer_required':True})
        write_json(folder/'exercise.json',{'method':'roof','options':{'newOption':True}})
        write_json(folder/'proposal.json',{'requires_design_update':True})
        return kit

    monkeypatch.setattr(adaptive.kit_evolution,'propose',propose)
    monkeypatch.setattr(adaptive,'regressions',lambda *a:[{'passed':True}])

    def author(provider,node,site,style,images,previous,feedback,kit_api):
        calls.append((node,feedback))
        return {'code':'repaired caller' if 'repair' in node else 'invalid caller'}

    def render(folder,code,*args,**kwargs):
        folder.mkdir(parents=True)
        (folder/'design.mjs').write_text(code)
        if code=='invalid caller':
            return None,'RUNTIME: KIT_INVALID_WING_RECTANGLE'
        return {'passed':True,'mean_oblique_iou':.88},None

    def critic(provider,node,*args):
        return {'likeness':.6,'style':.6,'detail':.4 if 'baseline' in node else .48}

    monkeypatch.setattr(adaptive.design,'author',author)
    monkeypatch.setattr(adaptive.design,'render_attempt',render)
    monkeypatch.setattr(adaptive.design,'critic',critic)

    class Provider:
        usage={}

        def save(self):
            pass

    run=tmp_path/'run'
    result=adaptive.evolve_design(source,run,None,provider=Provider())
    assert [c[0] for c in calls]==['kit-consumer-0','kit-consumer-repair-0']
    assert calls[1][1]['build_error']=='RUNTIME: KIT_INVALID_WING_RECTANGLE'
    assert result['cycles'][0]['activated']
    assert result['shared_runtime_unchanged']
    # A relative improvement still falls below the absolute detail threshold.
    assert not result['accepted']
    assert result['selected_render'].endswith('render-repair')
    manifest=json.loads((run/'active-kit.json').read_text())
    assert manifest['scope']=='run-local'
    assert kit_evolution.copy_active_version(run/'active-kit.json',tmp_path/'reuse').exists()
