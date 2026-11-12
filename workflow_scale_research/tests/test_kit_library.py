import json
import shutil

import pytest

from worldscale.artifacts import file_hash, write_json
from worldscale.kit_evolution import apply_proposal
from worldscale.kit_library import Library


def candidate(library,tmp_path,name='roofFixture'):
    base,_=library.resolve()
    folder=tmp_path/name
    shutil.copytree(base,folder/'runtime')
    proposal={'edits':[],'new_methods':[{'name':name,'code':f'  {name}(o={{}}) {{ return this.roof(o); }}'}]}
    source,_=apply_proposal((base/'kit.mjs').read_text(encoding='utf-8'),proposal,{'roof'})
    (folder/'runtime/kit.mjs').write_text(source,encoding='utf-8')
    write_json(folder/'proposal.json',proposal)
    write_json(folder/'permissions.json',{'granted_methods':['roof'],'base_sha256':file_hash(base/'kit.mjs')})
    write_json(folder/'exercise.json',{'method':name,'options':{'material':'brick'}})
    write_json(folder/'decision.json',{'activated':True,'candidate_sha256':file_hash(folder/'runtime/kit.mjs')})
    manifest=folder/'active-kit.json'
    write_json(manifest,{'path':str(folder/'runtime/kit.mjs'),'sha256':file_hash(folder/'runtime/kit.mjs'),
        'scope':'run-local','modules':{p.name:file_hash(p) for p in (folder/'runtime').glob('*.mjs')},
        'validation_path':str(folder/'decision.json'),'validation_sha256':file_hash(folder/'decision.json')})
    return manifest


@pytest.fixture
def library(tmp_path,monkeypatch):
    library=Library(tmp_path/'library')
    library.initialize()
    calls=[]

    def regressions(*args):
        calls.append(args)
        return [{'case':i,'passed':True} for i in range(3)]

    monkeypatch.setattr('worldscale.adaptive.regressions',regressions)
    library.fixture_calls=calls
    return library


def test_permissions_revocation_and_scope(library,tmp_path):
    manifest=candidate(library,tmp_path)
    with pytest.raises(ValueError,match='GRANT_REQUIRED'):
        library.submit(manifest,'buildings',None)
    token=library.grant('workflow',['buildings'],['submit'])
    with pytest.raises(ValueError,match='SCOPE'):
        library.submit(manifest,'vegetation',token)
    library.revoke(token)
    with pytest.raises(ValueError,match='REVOKED'):
        library.submit(manifest,'buildings',token)
    expired=library.grant('workflow',['buildings'],['submit'])
    path=library.root/'grants'/f'{expired}.json'
    grant=json.loads(path.read_text())
    grant['expires_at']='2000-01-01T00:00:00+00:00'
    write_json(path,grant)
    with pytest.raises(ValueError,match='EXPIRED'):
        library.submit(manifest,'buildings',expired)


def test_publish_pin_and_rollback_do_not_mutate_existing_job(library,tmp_path):
    builtin,_=library.resolve()
    builtin_version=builtin.name
    token=library.grant('workflow',['buildings'],['submit','promote-incubating','set-default','rollback'])
    submission=library.submit(candidate(library,tmp_path),'buildings',token)
    with pytest.raises(FileNotFoundError):
        library.promote(submission['id'],'incubating',token)
    validation=library.validate(submission['id'])
    assert validation['incubating_eligible'] and not validation['stable_eligible']
    assert len(library.fixture_calls)==2
    release=library.promote(submission['id'],'incubating',token,set_default=True)
    pinned=library.pin(tmp_path/'job')
    old_hash=file_hash(pinned)
    library.rollback('buildings','incubating',builtin_version,token,subject='workflow')
    assert library.resolve()[0].name==builtin_version
    assert file_hash(pinned)==old_hash and release['version']!=builtin_version
    assert library.verify_release('buildings',release['version'])


def test_permission_never_bypasses_stable_validation(library,tmp_path):
    token=library.grant('workflow',['buildings'],['submit','promote-stable'])
    submission=library.submit(candidate(library,tmp_path),'buildings',token)
    library.validate(submission['id'])
    with pytest.raises(ValueError,match='GATES_FAILED'):
        library.promote(submission['id'],'stable',token)
    validation_path=library.root/'submissions'/submission['id']/'validation.json'
    validation=json.loads(validation_path.read_text())
    validation['stable_eligible']=True
    write_json(validation_path,validation)
    with pytest.raises(ValueError,match='GATES_FAILED'):
        library.promote(submission['id'],'stable',token)


def test_stale_branch_cannot_overwrite_shared_head(library,tmp_path):
    token=library.grant('workflow',['buildings'],['submit','promote-incubating','set-default'])
    a=library.submit(candidate(library,tmp_path,'roofA'),'buildings',token)
    b=library.submit(candidate(library,tmp_path,'roofB'),'buildings',token)
    library.validate(a['id'])
    library.validate(b['id'])
    library.promote(a['id'],'incubating',token,set_default=True)
    with pytest.raises(ValueError,match='REBASE_REQUIRED'):
        library.promote(b['id'],'incubating',token,set_default=True)


def test_changed_submission_and_release_are_rejected(library,tmp_path):
    token=library.grant('workflow',['buildings'],['submit'])
    item=library.submit(candidate(library,tmp_path),'buildings',token)
    source=library.root/'submissions'/item['id']/'runtime/kit.mjs'
    source.write_text('tampered')
    with pytest.raises(ValueError,match='SUBMISSION_CHANGED'):
        library.validate(item['id'])
    folder,_=library.resolve()
    (folder/'kit-api.md').write_text('tampered API')
    with pytest.raises(ValueError,match='FILE_MISMATCH'):
        library.resolve()


def test_channel_head_is_protected_even_when_not_default(library,tmp_path):
    token=library.grant('workflow',['buildings'],['submit','promote-incubating'])
    a=library.submit(candidate(library,tmp_path,'roofA'),'buildings',token)
    b=library.submit(candidate(library,tmp_path,'roofB'),'buildings',token)
    library.validate(a['id'])
    library.validate(b['id'])
    library.promote(a['id'],'incubating',token)
    with pytest.raises(ValueError,match='REBASE_REQUIRED'):
        library.promote(b['id'],'incubating',token)
