"""Versioned shared kit registry. Host-held grants never enter model prompts."""

import fnmatch
import json
import re
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .artifacts import digest, file_hash, run_lock, write_json
from .config import ROOT
from .kit_context import cards

SLUG=re.compile(r'^[a-z][a-z0-9.-]{0,79}$')
ACTIONS={'submit','promote-incubating','promote-stable','set-default','rollback'}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def now():
    return datetime.now(timezone.utc)


def package_files(folder):
    folder=Path(folder)
    names={'kit.mjs','kit-api.md','capabilities.json'}
    pending=['kit.mjs']
    while pending:
        name=pending.pop()
        for dep in re.findall(r"from\s+['\"]\./([^'\"]+)['\"]",(folder/name).read_text(encoding='utf-8')):
            if Path(dep).name!=dep:
                raise ValueError('KIT_UNSUPPORTED_DEPENDENCY_PATH')
            if dep not in names:
                names.add(dep)
                pending.append(dep)
    return [folder/name for name in sorted(names)]


class Library:
    def __init__(self, root=None):
        self.root=Path(root or ROOT/'kit_library').resolve()

    def initialize(self, source=None):
        """Bootstrap the existing SDK, explicitly not a new validated release."""
        self.root.mkdir(parents=True,exist_ok=True)
        with run_lock(self.root):
            if (self.root/'registry.json').exists():
                return read(self.root/'registry.json')
            source=Path(source or ROOT/'runtime')
            files=package_files(source)
            hashes={p.name:file_hash(p) for p in files}
            version=digest(hashes)
            folder=self.root/'releases/buildings'/version
            folder.mkdir(parents=True)
            for path in files:
                shutil.copy2(path,folder/path.name)
            write_json(folder/'release.json',{'schema':'shared-kit-release-1','package':'buildings','version':version,
                'files':hashes,'origin':'builtin snapshot; no new cross-site quality claim','channel':'builtin'})
            write_json(folder/'context-index.json',{'cards':[{'id':c['id'],'methods':c['methods']} for c in cards(folder/'kit-api.md').values()]})
            registry={'schema':'shared-kit-registry-1','revision':1,'packages':{'buildings':{
                'summary':'Metric building geometry, roof/facade/material authoring',
                'channels':{'builtin':version,'incubating':None,'stable':None},'default_channel':'builtin'}}}
            write_json(self.root/'policy.json',{'schema':'kit-release-policy-1','incubating':{'require_local_activation':True,
                'minimum_fixture_cases':3},'stable':{'minimum_distinct_accepted_sites':2},
                'note':'Permissions do not bypass validation. Stable is not granted automatically.'})
            write_json(self.root/'registry.json',registry)
            return registry

    def grant(self, subject, packages, actions, hours=24*30):
        if not set(actions)<=ACTIONS or not actions or not subject or not 0<hours<=24*366:
            raise ValueError('INVALID_KIT_GRANT')
        if not packages or any(not SLUG.fullmatch(p) for p in packages):
            raise ValueError('INVALID_KIT_PACKAGE_SCOPE')
        token=uuid.uuid4().hex
        record={'id':token,'subject':subject,'packages':packages,'actions':sorted(set(actions)),
                'expires_at':(now()+timedelta(hours=hours)).isoformat(),'revoked':False}
        write_json(self.root/'grants'/f'{token}.json',record,exclusive=True)
        return token

    def authorize(self, token, subject, package, action):
        if not re.fullmatch(r'[a-f0-9]{32}',token or ''):
            raise ValueError('KIT_GRANT_REQUIRED')
        grant=read(self.root/'grants'/f'{token}.json')
        if grant['revoked'] or grant['subject']!=subject or now()>=datetime.fromisoformat(grant['expires_at']):
            raise ValueError('KIT_GRANT_EXPIRED_OR_REVOKED')
        if action not in grant['actions'] or not any(fnmatch.fnmatchcase(package,p) for p in grant['packages']):
            raise ValueError('KIT_GRANT_SCOPE_DENIED')
        return grant

    def revoke(self, token):
        if not re.fullmatch(r'[a-f0-9]{32}',token):
            raise ValueError('INVALID_KIT_GRANT_ID')
        with run_lock(self.root):
            path=self.root/'grants'/f'{token}.json'
            record=read(path)
            record['revoked']=True
            write_json(path,record)

    def verify_release(self, package, version):
        if not SLUG.fullmatch(package) or not re.fullmatch(r'[a-f0-9]{64}',version):
            raise ValueError('INVALID_KIT_RELEASE_ID')
        folder=self.root/'releases'/package/version
        release=read(folder/'release.json')
        if release['package']!=package or release['version']!=version or digest(release['files'])!=version:
            raise ValueError('KIT_RELEASE_DESCRIPTOR_MISMATCH')
        for name,expected in release['files'].items():
            if Path(name).name!=name or file_hash(folder/name)!=expected:
                raise ValueError('KIT_RELEASE_FILE_MISMATCH')
        return folder,release

    def resolve(self, package='buildings', channel=None, version=None):
        package_record=read(self.root/'registry.json')['packages'][package]
        channel=channel or package_record['default_channel']
        if channel not in ('builtin','incubating','stable'):
            raise ValueError('INVALID_KIT_CHANNEL')
        version=version or package_record['channels'].get(channel) or package_record['channels']['builtin']
        folder,release=self.verify_release(package,version)
        return folder,{'package':package,'channel':channel,'version':version,'kit_sha256':release['files']['kit.mjs']}

    def pin(self, destination, package='buildings', channel=None, version=None):
        folder,selection=self.resolve(package,channel,version)
        shutil.copytree(folder,destination)
        write_json(Path(destination)/'library-selection.json',selection)
        return Path(destination)/'kit.mjs'

    def search(self, query, limit=6):
        if not 1<=limit<=12:
            raise ValueError('KIT_SEARCH_LIMIT')
        words=set(re.findall(r'\w+',query.lower()))
        matches=[]
        for name,entry in read(self.root/'registry.json')['packages'].items():
            text=(name+' '+entry['summary']).lower()
            score=sum(word in text for word in words)
            if score:
                matches.append((score,{'package':name,'summary':entry['summary'],'default_channel':entry['default_channel']}))
        return [entry for _,entry in sorted(matches,key=lambda item:item[0],reverse=True)[:limit]]

    def submit(self, manifest, package, token, subject='workflow'):
        self.authorize(token,subject,package,'submit')
        if not SLUG.fullmatch(package):
            raise ValueError('INVALID_KIT_PACKAGE')
        # Verify the local activation and dependencies using the same loader used
        # by design runs; a model-proposed release label is never sufficient.
        from .kit_evolution import copy_active_version

        record=read(manifest)
        submission_id=digest({'manifest':file_hash(manifest),'package':package})
        folder=self.root/'submissions'/submission_id
        with run_lock(self.root):
            if (folder/'submission.json').exists():
                return read(folder/'submission.json')
            folder.mkdir(parents=True,exist_ok=True)
            copy_active_version(manifest,folder/'runtime')
            if file_hash(folder/'runtime/kit.mjs')!=record['sha256']:
                raise ValueError('KIT_SUBMISSION_COPY_MISMATCH')
            cycle=Path(record['path']).parent.parent
            permissions=read(cycle/'permissions.json')
            proposal=read(cycle/'proposal.json')
            write_json(folder/'permissions.json',permissions)
            write_json(folder/'proposal.json',proposal)
            shutil.copy2(cycle/'exercise.json',folder/'exercise.json')
            decision=read(record.get('validation_path',cycle/'decision.json'))
            write_json(folder/'activation.json',decision)
            data={'id':submission_id,'package':package,'subject':subject,'candidate_sha256':record['sha256'],
                  'base_sha256':permissions['base_sha256'],'state':'submitted',
                  'provenance':str(Path(manifest).resolve()),
                  'input_hashes':self._submission_hashes(folder)}
            write_json(folder/'submission.json',data)
            return data

    def _submission_hashes(self, folder):
        paths=[*Path(folder).glob('runtime/*'),*Path(folder).glob('*.json')]
        return {p.relative_to(folder).as_posix():file_hash(p) for p in paths if p.is_file() and p.name not in {'submission.json','validation.json'}}

    def validate(self, submission_id, heldout_runs=()):
        if not re.fullmatch(r'[a-f0-9]{64}',submission_id):
            raise ValueError('INVALID_KIT_SUBMISSION_ID')
        folder=self.root/'submissions'/submission_id
        submission=read(folder/'submission.json')
        if self._submission_hashes(folder)!=submission['input_hashes']:
            raise ValueError('KIT_SUBMISSION_CHANGED')
        # Re-run tests in a worker against the frozen submitted code. Historical
        # passed booleans are not enough to publish shared executable code.
        from .adaptive import regressions
        from .kit_evolution import apply_proposal

        base=None
        package=submission['package']
        for release in (self.root/'releases'/package).glob('*/release.json'):
            if read(release)['files']['kit.mjs']==submission['base_sha256']:
                base=self.verify_release(package,release.parent.name)[0]/'kit.mjs'
                break
        if base is None:
            raise ValueError('KIT_SUBMISSION_BASE_NOT_IN_LIBRARY')
        permissions=read(folder/'permissions.json')
        reconstructed,_=apply_proposal(base.read_text(encoding='utf-8'),read(folder/'proposal.json'),permissions['granted_methods'])
        if digest(reconstructed)!=digest((folder/'runtime/kit.mjs').read_text(encoding='utf-8')):
            raise ValueError('KIT_SUBMISSION_PATCH_MISMATCH')
        for dep in package_files(folder/'runtime'):
            if dep.suffix=='.mjs' and dep.name!='kit.mjs' and file_hash(dep)!=file_hash(base.parent/dep.name):
                raise ValueError('KIT_PROTECTED_DEPENDENCY_CHANGED')
        validation_id=uuid.uuid4().hex
        checks=folder/'checks'/validation_id
        compatibility=regressions(folder/'runtime/kit.mjs',checks/'compatibility')
        capability=regressions(folder/'runtime/kit.mjs',checks/'capability',folder/'exercise.json')
        sites=[]
        for run in map(Path,heldout_runs):
            result=read(run/'result.json')
            index=result.get('best_attempt')
            if index is None:
                continue
            attempt=run/f'attempt-{index}'
            metrics=read(attempt/'metrics.json')
            review=read(attempt/'review.json')
            from .design import ACCEPT, validated_scores
            scores=validated_scores(review)
            kit_manifest=read(run/'input-manifest.json')
            pinned=run/'kit-versions/base/kit.mjs'
            render_path=attempt/'render-manifest.json'
            render=read(render_path) if render_path.exists() else {}
            selection_path=attempt/'selected-runtime/selection.json'
            selection=read(selection_path) if selection_path.exists() else {}
            correct_kit=(kit_manifest.get('kit_sha256')==submission['candidate_sha256'] and pinned.is_file()
                         and file_hash(pinned)==submission['candidate_sha256']
                         and selection.get('master_sha256')==submission['candidate_sha256'])
            real_render=(render.get('passed') is True and (attempt/'bundle.js').is_file()
                         and render.get('bundle_sha256')==file_hash(attempt/'bundle.js'))
            accepted=(correct_kit and real_render and result.get('accepted') is True
                      and result.get('evaluation_complete',True) and metrics['passed']
                      and all(scores[k]>=v for k,v in ACCEPT.items()))
            sites.append({'object_id':result.get('object_id'),'accepted':accepted,
                          'evidence_sha256':result.get('evidence_sha256'),'correct_kit':correct_kit,
                          'real_render_verified':real_render,'run':str(run.resolve()),
                          'artifacts':{str(p.resolve()):file_hash(p) for p in
                              [run/'result.json',run/'input-manifest.json',attempt/'review.json',attempt/'metrics.json',
                               render_path,attempt/'bundle.js',selection_path,pinned] if p.is_file()},
                          'review_sha256':file_hash(attempt/'review.json'),'metrics_sha256':file_hash(attempt/'metrics.json')})
        policy=read(self.root/'policy.json')
        minimum=policy['incubating']['minimum_fixture_cases']
        passed=(len(compatibility)>=minimum and len(capability)>=minimum and
                all(c.get('passed') is True for c in compatibility+capability) and read(folder/'activation.json').get('activated') is True)
        accepted_sites={s['object_id'] for s in sites if s['accepted'] and s['object_id'] and s['evidence_sha256']}
        validation={'submission':submission_id,'input_hashes':submission['input_hashes'],
                    'policy_sha256':file_hash(self.root/'policy.json'),'compatibility':compatibility,'capability':capability,
                    'incubating_eligible':passed,'stable_eligible':passed and len(accepted_sites)>=policy['stable']['minimum_distinct_accepted_sites'],
                    'heldout_sites':sites,'checks':str(checks.relative_to(self.root))}
        write_json(folder/'validation.json',validation)
        submission['validation_sha256']=file_hash(folder/'validation.json')
        write_json(folder/'submission.json',submission)
        return validation

    def promote(self, submission_id, channel, token, subject='workflow', set_default=False):
        if channel not in ('incubating','stable') or not re.fullmatch(r'[a-f0-9]{64}',submission_id):
            raise ValueError('INVALID_KIT_PROMOTION')
        folder=self.root/'submissions'/submission_id
        submission=read(folder/'submission.json')
        package=submission['package']
        self.authorize(token,subject,package,'promote-'+channel)
        if set_default:
            self.authorize(token,subject,package,'set-default')
        with run_lock(self.root):
            validation=read(folder/'validation.json')
            if (file_hash(folder/'validation.json')!=submission.get('validation_sha256') or
                self._submission_hashes(folder)!=submission['input_hashes'] or validation['input_hashes']!=submission['input_hashes'] or
                validation['policy_sha256']!=file_hash(self.root/'policy.json') or not validation.get(channel+'_eligible')):
                raise ValueError('KIT_PROMOTION_GATES_FAILED')
            if channel=='stable':
                for site in validation['heldout_sites']:
                    if site['accepted'] and any(not Path(path).is_file() or file_hash(path)!=expected
                                                for path,expected in site['artifacts'].items()):
                        raise ValueError('KIT_HELDOUT_EVIDENCE_CHANGED')
            registry=read(self.root/'registry.json')
            channel_head=registry['packages'][package]['channels'][channel]
            head,_=self.resolve(package,version=channel_head) if channel_head else self.resolve(package)
            if file_hash(head/'kit.mjs') not in (submission['base_sha256'],submission['candidate_sha256']):
                raise ValueError('KIT_SHARED_HEAD_CONFLICT_REBASE_REQUIRED')
            paths=package_files(folder/'runtime')
            if (folder/'runtime/version.json').is_file():
                paths.append(folder/'runtime/version.json')
            hashes={p.name:file_hash(p) for p in paths}
            version=digest(hashes)
            destination=self.root/'releases'/package/version
            if not destination.exists():
                destination.mkdir(parents=True)
                for path in paths:
                    shutil.copy2(path,destination/path.name)
                write_json(destination/'release.json',{'schema':'shared-kit-release-1','package':package,'version':version,
                    'files':hashes,'channel':channel,'submission':submission_id,'validation_sha256':file_hash(folder/'validation.json')})
                write_json(destination/'context-index.json',{'cards':[{'id':c['id'],'methods':c['methods']} for c in cards(destination/'kit-api.md').values()]})
            self.verify_release(package,version)
            previous=registry['packages'][package]['channels'][channel]
            registry['packages'][package]['channels'][channel]=version
            if set_default:
                registry['packages'][package]['default_channel']=channel
            registry['revision']+=1
            write_json(self.root/'registry.json',registry)
            write_json(self.root/'events'/f'{uuid.uuid4().hex}.json',{'action':'promote','package':package,'channel':channel,
                'version':version,'previous':previous,'subject':subject,'grant_fingerprint':digest(token),'submission':submission_id})
            return {'package':package,'channel':channel,'version':version,'default_changed':set_default}

    def rollback(self, package, channel, version, token, subject='operator'):
        self.authorize(token,subject,package,'rollback')
        if channel not in ('incubating','stable'):
            raise ValueError('INVALID_KIT_CHANNEL')
        self.verify_release(package,version)
        with run_lock(self.root):
            registry=read(self.root/'registry.json')
            history=[read(p) for p in (self.root/'events').glob('*.json')]
            installed={e['version'] for e in history if e['package']==package and e['channel']==channel and e['action']=='promote'}
            if channel=='incubating':
                installed.add(registry['packages'][package]['channels']['builtin'])
            if version not in installed:
                raise ValueError('KIT_ROLLBACK_REQUIRES_PREVIOUS_CHANNEL_RELEASE')
            prior=registry['packages'][package]['channels'][channel]
            registry['packages'][package]['channels'][channel]=version
            registry['revision']+=1
            write_json(self.root/'registry.json',registry)
            write_json(self.root/'events'/f'{uuid.uuid4().hex}.json',{'action':'rollback','package':package,'channel':channel,
                'version':version,'previous':prior,'subject':subject,'grant_fingerprint':digest(token)})
        return {'package':package,'channel':channel,'version':version}
