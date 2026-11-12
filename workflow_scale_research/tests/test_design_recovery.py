from worldscale import design
from worldscale.artifacts import write_json


def partial_run(folder):
    write_json(folder/'input-manifest.json',{'evidence_sha256':'pinned'})
    write_json(folder/'site.json',{'object_id':'held-out'})
    write_json(folder/'usage.json',{'calls':3,'unknown_token_reserve':12000})
    for i in range(2):
        attempt=folder/f'attempt-{i}'
        attempt.mkdir()
        (attempt/'design.mjs').write_text('export function design(){}')
        write_json(attempt/'metrics.json',{'passed':True,'mean_oblique_iou':.9})
    write_json(folder/'attempt-0/review.json',{'likeness':.6,'style':.7,'detail':.4})


def test_recovery_keeps_last_review_and_never_promotes_unreviewed_render(tmp_path):
    partial_run(tmp_path)
    result=design.recover_design(tmp_path,'STREAM_PROVIDER_ERROR')
    assert result['best_attempt']==0
    assert not result['accepted'] and not result['evaluation_complete']
    assert result['attempts'][1]['evaluation']=='unreviewed'
    assert result['usage']['calls']==3 and result['usage']['unknown_token_reserve']==12000


def test_provider_failure_returns_inspectable_partial_result_without_retry(tmp_path,monkeypatch):
    calls=[]

    def fail(*args,**kwargs):
        calls.append(True)
        partial_run(tmp_path)
        raise RuntimeError('STREAM_PROVIDER_ERROR')

    monkeypatch.setattr(design,'_run_design',fail)
    result=design.run_design(None,[],tmp_path,None)
    assert len(calls)==1 and result['best_attempt']==0
    assert 'STREAM_PROVIDER_ERROR' in result['error']


def test_recovery_does_not_demote_a_completed_run(tmp_path):
    completed={'status':'designed','accepted':True,'best_attempt':0}
    write_json(tmp_path/'result.json',completed)
    assert design.recover_design(tmp_path)==completed
