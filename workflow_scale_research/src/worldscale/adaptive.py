"""Kit developer nodes evaluated in isolated versions and activated per run."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import psutil

from . import design, georef, kit_evolution
from .artifacts import file_hash, run_lock, write_json
from .config import ROOT
from .provider import Provider


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def regressions(kit, folder, exercise=None):
    command=[sys.executable, '-m', 'worldscale.kit_regression', '--kit', str(kit), '--out', str(folder)]
    if exercise:
        command+=['--exercise',str(exercise)]
    process = subprocess.Popen(command,
                               cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
    try:
        stdout, stderr = process.communicate(timeout=240)
    except subprocess.TimeoutExpired:
        parent = psutil.Process(process.pid)
        for child in parent.children(recursive=True):
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass
        process.kill()
        stdout, stderr = process.communicate()
        result = [{'passed':False,'error':'KIT_REGRESSION_WALL_TIME_LIMIT'}]
    else:
        report = folder / 'result.json'
        # Exit 2 means completed negative checks, not a crashed worker. Preserve
        # per-case diagnostics so the next developer can correct the actual bug.
        result = read(report)['cases'] if report.exists() and process.returncode in (0, 2) else [{'passed':False,'error':stderr[-1800:]}]
    write_json(folder / 'worker.json', {'exit_code':process.returncode,'stdout':stdout[-4000:],'stderr':stderr[-4000:]})
    return result


def _evolve_design(source_run, run, settings, max_cycles=1, max_tokens=220000, provider=None):
    source_run, run = Path(source_run).resolve(), Path(run).resolve()
    if not 1 <= max_cycles <= 3:
        raise ValueError('KIT_CYCLE_LIMIT_MUST_BE_1_TO_3')
    if run.exists():
        raise ValueError('USE_NEW_KIT_EVOLUTION_RUN')
    run.mkdir(parents=True)
    with run_lock(run):
        provider = provider or Provider(settings, run, max_calls=3+5*max_cycles, max_tokens=max_tokens, max_seconds=2400)
        original = read(source_run/'result.json')
        best = original.get('best_attempt')
        if best is None:
            raise ValueError('KIT_EVOLUTION_REQUIRES_BUILDABLE_BASELINE')
        source = source_run/f'attempt-{best}'
        site, style = read(source_run/'site.json'),read(source_run/'style.json')
        code = (source/'design.mjs').read_text(encoding='utf-8')
        evidence_path = read(source_run/'fit.json').get('evidence_path')
        # Resolve by the content pin, never by a hardcoded building name.
        evidence = None
        if evidence_path and Path(evidence_path).exists():
            evidence = georef.load_evidence(evidence_path)
        if evidence is None:
            for path in sorted((ROOT/'inputs/evidence').glob('*/evidence.json')):
                if file_hash(path) == original['evidence_sha256']:
                    evidence=georef.load_evidence(path)
                    break
        if evidence is None:
            raise ValueError('PINNED_EVIDENCE_BUNDLE_NOT_FOUND')
        registration=site.get('registration')
        if registration is None:
            registration=next((item for item in reversed(read(source_run/'fit.json').get('trace',[]))
                               if item.get('stage') in ('registration-final','registration')),None)
        if registration and evidence.get('wings'):
            from .brief import registered_wings
            fitted=design.massing.Registration(**{k:registration.get(k,0) for k in ('dx','dz','grow')})
            site={**site,'registration':fitted.model_dump(),'wings':registered_wings(evidence,fitted)}
        write_json(run/'site.json',site)
        write_json(run/'style.json',style)
        references = source_run/'reference-sheet.jpg'
        details = source_run/'reference-details.jpg'
        if not details.exists():
            details = design.detail_sheet(evidence,run,run/'reference-details.jpg')
        style_images = sorted(source_run.glob('style-*.jpg'))
        source_kit=source_run/'kit-versions/base'
        if (source_kit/'kit.mjs').is_file():
            shutil.copytree(source_kit,run/'versions/base')
            active=run/'versions/base/kit.mjs'
        else:
            # Legacy experiments had no pinned kit. Re-render the current
            # snapshot as a fresh control rather than reuse historical scores.
            active = kit_evolution.snapshot(run/'versions/base')
        protected_hashes={p.name:file_hash(p) for p in (ROOT/'runtime').glob('*.mjs')}
        write_json(run/'input-manifest.json',{'source_run':str(source_run),'source_attempt':best,
            'evidence':evidence['path'],'evidence_sha256':file_hash(evidence['path']),
            'site_sha256':file_hash(run/'site.json'),
            'shared_runtime_hashes':protected_hashes,'base_kit':file_hash(active),'max_cycles':max_cycles})
        baseline=run/'baseline'
        metrics,error=design.render_attempt(baseline,code,site,style,evidence,kit_path=active)
        if error:
            result={'accepted':False,'status':'baseline-failed','error':error}
            write_json(run/'result.json',result)
            return result
        review=design.critic(provider,'kit-baseline-critic',site,style,metrics,
            [references,baseline/'render-sheet.jpg',*style_images,details,baseline/'detail-sheet.jpg'])
        scores=design.validated_scores(review)
        write_json(baseline/'review.json',review)
        history=[]
        for prior in sorted(source_run.glob('attempt-*/review.json')):
            history.append({'attempt':prior.parent.name,'historical_review':read(prior),
                            'note':'Historical implementation; compare against actual pinned source and current control below.'})
        history.append({'current_pinned_review':review,'metrics':metrics})
        cycles=[]
        selected_folder=baseline
        for index in range(max_cycles):
            if metrics['passed'] and all(scores[k]>=v for k,v in design.ACCEPT.items()):
                break
            proposal_folder=run/f'cycle-{index}'
            candidate=kit_evolution.propose(provider,proposal_folder,active,history,
                [references,selected_folder/'render-sheet.jpg',*style_images,details,selected_folder/'detail-sheet.jpg'],site)
            if candidate is None:
                decision=read(proposal_folder/'decision.json')
                if decision.get('status')=='fix-design':
                    reply=design.author(provider,f'design-repair-{index}',site,style,
                        [references,*style_images,details,selected_folder/'render-sheet.jpg',selected_folder/'detail-sheet.jpg'],
                        previous=code,feedback={'route':decision,'review':review,
                            'instruction':'Correct the highest-value observed architectural defects using the existing API. Preserve measured geometry and supported details; do not invent ornament.'},
                        kit_api=active.parent/'kit-api.md')
                    folder=proposal_folder/'design-repair'
                    after,error=design.render_attempt(folder,reply['code'],site,style,evidence,kit_path=active)
                    if error:
                        decision.update({'status':'design-repair-failed','error':error})
                    else:
                        after_review=design.critic(provider,f'design-repair-critic-{index}',site,style,after,
                            [references,folder/'render-sheet.jpg',*style_images,details,folder/'detail-sheet.jpg'])
                        after_scores=design.validated_scores(after_review)
                        write_json(folder/'review.json',after_review)
                        def rank(m,s):
                            return design.candidate_rank({'accepted':m['passed'] and all(s[k]>=v for k,v in design.ACCEPT.items()),
                                'metrics_passed':m['passed'],'scores':s})
                        improved=(after['passed'] and after['mean_oblique_iou']>=metrics['mean_oblique_iou']-.025
                                  and after_scores['likeness']>=scores['likeness']-.02 and rank(after,after_scores)>rank(metrics,scores))
                        decision.update({'status':'design-refined','selected':improved,'kit_modified':False,
                                         'before_scores':scores,'after_scores':after_scores})
                        if improved:
                            metrics,review,scores,code,selected_folder=after,after_review,after_scores,reply['code'],folder
                    write_json(proposal_folder/'decision.json',decision)
                    cycles.append(decision)
                    history.append({'design_repair':decision,'review':review})
                    continue
                cycles.append(decision)
                if decision.get('status')=='proposal-rejected':
                    history.append({'kit_failure':decision,
                                    'rejected_proposal':read(proposal_folder/'proposal.json')})
                    continue
                break
            candidate_hash=file_hash(candidate)
            regression_results=regressions(candidate,proposal_folder/'regressions')
            exercise_path=proposal_folder/'exercise.json'
            if exercise_path.exists():
                regression_results+=regressions(candidate,proposal_folder/'capability-regressions',exercise_path)
            else:
                regression_results.append({'passed':False,'error':'UNEXERCISED_NEW_KIT_CAPABILITY'})
            if not regression_results or not all(r.get('passed') for r in regression_results):
                decision={'activated':False,'status':'regression-failed','regressions':regression_results}
                write_json(proposal_folder/'decision.json',decision)
                cycles.append(decision)
                history.append({'kit_failure':decision,
                                'rejected_proposal':read(proposal_folder/'proposal.json')})
                continue
            permissions=read(proposal_folder/'permissions.json')
            candidate_methods=kit_evolution.methods(candidate.read_text(encoding='utf-8'))
            consumer_context={'new_kit_api':[name for name in permissions['added_methods'] if not name.startswith('_')],
                'review':review,
                'capability_implementation':{name:candidate_methods[name] for name in permissions['added_methods']},
                'usage_policy':'Use documented input constraints. Fit roof wings to measured site facts; do not assume raw footprint corners are exact rectangles. Never change measured walls. Exercise markers are test metadata, not real design inputs.'}
            candidate_code=code
            if permissions.get('consumer_required',bool(permissions['added_methods'])):
                # A new API requires a design consumer; existing-method fixes
                # are compared with exactly the same script for attribution.
                reply=design.author(provider,f'kit-consumer-{index}',site,style,
                    [references,*style_images,details,selected_folder/'render-sheet.jpg'],
                    previous=code,feedback=consumer_context,
                    kit_api=candidate.parent/'kit-api.md')
                candidate_code=reply['code']
            folder=proposal_folder/'render'
            after,error=design.render_attempt(folder,candidate_code,site,style,evidence,kit_path=candidate)
            if error and permissions.get('consumer_required',bool(permissions['added_methods'])):
                # A bad caller should not force another expensive library rewrite.
                # One bounded repair gets the actual runtime error and API source.
                reply=design.author(provider,f'kit-consumer-repair-{index}',site,style,
                    [references,*style_images,details,selected_folder/'render-sheet.jpg'],
                    previous=candidate_code,feedback={**consumer_context,'build_error':error,
                        'instruction':'Correct the usage of the tested kit API. Do not silently skip the new capability.'},
                    kit_api=candidate.parent/'kit-api.md')
                candidate_code=reply['code']
                folder=proposal_folder/'render-repair'
                after,error=design.render_attempt(folder,candidate_code,site,style,evidence,kit_path=candidate)
            if error:
                decision={'activated':False,'status':'render-failed','error':error}
                write_json(proposal_folder/'decision.json',decision)
                cycles.append(decision)
                history.append({'kit_failure':decision,
                                'rejected_proposal':read(proposal_folder/'proposal.json')})
                continue
            after_review=design.critic(provider,f'kit-candidate-critic-{index}',site,style,after,
                [references,folder/'render-sheet.jpg',*style_images,details,folder/'detail-sheet.jpg'])
            after_scores=design.validated_scores(after_review)
            write_json(folder/'review.json',after_review)
            decision=kit_evolution.activation_decision(metrics,after,scores,after_scores,regression_results)
            if candidate_hash!=file_hash(candidate):
                raise ValueError('KIT_CHANGED_DURING_EVALUATION')
            decision.update({'candidate_sha256':candidate_hash,'before_scores':scores,'after_scores':after_scores})
            write_json(proposal_folder/'decision.json',decision)
            cycles.append(decision)
            history.append({'review':after_review,'metrics':after,'decision':decision,
                            'kit_failure':None if decision['activated'] else decision,
                            'rejected_proposal':None if decision['activated'] else read(proposal_folder/'proposal.json')})
            if decision['activated']:
                active,metrics,review,scores,code,selected_folder=candidate,after,after_review,after_scores,candidate_code,folder
                write_json(run/'active-kit.json',{'path':str(active),'sha256':candidate_hash,'cycle':index,'scope':'run-local',
                    'modules':{p.name:file_hash(p) for p in active.parent.glob('*.mjs')},
                    'validation_path':str(proposal_folder/'decision.json'),
                    'validation_sha256':file_hash(proposal_folder/'decision.json')})
        unchanged=all(file_hash(ROOT/'runtime'/name)==value for name,value in protected_hashes.items())
        if not unchanged:
            raise ValueError('SHARED_KIT_CHANGED_DURING_EVOLUTION')
        provider.save()
        result={'accepted':metrics['passed'] and all(scores[k]>=v for k,v in design.ACCEPT.items()),
                'acceptance_basis':'metric checks plus automated critic; no human acceptance',
                'status':'kit-evolution-complete','cycles':cycles,'selected_render':str(selected_folder),
                'active_kit':str(active),'shared_runtime_unchanged':unchanged,'scores':scores,'usage':provider.usage}
        write_json(run/'result.json',result)
        return result


def evolve_design(source_run, run, settings, max_cycles=1, max_tokens=220000, provider=None):
    existed = Path(run).exists()
    try:
        return _evolve_design(source_run,run,settings,max_cycles,max_tokens,provider)
    except Exception as exc:
        if existed:
            raise
        path=Path(run)
        path.mkdir(parents=True,exist_ok=True)
        usage_file=path/'usage.json'
        result={'accepted':False,'status':'kit-evolution-blocked','error':type(exc).__name__+': '+str(exc),
                'note':'No automatic retry; provider failures may have unknown billed usage.',
                'usage':provider.usage if provider else read(usage_file) if usage_file.exists() else None}
        write_json(path/'result.json',result)
        return result
